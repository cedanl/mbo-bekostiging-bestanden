"""Tests voor de CLI-wrappers (TDD)."""

import argparse
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.cli import _stapel, _verwerk, build_parser

DEMO_H15 = Path("data/01-raw/demo/h15")
RO = DEMO_H15 / "RO_21CY_20250730_20250731.csv"
TBGI = Path("data/01-raw/demo/h16/TBGI_25LX_2027_20251124.XML")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_build_parser_returns_parser():
    assert isinstance(build_parser(), argparse.ArgumentParser)


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
