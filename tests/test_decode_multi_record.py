"""Tests voor generieke multi-record decode en compact datumformaat (TDD)."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.decode import (
    _detect_date_format,
    _to_compact_expr,
    decode_multi_record_csv,
    decode_ro,
)
from mbo_bekostiging_bestanden.ingest import read_ro

DEMO_H15 = Path("data/01-raw/demo/h15")
RO_27DV = DEMO_H15 / "RO_27DV_20240731_20260324.csv"


# ---------------------------------------------------------------------------
# Compact datumformaat detector
# ---------------------------------------------------------------------------

def test_detect_date_format_iso():
    assert _detect_date_format("2026-03-25") == "iso"


def test_detect_date_format_dutch():
    assert _detect_date_format("1-8-2025") == "dutch"


def test_detect_date_format_compact():
    assert _detect_date_format("20251119") == "compact"


# ---------------------------------------------------------------------------
# Compact datumexpressie
# ---------------------------------------------------------------------------

def test_to_compact_expr_parses_correctly():
    df = pl.DataFrame({"d": ["20251119", "20230130", ""]})
    result = df.with_columns(_to_compact_expr(pl.col("d")).alias("d"))
    assert result["d"].dtype == pl.Date
    assert result["d"][0] == date(2025, 11, 19)
    assert result["d"][2] is None


# ---------------------------------------------------------------------------
# Generieke decode
# ---------------------------------------------------------------------------

def test_decode_multi_record_csv_returns_dict():
    frames = read_ro(RO_27DV)
    result = decode_multi_record_csv(frames, "ro")
    assert isinstance(result, dict)


def test_decode_multi_record_csv_same_output_as_decode_ro():
    frames = read_ro(RO_27DV)
    via_generic = decode_multi_record_csv(frames, "ro")
    via_wrapper = decode_ro(frames)
    assert via_generic.keys() == via_wrapper.keys()
    for rt in via_generic:
        assert via_generic[rt].equals(via_wrapper[rt])


def test_decode_ro_wrapper_still_works():
    frames = read_ro(RO_27DV)
    result = decode_ro(frames)
    assert result["VLP"]["DatumAanmaak"].dtype == pl.Date


# ---------------------------------------------------------------------------
# Validate wrapper
# ---------------------------------------------------------------------------

def test_validate_single_row_driven_by_schema():
    """VLP/SLR-check komt uit schema, niet uit hardcoded constante."""
    from mbo_bekostiging_bestanden.validate import validate_multi_record
    frames = decode_ro(read_ro(RO_27DV))
    result = validate_multi_record(frames, "ro")
    assert result is frames


def test_validate_multi_record_unknown_schema_raises():
    from mbo_bekostiging_bestanden.validate import validate_multi_record
    frames = decode_ro(read_ro(RO_27DV))
    with pytest.raises(FileNotFoundError):
        validate_multi_record(frames, "bestaat_niet")
