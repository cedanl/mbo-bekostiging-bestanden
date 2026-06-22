"""Tests voor de TBGI-pipeline (end-to-end, TDD)."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.pipeline import run_tbgi_pipeline

DEMO_H16 = Path("data/01-raw/demo/h16")
TBGI = DEMO_H16 / "TBGI_25LX_2027_20251124.XML"


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------


def test_run_tbgi_pipeline_contains_expected_tables(tmp_path):
    result = run_tbgi_pipeline(TBGI, tmp_path)
    assert {"Inschrijving", "Teldatum", "Diploma", "Signaal"} <= result.keys()


def test_run_tbgi_pipeline_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_tbgi_pipeline("bestaat_niet.xml", tmp_path)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def test_run_tbgi_pipeline_writes_parquet(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    written = {f.stem for f in tmp_path.glob("*.parquet")}
    assert written == set(frames.keys())


def test_run_tbgi_pipeline_csv_format(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path, fmt="csv")
    written = {f.stem for f in tmp_path.glob("*.csv")}
    assert written == set(frames.keys())


# ---------------------------------------------------------------------------
# Datums correct getypeerd
# ---------------------------------------------------------------------------


def test_run_tbgi_pipeline_inschrijving_datum_is_date(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    assert frames["Inschrijving"]["DatumInschrijving"].dtype == pl.Date


def test_run_tbgi_pipeline_inschrijving_datum_value(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    assert frames["Inschrijving"]["DatumInschrijving"][0] == date(2024, 2, 1)


def test_run_tbgi_pipeline_diploma_datum_is_date(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    assert frames["Diploma"]["DatumBehaald"].dtype == pl.Date


def test_run_tbgi_pipeline_diploma_datum_value(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    assert frames["Diploma"]["DatumBehaald"][0] == date(2025, 6, 17)


def test_run_tbgi_pipeline_teldatum_is_date(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    assert frames["Teldatum"]["Teldatum"].dtype == pl.Date


# ---------------------------------------------------------------------------
# Floats correct getypeerd
# ---------------------------------------------------------------------------


def test_run_tbgi_pipeline_bblbolfactor_is_float(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    assert frames["Teldatum"]["BBLBOLFactor"].dtype == pl.Float64


def test_run_tbgi_pipeline_bijdrage_is_float(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    col = frames["Teldatum"]["BijdrageInschrijvingAanDeelnemerswaarde"]
    assert col.dtype == pl.Float64


# ---------------------------------------------------------------------------
# Parquet-output bewaart types
# ---------------------------------------------------------------------------


def test_run_tbgi_pipeline_parquet_preserves_date(tmp_path):
    run_tbgi_pipeline(TBGI, tmp_path)
    df = pl.read_parquet(tmp_path / "Inschrijving.parquet")
    assert df["DatumInschrijving"].dtype == pl.Date


def test_run_tbgi_pipeline_parquet_preserves_float(tmp_path):
    run_tbgi_pipeline(TBGI, tmp_path)
    df = pl.read_parquet(tmp_path / "Teldatum.parquet")
    assert df["BBLBOLFactor"].dtype == pl.Float64


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def test_run_auto_pipeline_routes_tbgi(tmp_path):
    """run_auto_pipeline herkent TBGI-bestanden en roept de juiste pipeline aan."""
    from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline

    frames = run_auto_pipeline(TBGI, tmp_path)
    assert "Inschrijving" in frames
