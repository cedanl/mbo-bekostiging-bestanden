"""Tests voor obt.py (OBT-bouwfuncties)."""

from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.obt import (
    _bouw_detail_bekostiging,
    _resolve_inschrijving,
    build_obt,
)
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline
from mbo_bekostiging_bestanden.stack import stack_prepared

RAW = Path("data/01-raw/demo")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def demo_stacked(tmp_path_factory):
    prepared = tmp_path_factory.mktemp("prepared")
    for raw_file in sorted(RAW.rglob("*")):
        if raw_file.suffix.lower() not in {".csv", ".xml"}:
            continue
        subdir = raw_file.parent.relative_to(RAW)
        run_auto_pipeline(raw_file, prepared / subdir / raw_file.stem)
    dirs = [d for d in sorted(prepared.glob("*/*")) if d.is_dir()]
    return stack_prepared(dirs, relative_to=prepared)


@pytest.fixture(scope="session")
def demo_obt(demo_stacked):
    return build_obt(demo_stacked)


# ---------------------------------------------------------------------------
# build_obt – input-validatie
# ---------------------------------------------------------------------------


def test_build_obt_raises_without_isp_and_inschrijving():
    with pytest.raises(ValueError, match="ISP"):
        build_obt({"PER": pl.DataFrame()})


def test_build_obt_raises_with_leeg_isp_en_geen_inschrijving():
    with pytest.raises(ValueError, match="ISP"):
        build_obt({"ISP": pl.DataFrame()})


def test_build_obt_tbgi_fallback_gebruikt_inschrijving_als_grain():
    """Zonder ISP maar met TBGI Inschrijving → obt_inschrijvingen gevuld."""
    inschrijving = pl.DataFrame({
        "levering": ["L1"],
        "BRIN": ["25LX"],
        "Burgerservicenummer": ["BSN1"],
        "Onderwijsnummer": [None],
        "Inschrijvingvolgnummer": ["001"],
    })
    result = build_obt({"Inschrijving": inschrijving})
    assert result["obt_inschrijvingen"].height == 1
    assert "_persoon_id" in result["obt_inschrijvingen"].columns


def test_build_obt_tbgi_fallback_detail_bekostiging_gevuld():
    """Teldatum verschijnt in detail_bekostiging ook als ISP ontbreekt."""
    inschrijving = pl.DataFrame({
        "levering": ["L1"],
        "BRIN": ["25LX"],
        "Burgerservicenummer": ["BSN1"],
        "Onderwijsnummer": [None],
        "Inschrijvingvolgnummer": ["001"],
    })
    teldatum = pl.DataFrame({
        "levering": ["L1"],
        "BRIN": ["25LX"],
        "Inschrijvingvolgnummer": ["001"],
        "Teldatum": ["2025-10-01"],
        "Bekostigingsstatus": ["A"],
    })
    result = build_obt({"Inschrijving": inschrijving, "Teldatum": teldatum})
    detail = result["detail_bekostiging"]
    assert detail.height == 1
    assert "TBGI" in detail["_bron"].to_list()


# ---------------------------------------------------------------------------
# build_obt – output-structuur
# ---------------------------------------------------------------------------


def test_build_obt_returns_five_tables(demo_obt):
    assert set(demo_obt.keys()) == {
        "obt_inschrijvingen",
        "detail_bpv",
        "detail_kzd_amo",
        "detail_bekostiging",
        "meta_leveringen",
    }


def test_obt_inschrijvingen_grain_isp(demo_obt, demo_stacked):
    """OBT behoudt exact het aantal ISP-rijen."""
    assert demo_obt["obt_inschrijvingen"].height == demo_stacked["ISP"].height


def test_obt_inschrijvingen_heeft_persoon_id(demo_obt):
    assert "_persoon_id" in demo_obt["obt_inschrijvingen"].columns


# ---------------------------------------------------------------------------
# KZD/AMO – DIP-fallback voor Inschrijvingvolgnummer
# ---------------------------------------------------------------------------


def test_kzd_aantal_bsn1_ingevuld(demo_obt):
    """BSN1 heeft 2 KZD-records; na DIP-fallback is KZD_Aantal=2 (niet null)."""
    obt = demo_obt["obt_inschrijvingen"]
    bsn1 = obt.filter(
        (pl.col("_persoon_id") == "BSN1")
        & (pl.col("levering") == "h17/GRONDSLAG_IP_MBO_27DV_20251119_2025")
    )
    assert bsn1.height >= 1
    assert bsn1["KZD_Aantal"].to_list()[0] == 2


def test_kzd_behaald_bsn1_ingevuld(demo_obt):
    obt = demo_obt["obt_inschrijvingen"]
    bsn1 = obt.filter(
        (pl.col("_persoon_id") == "BSN1")
        & (pl.col("levering") == "h17/GRONDSLAG_IP_MBO_27DV_20251119_2025")
    )
    assert bsn1["KZD_AantalBehaald"].to_list()[0] == 2


def test_detail_kzd_amo_geen_lege_inschrijvingvolgnummer(demo_obt):
    """Na DIP-fallback: geen enkel KZD/AMO-record heeft een leeg Inschrijvingvolgnummer.
    """
    detail = demo_obt["detail_kzd_amo"]
    assert detail["Inschrijvingvolgnummer"].null_count() == 0
    leeg = (detail["Inschrijvingvolgnummer"] == "").sum()
    assert leeg == 0


# ---------------------------------------------------------------------------
# GEO – dynamische pivot
# ---------------------------------------------------------------------------


def test_geo_kolommen_aanwezig(demo_obt):
    obt = demo_obt["obt_inschrijvingen"]
    geo_cols = [c for c in obt.columns if c.startswith("GEO_")]
    assert len(geo_cols) > 0


