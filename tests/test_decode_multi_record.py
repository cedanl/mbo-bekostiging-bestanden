"""Tests voor generieke multi-record decode en compact datumformaat (TDD)."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.decode import (
    _detect_date_format,
    _to_compact_expr,
    decode_multi_record_csv,
)
from mbo_bekostiging_bestanden.ingest import read_ro

DEMO_H15 = Path("data/01-raw/demo/h15")
RO_27DV = DEMO_H15 / "RO_27DV_20240731_20260324.csv"


# ---------------------------------------------------------------------------
# Compact datumformaat — detector
# ---------------------------------------------------------------------------

def test_detect_date_format_iso():
    assert _detect_date_format("2026-03-25") == "iso"


def test_detect_date_format_dutch():
    assert _detect_date_format("1-8-2025") == "dutch"


def test_detect_date_format_compact():
    assert _detect_date_format("20251119") == "compact"


# ---------------------------------------------------------------------------
# Compact datumexpressie — gedrag
# ---------------------------------------------------------------------------

def test_to_compact_expr_parses_date():
    df = pl.DataFrame({"d": ["20251119"]})
    result = df.with_columns(_to_compact_expr(pl.col("d")).alias("d"))
    assert result["d"][0] == date(2025, 11, 19)


def test_to_compact_expr_returns_date_type():
    df = pl.DataFrame({"d": ["20230130"]})
    result = df.with_columns(_to_compact_expr(pl.col("d")).alias("d"))
    assert result["d"].dtype == pl.Date


def test_to_compact_expr_empty_becomes_null():
    df = pl.DataFrame({"d": [""]})
    result = df.with_columns(_to_compact_expr(pl.col("d")).alias("d"))
    assert result["d"][0] is None


# ---------------------------------------------------------------------------
# Generieke decode — gedrag
# ---------------------------------------------------------------------------

def test_decode_multi_record_csv_dates_typed():
    """Datumvelden zijn pl.Date na decode via generieke functie."""
    frames = read_ro(RO_27DV)
    result = decode_multi_record_csv(frames, "ro")
    assert result["VLP"]["DatumAanmaak"].dtype == pl.Date


def test_decode_multi_record_csv_integers_typed():
    """Integervelden zijn pl.Int64 na decode via generieke functie."""
    frames = read_ro(RO_27DV)
    result = decode_multi_record_csv(frames, "ro")
    assert result["SLR"]["AantalPER"].dtype == pl.Int64


def test_decode_multi_record_csv_unknown_schema_raises():
    frames = read_ro(RO_27DV)
    with pytest.raises(FileNotFoundError):
        decode_multi_record_csv(frames, "bestaat_niet")
