"""Tests voor generieke multi-record decode en compact datumformaat (TDD)."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.decode import (
    _detect_date_format,
    decode_frames,
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


def _compact(waarden: list[str]) -> pl.Series:
    frames = {"VLP": pl.DataFrame({"DatumAanmaak": waarden})}
    return decode_frames(frames, "ro")["VLP"]["DatumAanmaak"]


def test_compact_datum_wordt_date():
    kolom = _compact(["20251119"])
    assert kolom.dtype == pl.Date
    assert kolom[0] == date(2025, 11, 19)


def test_compact_lege_datum_wordt_null():
    assert _compact(["20251119", ""])[1] is None


# ---------------------------------------------------------------------------
# Generieke decode — gedrag
# ---------------------------------------------------------------------------


def test_decode_frames_unknown_schema_raises():
    frames = read_ro(RO_27DV)
    with pytest.raises(FileNotFoundError):
        decode_frames(frames, "bestaat_niet")


# ---------------------------------------------------------------------------
# Omringende witruimte (#392)
# ---------------------------------------------------------------------------


def test_omringende_witruimte_wordt_getrimd():
    """Domeincontrole trimt al; opslag moet dat ook doen, anders mislukken
    group-by en join op ``' 21CY '`` zonder foutmelding."""
    frames = {"VLP": pl.DataFrame({"BRIN": [" 21CY ", "21CY"], "Naam": ["a ", " b"]})}
    vlp = decode_frames(frames, "ro")["VLP"]
    assert vlp["BRIN"].to_list() == ["21CY", "21CY"]
    assert vlp["Naam"].to_list() == ["a", "b"]


def test_alleen_witruimte_wordt_null():
    frames = {"VLP": pl.DataFrame({"Naam": ["   ", "x"]})}
    assert decode_frames(frames, "ro")["VLP"]["Naam"].to_list() == [None, "x"]


def test_witruimte_rond_getal_en_datum_parseert():
    frames = {
        "VLP": pl.DataFrame({"DatumAanmaak": [" 20251119 "]}),
    }
    assert decode_frames(frames, "ro")["VLP"]["DatumAanmaak"][0] == date(2025, 11, 19)
