"""Tests voor de ingestion-pipeline op de demo-data."""

from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.ingest import read_raw_file
from mbo_bekostiging_bestanden.pipeline import run_pipeline
from mbo_bekostiging_bestanden.validate import validate_data

DEMO = Path("data/01-raw/demo/bekostiging_demo.csv")


def test_read_raw_file_returns_rows():
    data = read_raw_file(DEMO)
    assert isinstance(data, pl.DataFrame)
    assert not data.is_empty()


def test_validate_rejects_empty():
    empty = pl.DataFrame()
    try:
        validate_data(empty)
    except ValueError:
        return
    raise AssertionError("validate_data had moeten falen op lege data")


def test_run_pipeline_writes_output(tmp_path):
    target = tmp_path / "out.parquet"
    data = run_pipeline(DEMO, target)
    assert target.exists()
    assert len(data) == 5
