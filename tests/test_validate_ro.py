"""Tests voor RO-validatie (TDD)."""

from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.decode import decode_ro
from mbo_bekostiging_bestanden.ingest import read_ro
from mbo_bekostiging_bestanden.validate import validate_ro

DEMO_H15 = Path("data/01-raw/demo/h15")
RO_27DV = DEMO_H15 / "RO_27DV_20240731_20260324.csv"


@pytest.fixture
def frames():
    return decode_ro(read_ro(RO_27DV))


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------

def test_validate_ro_returns_frames(frames):
    result = validate_ro(frames)
    assert result is frames


# ---------------------------------------------------------------------------
# Kolomcontroles
# ---------------------------------------------------------------------------

def test_validate_ro_missing_column_raises(frames):
    bad = {**frames, "VLP": frames["VLP"].drop("BRIN")}
    with pytest.raises(ValueError, match="VLP"):
        validate_ro(bad)


def test_validate_ro_missing_column_mentions_field(frames):
    bad = {**frames, "PER": frames["PER"].drop("Geboortedatum")}
    with pytest.raises(ValueError, match="Geboortedatum"):
        validate_ro(bad)


# ---------------------------------------------------------------------------
# Structuurcontroles
# ---------------------------------------------------------------------------

def test_validate_ro_vlp_multiple_rows_raises(frames):
    bad = {**frames, "VLP": pl.concat([frames["VLP"], frames["VLP"]])}
    with pytest.raises(ValueError, match="VLP"):
        validate_ro(bad)


def test_validate_ro_slr_multiple_rows_raises(frames):
    bad = {**frames, "SLR": pl.concat([frames["SLR"], frames["SLR"]])}
    with pytest.raises(ValueError, match="SLR"):
        validate_ro(bad)


# ---------------------------------------------------------------------------
# Generieke validate_multi_record
# ---------------------------------------------------------------------------

def test_validate_multi_record_passes_ro_frames(frames):
    from mbo_bekostiging_bestanden.validate import validate_multi_record
    result = validate_multi_record(frames, "ro")
    assert result is frames


def test_validate_multi_record_single_row_check_from_schema(frames):
    """single_row-check komt uit schema — dubbele VLP gooit ValueError."""
    from mbo_bekostiging_bestanden.validate import validate_multi_record
    bad = {**frames, "VLP": pl.concat([frames["VLP"], frames["VLP"]])}
    with pytest.raises(ValueError, match="VLP"):
        validate_multi_record(bad, "ro")


def test_validate_multi_record_unknown_schema_raises(frames):
    from mbo_bekostiging_bestanden.validate import validate_multi_record
    with pytest.raises(FileNotFoundError):
        validate_multi_record(frames, "bestaat_niet")


# ---------------------------------------------------------------------------
# Alle demo-bestanden
# ---------------------------------------------------------------------------

def test_validate_ro_all_demo_files_pass():
    for path in DEMO_H15.glob("RO_*.csv"):
        frames = decode_ro(read_ro(path))
        validate_ro(frames)
