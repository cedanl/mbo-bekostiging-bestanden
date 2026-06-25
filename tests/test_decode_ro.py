"""Tests voor RO-decode (TDD)."""

from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.decode import decode_ro
from mbo_bekostiging_bestanden.ingest import read_ro

DEMO_H15 = Path("data/01-raw/demo/h15")
RO_27DV = DEMO_H15 / "RO_27DV_20240731_20260324.csv"  # ISO-datums
RO_25LX = DEMO_H15 / "RO_25LX_20250101_20251231.csv"  # Nederlandse datums


# ---------------------------------------------------------------------------
# Datumvelden
# ---------------------------------------------------------------------------


def test_decode_ro_vlp_dates_are_date_type():
    result = decode_ro(read_ro(RO_27DV))
    for col in ["DatumBeginPeriode", "DatumEindePeriode", "DatumAanmaak"]:
        assert result["VLP"][col].dtype == pl.Date, f"{col} moet pl.Date zijn"


def test_decode_ro_iso_date_value():
    from datetime import date

    result = decode_ro(read_ro(RO_27DV))
    assert result["VLP"]["DatumAanmaak"][0] == date(2026, 3, 25)


def test_decode_ro_dutch_date_value():
    """25LX gebruikt dd-m-yyyy formaat zonder leading zeros."""
    from datetime import date

    result = decode_ro(read_ro(RO_25LX))
    assert result["VLP"]["DatumAanmaak"][0] == date(2026, 3, 23)


def test_decode_ro_isg_dates_are_date_type():
    result = decode_ro(read_ro(RO_27DV))
    for col in ["DatumInschrijving", "DatumUitschrijvingGepland"]:
        assert result["ISG"][col].dtype == pl.Date, f"{col} moet pl.Date zijn"


def test_decode_ro_empty_date_becomes_null():
    """Lege datumvelden (optionele velden) worden null, niet leeg string."""
    result = decode_ro(read_ro(RO_27DV))
    # DatumUitschrijvingWerkelijk is leeg voor actieve inschrijvingen
    col = result["ISG"]["DatumUitschrijvingWerkelijk"]
    assert col.dtype == pl.Date
    assert col.null_count() > 0


def test_decode_ro_per_geboortedatum_is_date():
    result = decode_ro(read_ro(RO_27DV))
    assert result["PER"]["Geboortedatum"].dtype == pl.Date


# ---------------------------------------------------------------------------
# Integervelden
# ---------------------------------------------------------------------------


def test_decode_ro_slr_counts_are_integer():
    result = decode_ro(read_ro(RO_27DV))
    for col in ["AantalPER", "AantalISG", "AantalISP", "AantalBPV", "AantalDIP"]:
        assert result["SLR"][col].dtype == pl.Int64, f"{col} moet pl.Int64 zijn"


# ---------------------------------------------------------------------------
# Datumformaat-detectie zonder VLP
# ---------------------------------------------------------------------------


def test_decode_ro_dates_typed_without_vlp():
    """Datumformaat wordt gevonden via andere recordtypes als VLP ontbreekt."""
    frames = read_ro(RO_27DV)
    frames_no_vlp = {rt: df for rt, df in frames.items() if rt != "VLP"}
    result = decode_ro(frames_no_vlp)
    assert result["ISG"]["DatumInschrijving"].dtype == pl.Date


def test_decode_ro_dutch_dates_typed_without_vlp():
    """Dutch datumformaat wordt ook zonder VLP correct gedetecteerd."""
    frames = read_ro(RO_25LX)
    frames_no_vlp = {rt: df for rt, df in frames.items() if rt != "VLP"}
    result = decode_ro(frames_no_vlp)
    assert result["ISG"]["DatumInschrijving"].dtype == pl.Date


# ---------------------------------------------------------------------------
# Alle demo-bestanden
# ---------------------------------------------------------------------------


def test_decode_ro_all_demo_files():
    for path in DEMO_H15.glob("RO_*.csv"):
        result = decode_ro(read_ro(path))
        assert result["VLP"]["DatumAanmaak"].dtype == pl.Date, (
            f"DatumAanmaak niet Date in {path.name}"
        )


# ---------------------------------------------------------------------------
# Lege strings → null
# ---------------------------------------------------------------------------


def test_decode_lege_strings_worden_null_in_string_kolommen():
    """Lege strings in String-kolommen worden null na decode."""
    result = decode_ro(read_ro(RO_27DV))
    col = result["ISG"]["RedenUitschrijving"]
    assert col.dtype == pl.String
    assert col.null_count() > 0, (
        "RedenUitschrijving heeft geen nulls (lege strings staan er nog in)"
    )
    assert (col == "").sum() == 0, "Er zijn nog lege strings in RedenUitschrijving"


def test_decode_lege_strings_worden_null_isp():
    result = decode_ro(read_ro(RO_27DV))
    for col_name in ("Niveau", "LocatiecodeVSV", "Leerroute", "Leerroutefase"):
        col = result["ISP"][col_name]
        assert (col == "").sum() == 0, f"Lege strings aanwezig in ISP.{col_name}"


# ---------------------------------------------------------------------------
# BPV.Omvang als integer
# ---------------------------------------------------------------------------


def test_decode_ro_bpv_omvang_is_integer():
    result = decode_ro(read_ro(RO_27DV))
    assert result["BPV"]["Omvang"].dtype == pl.Int64, "BPV.Omvang moet Int64 zijn"


def test_decode_ro_bpv_omvang_waarden():
    result = decode_ro(read_ro(RO_27DV))
    omvang = result["BPV"]["Omvang"].drop_nulls()
    assert len(omvang) > 0
    assert (omvang > 0).all()
