"""Tests voor de GRONDSLAG-pipeline (end-to-end, TDD)."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.pipeline import run_grondslag_pipeline

DEMO_H17 = Path("data/01-raw/demo/h17")
GRONDSLAG = DEMO_H17 / "GRONDSLAG_IP_MBO_27DV_20251119_2025.csv"


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------


def test_run_grondslag_pipeline_contains_expected_recordtypes(tmp_path):
    result = run_grondslag_pipeline(GRONDSLAG, tmp_path)
    assert {"VLP", "PER", "ISG", "SLR"} <= result.keys()


def test_run_grondslag_pipeline_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_grondslag_pipeline("bestaat_niet.csv", tmp_path)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def test_run_grondslag_pipeline_writes_parquet(tmp_path):
    frames = run_grondslag_pipeline(GRONDSLAG, tmp_path)
    written = {f.stem for f in tmp_path.glob("*.parquet")}
    assert written == set(frames.keys())


def test_run_grondslag_pipeline_csv_format(tmp_path):
    frames = run_grondslag_pipeline(GRONDSLAG, tmp_path, fmt="csv")
    written = {f.stem for f in tmp_path.glob("*.csv")}
    assert written == set(frames.keys())


# ---------------------------------------------------------------------------
# Compact datumformaat correct getypeerd
# ---------------------------------------------------------------------------


def test_run_grondslag_pipeline_vlp_datum_is_date(tmp_path):
    """DatumAanmaak in VLP (compact YYYYMMDD) wordt pl.Date."""
    frames = run_grondslag_pipeline(GRONDSLAG, tmp_path)
    assert frames["VLP"]["DatumAanmaak"].dtype == pl.Date


def test_run_grondslag_pipeline_vlp_datum_value(tmp_path):
    frames = run_grondslag_pipeline(GRONDSLAG, tmp_path)
    assert frames["VLP"]["DatumAanmaak"][0] == date(2025, 11, 19)


def test_run_grondslag_pipeline_isg_dates_are_date(tmp_path):
    frames = run_grondslag_pipeline(GRONDSLAG, tmp_path)
    for col in ["DatumInschrijving", "DatumUitschrijvingGepland"]:
        assert frames["ISG"][col].dtype == pl.Date, f"{col} is geen pl.Date"


def test_run_grondslag_pipeline_per_leeftijden_are_int(tmp_path):
    """Leeftijden in PER zijn Int64."""
    frames = run_grondslag_pipeline(GRONDSLAG, tmp_path)
    for col in ["Leeftijd1", "Leeftijd2", "Leeftijd3", "Leeftijd4"]:
        assert frames["PER"][col].dtype == pl.Int64, f"{col} is geen Int64"


def test_run_grondslag_pipeline_slr_counts_are_int(tmp_path):
    frames = run_grondslag_pipeline(GRONDSLAG, tmp_path)
    assert frames["SLR"]["AantalPER"].dtype == pl.Int64


# ---------------------------------------------------------------------------
# Parquet-output bevat correcte types
# ---------------------------------------------------------------------------


def test_run_grondslag_pipeline_parquet_preserves_date(tmp_path):
    run_grondslag_pipeline(GRONDSLAG, tmp_path)
    vlp = pl.read_parquet(tmp_path / "VLP.parquet")
    assert vlp["DatumAanmaak"].dtype == pl.Date


def test_run_grondslag_pipeline_parquet_preserves_int(tmp_path):
    run_grondslag_pipeline(GRONDSLAG, tmp_path)
    slr = pl.read_parquet(tmp_path / "SLR.parquet")
    assert slr["AantalPER"].dtype == pl.Int64