def test_geo_pivot_naam_formaat(demo_obt):
    """GEO-kolomnamen volgen het patroon GEO_{code}_{veld}."""
    obt = demo_obt["obt_inschrijvingen"]
    for col in obt.columns:
        if col.startswith("GEO_"):
            parts = col.split("_")
            assert len(parts) >= 3, f"Onverwacht GEO-kolomformaat: {col}"


# ---------------------------------------------------------------------------
# detail_bpv
# ---------------------------------------------------------------------------


def test_detail_bpv_niet_leeg(demo_obt):
    assert demo_obt["detail_bpv"].height > 0


def test_detail_bpv_heeft_persoon_id(demo_obt):
    assert "_persoon_id" in demo_obt["detail_bpv"].columns


def test_detail_bpv_geen_rijen_verloren(demo_obt, demo_stacked):
    assert demo_obt["detail_bpv"].height == demo_stacked["BPV"].height


# ---------------------------------------------------------------------------
# detail_kzd_amo
# ---------------------------------------------------------------------------


def test_detail_kzd_amo_heeft_bron_kolom(demo_obt):
    assert "_bron" in demo_obt["detail_kzd_amo"].columns


def test_detail_kzd_amo_bron_waarden(demo_obt):
    bronnen = set(demo_obt["detail_kzd_amo"]["_bron"].unique().to_list())
    assert bronnen <= {"KZD", "AMO"}


def test_detail_kzd_amo_alle_records(demo_obt, demo_stacked):
    amo = demo_stacked.get("AMO", pl.DataFrame())
    verwacht = demo_stacked["KZD"].height + amo.height
    assert demo_obt["detail_kzd_amo"].height == verwacht


# ---------------------------------------------------------------------------
# detail_bekostiging
# ---------------------------------------------------------------------------


def test_detail_bekostiging_bevat_bii_indien_aanwezig():
    """BII-records komen in detail_bekostiging als ze aanwezig zijn in stacked."""
    bii = pl.DataFrame({
        "levering": ["L1"],
        "Burgerservicenummer": ["P1"],
        "Inschrijvingvolgnummer": ["C1"],
        "Teldatum": ["2024-10-01"],
        "Recordsoort": ["BII"],
    })
    detail = _bouw_detail_bekostiging({"BII": bii})
    assert "BII" in detail["_bron"].unique().to_list()


def test_detail_bekostiging_bevat_tbgi(demo_obt):
    detail = demo_obt["detail_bekostiging"]
    assert "TBGI" in detail["_bron"].unique().to_list()


# ---------------------------------------------------------------------------
# meta_leveringen
# ---------------------------------------------------------------------------


def test_meta_leveringen_bevat_alle_leveringen(demo_obt, demo_stacked):
    leveringen_obt = set(demo_obt["meta_leveringen"]["levering"].unique().to_list())
    leveringen_stacked = set(demo_stacked["VLP"]["levering"].unique().to_list())
    assert leveringen_stacked <= leveringen_obt


# ---------------------------------------------------------------------------
# _resolve_inschrijving – unit
# ---------------------------------------------------------------------------


def test_resolve_inschrijving_vult_via_dip():
    """Lege Inschrijvingvolgnummer wordt via ResultaatvolgnummerDiploma → DIP gevuld."""
    kzd = pl.DataFrame({
        "levering": ["L1"],
        "_persoon_id": ["P1"],
        "Inschrijvingvolgnummer": [""],
        "ResultaatvolgnummerDiploma": ["REF1"],
    })
    dip = pl.DataFrame({
        "levering": ["L1"],
        "Burgerservicenummer": ["P1"],
        "Resultaatvolgnummer": ["REF1"],
        "Inschrijvingvolgnummer": ["C3"],
    })
    result = _resolve_inschrijving(kzd, dip)
    assert result["Inschrijvingvolgnummer"].to_list() == ["C3"]


def test_resolve_inschrijving_behoudt_ingevuld_volgnummer():
    """Al ingevuld Inschrijvingvolgnummer wordt niet overschreven."""
    kzd = pl.DataFrame({
        "levering": ["L1"],
        "_persoon_id": ["P1"],
        "Inschrijvingvolgnummer": ["A1"],
        "ResultaatvolgnummerDiploma": ["REF1"],
    })
    dip = pl.DataFrame({
        "levering": ["L1"],
        "Burgerservicenummer": ["P1"],
        "Resultaatvolgnummer": ["REF1"],
        "Inschrijvingvolgnummer": ["C9"],
    })
    result = _resolve_inschrijving(kzd, dip)
    assert result["Inschrijvingvolgnummer"].to_list() == ["A1"]


def test_resolve_inschrijving_zonder_dip():
    """Zonder DIP-tabel blijft de DataFrame ongewijzigd (geen crash)."""
    df = pl.DataFrame({
        "levering": ["L1"],
        "_persoon_id": ["P1"],
        "Inschrijvingvolgnummer": [""],
    })
    result = _resolve_inschrijving(df, None)
    assert result["Inschrijvingvolgnummer"].to_list() == [None]


def test_resolve_inschrijving_zonder_resultaatvolgnummer_kolom():
    """DataFrame zonder ResultaatvolgnummerDiploma wordt ongewijzigd teruggegeven."""
    df = pl.DataFrame({
        "levering": ["L1"],
        "_persoon_id": ["P1"],
        "Inschrijvingvolgnummer": ["A1"],
    })
    dip = pl.DataFrame({
        "levering": ["L1"],
        "Burgerservicenummer": ["P1"],
        "Resultaatvolgnummer": ["REF1"],
        "Inschrijvingvolgnummer": ["C9"],
    })
    result = _resolve_inschrijving(df, dip)
    assert result["Inschrijvingvolgnummer"].to_list() == ["A1"]
