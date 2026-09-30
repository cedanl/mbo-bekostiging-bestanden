"""Tests voor de CLI-wrappers (TDD)."""

import argparse
import io
import sys
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.cli import _stapel, _verwerk, build_parser, main

DEMO_H15 = Path("data/01-raw/demo/h15")
RO = DEMO_H15 / "RO_21CY_20250730_20250731.csv"
TBGI = Path("data/01-raw/demo/h16/TBGI_25LX_2027_20251124.XML")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parser_verwerk_subcommand():
    parser = build_parser()
    args = parser.parse_args(["verwerk", str(RO), "/tmp/out"])
    assert args.command == "verwerk"
    assert args.fmt == "parquet"


def test_parser_stapel_subcommand(prepared_dirs):
    parser = build_parser()
    args = parser.parse_args(
        [
            "stapel",
            str(prepared_dirs["21CY"]),
            str(prepared_dirs["25LX"]),
            "--output",
            "/tmp/gestapeld",
        ]
    )
    assert args.command == "stapel"
    assert len(args.sources) == 2


def test_parser_stapel_relative_to(prepared_dirs):
    parser = build_parser()
    args = parser.parse_args(
        [
            "stapel",
            str(prepared_dirs["21CY"]),
            "--output",
            "/tmp/gestapeld",
            "--relative-to",
            str(prepared_dirs["base"]),
        ]
    )
    assert args.relative_to == prepared_dirs["base"]


# ---------------------------------------------------------------------------
# _verwerk
# ---------------------------------------------------------------------------


def test_verwerk_writes_parquet(tmp_path):
    args = argparse.Namespace(source=RO, target=tmp_path, fmt="parquet")
    _verwerk(args)
    assert any(tmp_path.glob("*.parquet"))


def test_verwerk_tbgi(tmp_path):
    args = argparse.Namespace(source=TBGI, target=tmp_path, fmt="parquet")
    _verwerk(args)
    assert (tmp_path / "Inschrijving.parquet").exists()


# ---------------------------------------------------------------------------
# _stapel
# ---------------------------------------------------------------------------


def test_stapel_writes_parquet(tmp_path, prepared_dirs):
    args = argparse.Namespace(
        sources=[prepared_dirs["21CY"], prepared_dirs["25LX"]],
        output=tmp_path,
        fmt="parquet",
        label_col="levering",
        relative_to=None,
    )
    _stapel(args)
    assert any(tmp_path.glob("*.parquet"))


def test_stapel_relative_to_labels(tmp_path, prepared_dirs):
    args = argparse.Namespace(
        sources=[prepared_dirs["21CY"], prepared_dirs["25LX"]],
        output=tmp_path,
        fmt="parquet",
        label_col="levering",
        relative_to=prepared_dirs["base"],
    )
    _stapel(args)
    isg = pl.read_parquet(tmp_path / "ISG.parquet")
    leveringen = set(isg["levering"].unique().to_list())
    assert leveringen == {"h15/21CY", "h15/25LX"}


def test_help_noemt_de_laag_per_commando():
    """Elk subcommando zegt of het brondata of het analysemodel oplevert (#213)."""
    regels = build_parser().format_help().splitlines()
    hulp = {
        r.split()[0]: r.lower()
        for r in regels
        if r.strip()[:4] in ("verw", "stap", "star")
    }
    assert "brondata" in hulp["verwerk"]
    assert "brondata" in hulp["stapel"]
    assert "analysemodel" in hulp["star"]


# ---------------------------------------------------------------------------
# Foutafhandeling (#291)
# ---------------------------------------------------------------------------


def test_main_toont_fail_closed_ingestfout_zonder_traceback(
    tmp_path, monkeypatch, capsys
):
    """Een kapot bronbestand geeft een korte melding op stderr en exitcode 1."""
    bron = tmp_path / "RO_99XX_20250801_20260731.csv"
    bron.write_text("VLP|99XX|2025-08-01|2026-07-31|2026-08-01\nXYZ|iets\n")
    monkeypatch.setattr(
        "sys.argv", ["mbo", "verwerk", str(bron), str(tmp_path / "prepared")]
    )

    with pytest.raises(SystemExit) as uit:
        main()

    assert uit.value.code == 1
    fout = capsys.readouterr().err
    assert "XYZ" in fout
    assert "Traceback" not in fout


def test_main_meldt_ontbrekende_bronmap_zonder_traceback(tmp_path, monkeypatch, capsys):
    """Een verkeerd pad is een gebruikersfout, geen crash (#353)."""
    ontbreekt = tmp_path / "bestaat_niet"
    monkeypatch.setattr(
        "sys.argv", ["mbo", "star", str(ontbreekt), "--output", str(tmp_path / "s")]
    )

    with pytest.raises(SystemExit) as uit:
        main()

    assert uit.value.code == 1
    assert str(ontbreekt) in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Windows-console (#353)
# ---------------------------------------------------------------------------


def test_cli_werkt_op_windows_console(tmp_path, monkeypatch):
    """Elk commando meldt zijn resultaat zonder UnicodeEncodeError op cp1252.

    Die fout is een ``ValueError``; ``main()`` zou hem als ingestfout met
    exitcode 1 melden terwijl de uitvoer al geschreven is.
    """
    prepared = tmp_path / "prepared"
    commandos = [
        ["verwerk", str(RO), str(prepared)],
        ["stapel", str(prepared), "--output", str(tmp_path / "gestapeld")],
        ["star", str(prepared), "--output", str(tmp_path / "star")],
    ]
    for commando in commandos:
        # Standaard Windows-console: cp1252 met errors="strict" op stdout.
        uitvoer = io.BytesIO()
        console = io.TextIOWrapper(uitvoer, encoding="cp1252", errors="strict")
        monkeypatch.setattr(sys, "stdout", console)
        monkeypatch.setattr(sys, "argv", ["mbo", *commando])
        main()
        console.flush()
        assert b" -> " in uitvoer.getvalue(), commando[0]
