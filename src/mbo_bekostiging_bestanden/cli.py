"""CLI voor de MBO-bekostigingsbestanden pipeline.

Gebruik:
    mbo verwerk <source> <target> [--fmt parquet|csv]
    mbo stapel <dir...> --output <dir> [--fmt parquet|csv]
              [--label-col <naam>] [--relative-to <pad>]
    mbo star <dir...> --output <dir> [--relative-to <pad>] [--scenario <label>]
              [--allow-quality-errors]
"""

import argparse
import sys
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.export import export_frames
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline, run_star
from mbo_bekostiging_bestanden.quality import (
    SCENARIO_ONBEKEND,
    KwaliteitsFout,
    lees_status,
)
from mbo_bekostiging_bestanden.stack import stack_prepared

# Exitcode bij quality-status fail (#289); 1 is een ingestfout (#291).
EXIT_KWALITEIT = 3

# stdout is alleen ASCII: een Windows-console (cp1252) kan geen "→" coderen en
# de UnicodeEncodeError kwam als ingestfout met exitcode 1 naar buiten (#353).
PIJL = "->"


def _meld_resultaat(actie: str, frames: dict[str, pl.DataFrame], doel: Path) -> None:
    rijen = sum(df.height for df in frames.values())
    print(f"{actie}: {len(frames)} tabellen, {rijen} rijen {PIJL} {doel}")


def _verwerk(args: argparse.Namespace) -> None:
    frames = run_auto_pipeline(args.source, args.target, fmt=args.fmt)
    _meld_resultaat("Verwerkt", frames, args.target)


def _stapel(args: argparse.Namespace) -> None:
    frames = stack_prepared(
        args.sources,
        label_col=args.label_col,
        relative_to=args.relative_to,
    )
    export_frames(frames, args.output, fmt=args.fmt)
    _meld_resultaat("Gestapeld", frames, args.output)


def _star(args: argparse.Namespace) -> None:
    star = run_star(
        args.sources,
        args.output,
        relative_to=args.relative_to,
        scenario=args.scenario,
        fail_on_errors=not args.allow_quality_errors,
    )
    _meld_resultaat("Star schema gebouwd", star, args.output)
    status, fouten = lees_status(args.output / "quality.json")
    if status == "fail":
        print(f"Let op: kwaliteitsstatus {status} ({fouten} error(s)), toegestaan.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mbo",
        description="MBO-bekostigingsbestanden pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_verwerk = sub.add_parser(
        "verwerk", help="Verwerk één ruw bestand tot brondata (Parquet per recordtype)"
    )
    p_verwerk.add_argument("source", type=Path, help="Pad naar het ruwe bronbestand")
    p_verwerk.add_argument("target", type=Path, help="Doelmap voor de uitvoer")
    p_verwerk.add_argument(
        "--fmt",
        default="parquet",
        choices=["parquet", "csv"],
        help="Uitvoerformaat (standaard: parquet)",
    )
    p_verwerk.set_defaults(func=_verwerk)

    p_stapel = sub.add_parser(
        "stapel", help="Stapel de brondata van meerdere leveringen"
    )
    p_stapel.add_argument(
        "sources",
        nargs="+",
        type=Path,
        help="Mappen met Parquet-bestanden (één per levering)",
    )
    p_stapel.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Doelmap voor de gestapelde uitvoer",
    )
    p_stapel.add_argument(
        "--fmt",
        default="parquet",
        choices=["parquet", "csv"],
        help="Uitvoerformaat (standaard: parquet)",
    )
    p_stapel.add_argument(
        "--label-col",
        default="levering",
        dest="label_col",
        help="Naam van de leveringskolom (standaard: levering)",
    )
    p_stapel.add_argument(
        "--relative-to",
        type=Path,
        default=None,
        dest="relative_to",
        help="Basispad voor relatieve leveringslabels",
    )
    p_stapel.set_defaults(func=_stapel)

    p_star = sub.add_parser(
        "star", help="Bouw het analysemodel (star schema) uit de brondata"
    )
    p_star.add_argument(
        "sources",
        nargs="+",
        type=Path,
        help="Mappen met Parquet-bestanden (één per levering)",
    )
    p_star.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Doelmap voor de star-schema-bestanden",
    )
    p_star.add_argument(
        "--relative-to",
        type=Path,
        default=None,
        dest="relative_to",
        help="Basispad voor relatieve leveringslabels",
    )
    p_star.add_argument(
        "--scenario",
        default=SCENARIO_ONBEKEND,
        help="Scenariolabel in quality.json, bijv. 'demo' of 'prod'",
    )
    p_star.add_argument(
        "--allow-quality-errors",
        action="store_true",
        dest="allow_quality_errors",
        help="Bouw ook bij kwaliteitsfouten (exploratief; komt in quality.json)",
    )
    p_star.set_defaults(func=_star)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except (ValueError, FileNotFoundError) as fout:
        # Fail-closed ingest (#257, #281) of een verkeerd pad (#353): de
        # melding noemt het bestand, dus een traceback voegt niets toe.
        print(f"mbo {args.command}: {fout}", file=sys.stderr)
        sys.exit(1)
    except KwaliteitsFout as fout:
        print(f"mbo {args.command}: {fout}", file=sys.stderr)
        sys.exit(EXIT_KWALITEIT)
