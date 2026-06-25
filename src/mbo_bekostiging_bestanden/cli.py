"""CLI voor de MBO-bekostigingsbestanden pipeline.

Gebruik:
    mbo verwerk <source> <target> [--fmt parquet|csv]
    mbo stapel <dir...> --output <dir> [--fmt parquet|csv]
              [--label-col <naam>] [--relative-to <pad>]
    mbo obt <dir...> --output <dir> [--relative-to <pad>]
"""

import argparse
from pathlib import Path

from mbo_bekostiging_bestanden.export import export_frames
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline, run_obt
from mbo_bekostiging_bestanden.stack import stack_prepared


def _verwerk(args: argparse.Namespace) -> None:
    frames = run_auto_pipeline(args.source, args.target, fmt=args.fmt)
    total = sum(df.height for df in frames.values())
    print(f"Verwerkt: {len(frames)} tabellen, {total} rijen → {args.target}")


def _stapel(args: argparse.Namespace) -> None:
    frames = stack_prepared(
        args.sources,
        label_col=args.label_col,
        relative_to=args.relative_to,
    )
    export_frames(frames, args.output, fmt=args.fmt)
    total = sum(df.height for df in frames.values())
    print(f"Gestapeld: {len(frames)} tabellen, {total} rijen → {args.output}")


def _obt(args: argparse.Namespace) -> None:
    obt = run_obt(args.sources, args.output, relative_to=args.relative_to)
    total = sum(df.height for df in obt.values())
    print(f"OBT gebouwd: {len(obt)} tabellen, {total} rijen → {args.output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mbo",
        description="MBO-bekostigingsbestanden pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_verwerk = sub.add_parser("verwerk", help="Verwerk één ruw bestand")
    p_verwerk.add_argument("source", type=Path, help="Pad naar het ruwe bronbestand")
    p_verwerk.add_argument("target", type=Path, help="Doelmap voor de uitvoer")
    p_verwerk.add_argument(
        "--fmt",
        default="parquet",
        choices=["parquet", "csv"],
        help="Uitvoerformaat (standaard: parquet)",
    )
    p_verwerk.set_defaults(func=_verwerk)

    p_stapel = sub.add_parser("stapel", help="Stapel meerdere prepared-mappen")
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

    p_obt = sub.add_parser("obt", help="Bouw OBT vanuit prepared-mappen")
    p_obt.add_argument(
        "sources",
        nargs="+",
        type=Path,
        help="Mappen met Parquet-bestanden (één per levering)",
    )
    p_obt.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Doelmap voor de vijf OBT-bestanden",
    )
    p_obt.add_argument(
        "--relative-to",
        type=Path,
        default=None,
        dest="relative_to",
        help="Basispad voor relatieve leveringslabels",
    )
    p_obt.set_defaults(func=_obt)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)
