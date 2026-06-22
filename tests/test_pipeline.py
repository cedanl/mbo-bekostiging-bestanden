"""Tests voor de RO-pipeline (end-to-end)."""

from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.pipeline import run_pipeline

DEMO_H15 = Path("data/01-raw/demo/h15")
RO_27DV = DEMO_H15 / "RO_27DV_20240731_20260324.csv"


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------


def test_run_pipeline_contains_expected_recordtypes(tmp_path):
    result = run_pipeline(RO_27DV, tmp_path)
    assert {"VLP", "PER", "ISG", "SLR"} <= result.keys()


def test_run_pipeline_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_pipeline("bestaat_niet.csv", tmp_path)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def test_run_pipeline_writes_parquet(tmp_path):
    frames = run_pipeline(RO_27DV, tmp_path)
    written = {f.stem for f in tmp_path.glob("*.parquet")}
    assert written == set(frames.keys())


def test_run_pipeline_csv_format(tmp_path):
    frames = run_pipeline(RO_27DV, tmp_path, fmt="csv")
    written = {f.stem for f in tmp_path.glob("*.csv")}
    assert written == set(frames.keys())


# ---------------------------------------------------------------------------
# Types na full pipeline
# ---------------------------------------------------------------------------


def test_run_pipeline_dates_are_typed(tmp_path):
    frames = run_pipeline(RO_27DV, tmp_path)
    assert frames["VLP"]["DatumAanmaak"].dtype == pl.Date


def test_run_pipeline_integers_are_typed(tmp_path):
    frames = run_pipeline(RO_27DV, tmp_path)
    assert frames["SLR"]["AantalPER"].dtype == pl.Int64


# ---------------------------------------------------------------------------
# Alle demo-bestanden
# ---------------------------------------------------------------------------


def test_run_pipeline_all_demo_files(tmp_path):
    for path in DEMO_H15.glob("RO_*.csv"):
        out = tmp_path / path.stem
        run_pipeline(path, out)
        assert len(list(out.glob("*.parquet"))) > 0, (
            f"Geen Parquet-uitvoer voor {path.name}"
        )


# ---------------------------------------------------------------------------
# Demo-data aanwezig
# ---------------------------------------------------------------------------


def test_demo_data_present():
    files = [f for f in Path("data/01-raw/demo").rglob("*") if f.is_file()]
    assert files, "Geen demo-bestanden gevonden in data/01-raw/demo"
