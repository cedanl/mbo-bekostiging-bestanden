"""Tests voor obt.py (OBT-bouwfuncties)."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.obt import (
    _bouw_detail_bekostiging,
    _leid_studiejaar_af,
    _resolve_inschrijving,
    _voeg_afgeleide_velden_toe,
    _voeg_bekostigingsvlaggen_toe,
    _voeg_entree_vlaggen_toe,
    _voeg_sr_vlaggen_toe,
    _voeg_telling_en_jr_vlaggen_toe,
    _vul_niveau_aan,
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


# ---------------------------------------------------------------------------
# _voeg_bekostigingsvlaggen_toe – unit
# ---------------------------------------------------------------------------


def _obt_rij(**kwargs) -> pl.DataFrame:
    return pl.DataFrame({"Studiejaar": [2025], **kwargs})


def test_actief_1_oktober_true():
    obt = _obt_rij(
        DatumInschrijving=pl.Series([date(2025, 9, 1)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["J"],
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_actief_1_oktober"][0] is True


def test_actief_1_oktober_false_na_1okt_ingeschreven():
    obt = _obt_rij(
        DatumInschrijving=pl.Series([date(2025, 10, 15)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["J"],
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_actief_1_oktober"][0] is False


def test_actief_1_oktober_false_uitgeschreven_voor_1okt():
    obt = _obt_rij(
        DatumInschrijving=pl.Series([date(2025, 8, 15)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([date(2025, 9, 15)], dtype=pl.Date),
        IndicatieBekostigbaar=["J"],
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_actief_1_oktober"][0] is False


def test_actief_1_oktober_true_uitgeschreven_na_1okt():
    obt = _obt_rij(
        DatumInschrijving=pl.Series([date(2025, 8, 1)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([date(2025, 11, 1)], dtype=pl.Date),
        IndicatieBekostigbaar=["J"],
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_actief_1_oktober"][0] is True


def test_bekostigd_eerste_1okt_true():
    obt = _obt_rij(
        DatumInschrijving=pl.Series([date(2025, 9, 1)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["J"],
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_bekostigd_eerste_1okt"][0] is True


def test_bekostigd_eerste_1okt_false_niet_bekostigbaar():
    obt = _obt_rij(
        DatumInschrijving=pl.Series([date(2025, 9, 1)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["N"],
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_bekostigd_eerste_1okt"][0] is False


def test_bekostigd_eerste_1okt_false_niet_actief():
    obt = _obt_rij(
        DatumInschrijving=pl.Series([date(2025, 10, 15)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["J"],
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_bekostigd_eerste_1okt"][0] is False


def test_gediplomeerd_in_jaar_true():
    obt = _obt_rij(
        DIP_DatumResultaat=pl.Series([date(2025, 6, 15)], dtype=pl.Date),
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_gediplomeerd_in_jaar"][0] is True


def test_gediplomeerd_in_jaar_true_grenswaarden():
    obt = pl.DataFrame({
        "Studiejaar": [2025, 2025],
        "DIP_DatumResultaat": pl.Series(
            [date(2024, 8, 1), date(2025, 7, 31)], dtype=pl.Date
        ),
    })
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_gediplomeerd_in_jaar"].to_list() == [True, True]


def test_gediplomeerd_in_jaar_false_buiten_jaar():
    obt = _obt_rij(
        DIP_DatumResultaat=pl.Series([date(2025, 8, 1)], dtype=pl.Date),
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_gediplomeerd_in_jaar"][0] is False


def test_gediplomeerd_in_jaar_false_null_datum():
    obt = _obt_rij(
        DIP_DatumResultaat=pl.Series([None], dtype=pl.Date),
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_gediplomeerd_in_jaar"][0] is False


def test_gediplomeerd_in_jaar_false_kolom_ontbreekt():
    obt = _obt_rij()
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_gediplomeerd_in_jaar"][0] is False


def test_ingeschreven_jaar_later_true():
    obt = _obt_rij(
        DatumInschrijving=pl.Series([date(2025, 10, 15)], dtype=pl.Date),
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_ingeschreven_jaar_later"][0] is True


def test_ingeschreven_jaar_later_false():
    obt = _obt_rij(
        DatumInschrijving=pl.Series([date(2025, 9, 1)], dtype=pl.Date),
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_ingeschreven_jaar_later"][0] is False


def test_ingeschreven_jaar_later_false_op_1okt():
    obt = _obt_rij(
        DatumInschrijving=pl.Series([date(2025, 10, 1)], dtype=pl.Date),
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_ingeschreven_jaar_later"][0] is False


def test_ingeschreven_jaar_later_false_bij_null_datum():
    obt = _obt_rij(
        DatumInschrijving=pl.Series([None], dtype=pl.Date),
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_ingeschreven_jaar_later"][0] is False


def test_ontbrekend_studiejaar_geeft_none_vlaggen():
    obt = pl.DataFrame({"IndicatieBekostigbaar": ["J"]})
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_actief_1_oktober"][0] is None
    assert result["_bekostigd_eerste_1okt"][0] is None
    assert result["_ingeschreven_jaar_later"][0] is None


def test_ontbrekend_studiejaar_gediplomeerd_false():
    obt = pl.DataFrame({"IndicatieBekostigbaar": ["J"]})
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_gediplomeerd_in_jaar"][0] is False


def test_ontbrekende_datuminschrijving_geeft_none():
    obt = _obt_rij(IndicatieBekostigbaar=["J"])
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_actief_1_oktober"][0] is None
    assert result["_ingeschreven_jaar_later"][0] is None


# ---------------------------------------------------------------------------
# _voeg_bekostigingsvlaggen_toe – opbrengstjaar-logica
# ---------------------------------------------------------------------------


def test_opbrengstjaar_uitsplitsing_gelijk_aan_studiejaar():
    obt = _obt_rij()
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["Opbrengstjaar_uitsplitsing"][0] == 2025


def test_driejaars_teljaar_true_binnen_periode():
    obt = pl.DataFrame({"Studiejaar": [2023, 2024, 2025]})
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_driejaars_teljaar"].to_list() == [True, True, True]


def test_driejaars_teljaar_false_buiten_periode():
    obt = pl.DataFrame({"Studiejaar": [2021, 2022, 2023, 2024, 2025]})
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_driejaars_teljaar"].to_list() == [False, False, True, True, True]


def test_opbrengstjaar_3jaars_voortschrijdend_label():
    obt = pl.DataFrame({"Studiejaar": [2023, 2024, 2025]})
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["Opbrengstjaar_3jaars_voortschrijdend"][0] == "2023-2025"


def test_num_opbrengstjaar_3jr_rang():
    obt = pl.DataFrame({"Studiejaar": [2025, 2023, 2024]})
    result = _voeg_bekostigingsvlaggen_toe(obt)
    rang = dict(zip(
        result["Studiejaar"].to_list(),
        result["_num_opbrengstjaar_3jr"].to_list(),
        strict=True,
    ))
    assert rang[2023] == 1
    assert rang[2024] == 2
    assert rang[2025] == 3


def test_opbrengstjaar_ontbreekt_studiejaar_geeft_none():
    obt = pl.DataFrame({"IndicatieBekostigbaar": ["J"]})
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["Opbrengstjaar_uitsplitsing"][0] is None
    assert result["_driejaars_teljaar"][0] is None
    assert result["Opbrengstjaar_3jaars_voortschrijdend"][0] is None
    assert result["_num_opbrengstjaar_3jr"][0] is None


# ---------------------------------------------------------------------------
# _voeg_bekostigingsvlaggen_toe – _deelnemer_niet_bekostigd_eerste_1okt
# ---------------------------------------------------------------------------


def test_deelnemer_niet_bekostigd_eerste_1okt_true():
    obt = _obt_rij(
        DatumInschrijving=pl.Series([date(2025, 9, 1)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["N"],
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_deelnemer_niet_bekostigd_eerste_1okt"][0] is True


def test_deelnemer_niet_bekostigd_eerste_1okt_false_als_bekostigd():
    obt = _obt_rij(
        DatumInschrijving=pl.Series([date(2025, 9, 1)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["J"],
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_deelnemer_niet_bekostigd_eerste_1okt"][0] is False


def test_deelnemer_niet_bekostigd_eerste_1okt_false_niet_actief():
    obt = _obt_rij(
        DatumInschrijving=pl.Series([date(2025, 10, 15)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["N"],
    )
    result = _voeg_bekostigingsvlaggen_toe(obt)
    assert result["_deelnemer_niet_bekostigd_eerste_1okt"][0] is False


# ---------------------------------------------------------------------------
# _voeg_sr_vlaggen_toe – unit
# ---------------------------------------------------------------------------


def test_sr_hoogste_niveau():
    obt = pl.DataFrame({
        "_persoon_id": ["P1", "P1"],
        "Studiejaar": [2025, 2025],
        "Niveau": ["4", "3"],
        "Opleidingcode": ["A", "B"],
    })
    result = _voeg_sr_vlaggen_toe(obt)
    hoofd = dict(zip(
        result["Niveau"].to_list(),
        result["_hoogste_niveau"].to_list(),
        strict=True,
    ))
    assert hoofd["4"] is True
    assert hoofd["3"] is False


def test_sr_laagste_crebo():
    obt = pl.DataFrame({
        "_persoon_id": ["P1", "P1"],
        "Studiejaar": [2025, 2025],
        "Niveau": ["4", "4"],
        "Opleidingcode": ["A", "B"],
    })
    result = _voeg_sr_vlaggen_toe(obt)
    crebo = dict(zip(
        result["Opleidingcode"].to_list(),
        result["_laagste_CREBO"].to_list(),
        strict=True,
    ))
    assert crebo["A"] is True
    assert crebo["B"] is False


def test_sr_hoofdinschrijving_selecteert_juiste_rij():
    obt = pl.DataFrame({
        "_persoon_id": ["P1", "P1", "P2"],
        "Studiejaar": [2025, 2025, 2025],
        "Niveau": ["4", "3", "2"],
        "Opleidingcode": ["X", "Y", "Z"],
    })
    result = _voeg_sr_vlaggen_toe(obt)
    hoofd = result.filter(pl.col("_hoofdinschrijving")).to_dicts()
    assert len(hoofd) == 2
    p1 = [r for r in hoofd if r["_persoon_id"] == "P1"]
    assert len(p1) == 1
    assert p1[0]["Opleidingcode"] == "X"


def test_sr_hoofdinschrijving_gelijke_niveaus_kiest_laagste_crebo():
    obt = pl.DataFrame({
        "_persoon_id": ["P1", "P1"],
        "Studiejaar": [2025, 2025],
        "Niveau": ["4", "4"],
        "Opleidingcode": ["C002", "C001"],
    })
    result = _voeg_sr_vlaggen_toe(obt)
    hoofd = result.filter(pl.col("_hoofdinschrijving")).to_dicts()
    assert len(hoofd) == 1
    assert hoofd[0]["Opleidingcode"] == "C001"


def test_sr_vlaggen_ontbrekende_kolommen_geeft_none():
    obt = pl.DataFrame({"Studiejaar": [2025], "Niveau": ["4"]})
    result = _voeg_sr_vlaggen_toe(obt)
    assert result["_hoogste_niveau"][0] is None
    assert result["_laagste_CREBO"][0] is None
    assert result["_hoofdinschrijving"][0] is None


def test_sr_niveau_numeriek_mbo_prefix():
    """Niveau "MBO-4" moet hoger zijn dan "MBO-3" via numerieke extractie."""
    obt = pl.DataFrame({
        "_persoon_id": ["P1", "P1"],
        "Studiejaar": [2025, 2025],
        "Niveau": ["MBO-4", "MBO-3"],
        "Opleidingcode": ["A", "B"],
    })
    result = _voeg_sr_vlaggen_toe(obt)
    hoofd = dict(zip(
        result["Niveau"].to_list(),
        result["_hoogste_niveau"].to_list(),
        strict=True,
    ))
    assert hoofd["MBO-4"] is True
    assert hoofd["MBO-3"] is False


# ---------------------------------------------------------------------------
# _voeg_telling_en_jr_vlaggen_toe – unit
# ---------------------------------------------------------------------------


def test_telling_true_actief_en_hoofdinschrijving():
    obt = pl.DataFrame({
        "_actief_1_oktober": [True],
        "_hoofdinschrijving": [True],
        "_gediplomeerd_in_jaar": [False],
        "_ingeschreven_jaar_later": [True],
    })
    result = _voeg_telling_en_jr_vlaggen_toe(obt)
    assert result["_telling"][0] is True


def test_telling_false_niet_actief():
    obt = pl.DataFrame({
        "_actief_1_oktober": [False],
        "_hoofdinschrijving": [True],
        "_gediplomeerd_in_jaar": [False],
        "_ingeschreven_jaar_later": [False],
    })
    result = _voeg_telling_en_jr_vlaggen_toe(obt)
    assert result["_telling"][0] is False


def test_telling_false_niet_hoofdinschrijving():
    obt = pl.DataFrame({
        "_actief_1_oktober": [True],
        "_hoofdinschrijving": [False],
        "_gediplomeerd_in_jaar": [False],
        "_ingeschreven_jaar_later": [False],
    })
    result = _voeg_telling_en_jr_vlaggen_toe(obt)
    assert result["_telling"][0] is False


def test_telling_false_bij_null_actief():
    obt = pl.DataFrame({
        "_actief_1_oktober": pl.Series([None], dtype=pl.Boolean),
        "_hoofdinschrijving": [True],
        "_gediplomeerd_in_jaar": [False],
        "_ingeschreven_jaar_later": [False],
    })
    result = _voeg_telling_en_jr_vlaggen_toe(obt)
    assert result["_telling"][0] is False


def test_jr_noemer_gelijk_aan_telling():
    obt = pl.DataFrame({
        "_actief_1_oktober": [True],
        "_hoofdinschrijving": [True],
        "_gediplomeerd_in_jaar": [False],
        "_ingeschreven_jaar_later": [False],
    })
    result = _voeg_telling_en_jr_vlaggen_toe(obt)
    assert result["_jr_noemer"][0] == result["_telling"][0]


def test_jr_teller_true_gediplomeerd():
    obt = pl.DataFrame({
        "_actief_1_oktober": [True],
        "_hoofdinschrijving": [True],
        "_gediplomeerd_in_jaar": [True],
        "_ingeschreven_jaar_later": [False],
    })
    result = _voeg_telling_en_jr_vlaggen_toe(obt)
    assert result["_jr_teller"][0] is True


def test_jr_teller_true_ingeschreven_jaar_later():
    obt = pl.DataFrame({
        "_actief_1_oktober": [True],
        "_hoofdinschrijving": [True],
        "_gediplomeerd_in_jaar": [False],
        "_ingeschreven_jaar_later": [True],
    })
    result = _voeg_telling_en_jr_vlaggen_toe(obt)
    assert result["_jr_teller"][0] is True


def test_jr_teller_false_niet_in_noemer():
    obt = pl.DataFrame({
        "_actief_1_oktober": [False],
        "_hoofdinschrijving": [True],
        "_gediplomeerd_in_jaar": [True],
        "_ingeschreven_jaar_later": [True],
    })
    result = _voeg_telling_en_jr_vlaggen_toe(obt)
    assert result["_jr_teller"][0] is False


def test_jr_teller_false_geen_resultaat():
    obt = pl.DataFrame({
        "_actief_1_oktober": [True],
        "_hoofdinschrijving": [True],
        "_gediplomeerd_in_jaar": [False],
        "_ingeschreven_jaar_later": [False],
    })
    result = _voeg_telling_en_jr_vlaggen_toe(obt)
    assert result["_jr_teller"][0] is False


# ---------------------------------------------------------------------------
# IndicatieBekostigbaar normalisatie (decode-fase)
# ---------------------------------------------------------------------------


def test_indicatie_bekostigbaar_normalisatie_in_obt(demo_obt):
    """Na decode-normalisatie bevat de OBT alleen 'J' of 'N' (of null)."""
    obt = demo_obt["obt_inschrijvingen"]
    if "IndicatieBekostigbaar" in obt.columns:
        waarden = set(
            obt["IndicatieBekostigbaar"].drop_nulls().unique().to_list()
        )
        assert waarden <= {"J", "N"}, (
            f"Onverwachte waarden: {waarden}"
        )


# ---------------------------------------------------------------------------
# _voeg_entree_vlaggen_toe – unit
# ---------------------------------------------------------------------------


def test_entree_uitstroom_true_mbo1_uitgeschreven():
    obt = pl.DataFrame({
        "_persoon_id": ["P1"],
        "Niveau": ["MBO-1"],
        "DatumUitschrijvingWerkelijk": pl.Series(
            [date(2025, 6, 1)], dtype=pl.Date
        ),
        "DatumUitschrijvingGepland": pl.Series(
            [date(2025, 7, 31)], dtype=pl.Date
        ),
    })
    result = _voeg_entree_vlaggen_toe(obt)
    assert result["_entree_uitstroom"][0] is True


def test_entree_uitstroom_false_mbo4():
    obt = pl.DataFrame({
        "_persoon_id": ["P1"],
        "Niveau": ["MBO-4"],
        "DatumUitschrijvingWerkelijk": pl.Series(
            [date(2025, 6, 1)], dtype=pl.Date
        ),
        "DatumUitschrijvingGepland": pl.Series(
            [date(2025, 7, 31)], dtype=pl.Date
        ),
    })
    result = _voeg_entree_vlaggen_toe(obt)
    assert result["_entree_uitstroom"][0] is False


def test_entree_uitstroom_false_niet_uitgeschreven():
    obt = pl.DataFrame({
        "_persoon_id": ["P1"],
        "Niveau": ["MBO-1"],
        "DatumUitschrijvingWerkelijk": pl.Series(
            [None], dtype=pl.Date
        ),
        "DatumUitschrijvingGepland": pl.Series(
            [date(2025, 7, 31)], dtype=pl.Date
        ),
    })
    result = _voeg_entree_vlaggen_toe(obt)
    assert result["_entree_uitstroom"][0] is False


def test_entree_doorstroom_true():
    """MBO-1 student met ook een MBO-4 inschrijving bij dezelfde instelling."""
    obt = pl.DataFrame({
        "_persoon_id": ["P1", "P1"],
        "BRIN": ["01AA", "01AA"],
        "Niveau": ["MBO-1", "MBO-4"],
        "DatumUitschrijvingWerkelijk": pl.Series(
            [date(2025, 6, 1), None], dtype=pl.Date
        ),
        "DatumUitschrijvingGepland": pl.Series(
            [date(2025, 7, 31), date(2026, 7, 31)], dtype=pl.Date
        ),
    })
    result = _voeg_entree_vlaggen_toe(obt)
    doorstroom = dict(zip(
        result["Niveau"].to_list(),
        result["_entree_doorstroom"].to_list(),
        strict=True,
    ))
    assert doorstroom["MBO-1"] is True
    assert doorstroom["MBO-4"] is False


def test_entree_doorstroom_false_andere_instelling():
    """MBO-1 bij instelling A, MBO-4 bij instelling B → geen doorstroom."""
    obt = pl.DataFrame({
        "_persoon_id": ["P1", "P1"],
        "BRIN": ["01AA", "02BB"],
        "Niveau": ["MBO-1", "MBO-4"],
        "DatumUitschrijvingWerkelijk": pl.Series(
            [date(2025, 6, 1), None], dtype=pl.Date
        ),
        "DatumUitschrijvingGepland": pl.Series(
            [date(2025, 7, 31), date(2026, 7, 31)], dtype=pl.Date
        ),
    })
    result = _voeg_entree_vlaggen_toe(obt)
    doorstroom = dict(zip(
        result["Niveau"].to_list(),
        result["_entree_doorstroom"].to_list(),
        strict=True,
    ))
    assert doorstroom["MBO-1"] is False


def test_entree_doorstroom_false_geen_vervolg():
    """MBO-1 student zonder hoger niveau → geen doorstroom."""
    obt = pl.DataFrame({
        "_persoon_id": ["P1"],
        "BRIN": ["01AA"],
        "Niveau": ["MBO-1"],
        "DatumUitschrijvingWerkelijk": pl.Series(
            [date(2025, 6, 1)], dtype=pl.Date
        ),
        "DatumUitschrijvingGepland": pl.Series(
            [date(2025, 7, 31)], dtype=pl.Date
        ),
    })
    result = _voeg_entree_vlaggen_toe(obt)
    assert result["_entree_doorstroom"][0] is False


def test_entree_vlaggen_ontbrekende_kolommen():
    obt = pl.DataFrame({"Studiejaar": [2025]})
    result = _voeg_entree_vlaggen_toe(obt)
    assert result["_entree_uitstroom"][0] is None
    assert result["_entree_doorstroom"][0] is None


# ---------------------------------------------------------------------------
# _voeg_afgeleide_velden_toe – unit
# ---------------------------------------------------------------------------


def test_niveau_gecombineerd():
    obt = pl.DataFrame({
        "_persoon_id": ["P1"],
        "Inschrijvingvolgnummer": ["1"],
        "Niveau": ["MBO-4"],
        "Leertraject": ["BOL"],
    })
    result = _voeg_afgeleide_velden_toe(obt)
    assert result["Niveau_gecombineerd"][0] == "MBO-4 BOL"


def test_niveau_gecombineerd_null_leertraject():
    obt = pl.DataFrame({
        "_persoon_id": ["P1"],
        "Inschrijvingvolgnummer": ["1"],
        "Niveau": ["MBO-4"],
        "Leertraject": pl.Series([None], dtype=pl.Utf8),
    })
    result = _voeg_afgeleide_velden_toe(obt)
    assert result["Niveau_gecombineerd"][0] is None


def test_tellingen_aanwezig():
    obt = pl.DataFrame({
        "_persoon_id": ["P1", "P1", "P2"],
        "Inschrijvingvolgnummer": ["1", "1", "1"],
        "levering": ["L1", "L2", "L1"],
    })
    result = _voeg_afgeleide_velden_toe(obt)
    p1 = result.filter(pl.col("_persoon_id") == "P1")
    assert p1["_tellingen_aanwezig"][0] == 2
    p2 = result.filter(pl.col("_persoon_id") == "P2")
    assert p2["_tellingen_aanwezig"][0] == 1


def test_afgeleide_velden_in_demo_obt(demo_obt):
    """Afgeleide velden zijn aanwezig in de OBT."""
    obt = demo_obt["obt_inschrijvingen"]
    assert "Niveau_gecombineerd" in obt.columns
    assert "_tellingen_aanwezig" in obt.columns


# ---------------------------------------------------------------------------
# Niveau aanvullen vanuit CREBO
# ---------------------------------------------------------------------------


def test_vul_niveau_aan_vanuit_crebo():
    """Null Niveau wordt aangevuld via Opleidingcode → CREBO-tabel."""
    df = pl.DataFrame({
        "Opleidingcode": ["25655", "23301"],
        "Niveau": [None, "MBO-1"],
    })
    result = _vul_niveau_aan(df)
    assert result["Niveau"][0] == "MBO-4"
    assert result["Niveau"][1] == "MBO-1"


def test_vul_niveau_aan_behoudt_bestaand():
    """Bestaand Niveau wordt niet overschreven door CREBO."""
    df = pl.DataFrame({
        "Opleidingcode": ["25655"],
        "Niveau": ["MBO-3"],
    })
    result = _vul_niveau_aan(df)
    assert result["Niveau"][0] == "MBO-3"


def test_vul_niveau_aan_onbekende_code():
    """Onbekende Opleidingcode laat Niveau op null."""
    df = pl.DataFrame({
        "Opleidingcode": ["99999"],
        "Niveau": [None],
    })
    result = _vul_niveau_aan(df)
    assert result["Niveau"][0] is None


def test_vul_niveau_in_demo_obt(demo_obt):
    """Na Niveau-aanvulling hebben de meeste rijen een Niveau."""
    obt = demo_obt["obt_inschrijvingen"]
    filled = obt["Niveau"].drop_nulls().len()
    assert filled > 2


# ---------------------------------------------------------------------------
# Studiejaar afleiding
# ---------------------------------------------------------------------------


def test_studiejaar_afgeleid_uit_datumbegin_augustus():
    """DatumBegin in augustus → studiejaar = jaar van DatumBegin."""
    obt = pl.DataFrame({
        "DatumBegin": pl.Series([date(2025, 8, 1)], dtype=pl.Date),
    })
    result = _leid_studiejaar_af(obt)
    assert result["Studiejaar"][0] == 2025


def test_studiejaar_afgeleid_uit_datumbegin_januari():
    """DatumBegin in januari → studiejaar = jaar - 1."""
    obt = pl.DataFrame({
        "DatumBegin": pl.Series([date(2026, 1, 15)], dtype=pl.Date),
    })
    result = _leid_studiejaar_af(obt)
    assert result["Studiejaar"][0] == 2025


def test_studiejaar_afgeleid_uit_datumbegin_juli():
    """DatumBegin in juli → studiejaar = jaar - 1 (nog vorig studiejaar)."""
    obt = pl.DataFrame({
        "DatumBegin": pl.Series([date(2026, 7, 31)], dtype=pl.Date),
    })
    result = _leid_studiejaar_af(obt)
    assert result["Studiejaar"][0] == 2025


def test_studiejaar_behoudt_bestaande_waarde():
    """Bestaand Studiejaar wordt niet overschreven."""
    obt = pl.DataFrame({
        "DatumBegin": pl.Series([date(2025, 9, 1)], dtype=pl.Date),
        "Studiejaar": pl.Series([2024], dtype=pl.Int64),
    })
    result = _leid_studiejaar_af(obt)
    assert result["Studiejaar"][0] == 2024


def test_studiejaar_vult_null_aan():
    """Null Studiejaar wordt aangevuld, bestaande waarden blijven."""
    obt = pl.DataFrame({
        "DatumBegin": pl.Series([date(2025, 9, 1), date(2024, 10, 1)], dtype=pl.Date),
        "Studiejaar": pl.Series([None, 2024], dtype=pl.Int64),
    })
    result = _leid_studiejaar_af(obt)
    assert result["Studiejaar"].to_list() == [2025, 2024]


def test_studiejaar_uit_datuminschrijving():
    """Zonder DatumBegin wordt DatumInschrijving gebruikt (TBGI-pad)."""
    obt = pl.DataFrame({
        "DatumInschrijving": pl.Series([date(2024, 2, 1)], dtype=pl.Date),
    })
    result = _leid_studiejaar_af(obt)
    assert result["Studiejaar"][0] == 2023


def test_studiejaar_geen_datum_geen_crash():
    """Zonder datumvelden en zonder Studiejaar → geen crash, geen kolom."""
    obt = pl.DataFrame({"_persoon_id": ["P1"]})
    result = _leid_studiejaar_af(obt)
    assert "Studiejaar" not in result.columns


def test_studiejaar_afgeleid_in_demo_obt(demo_obt):
    """Na afleiding heeft elke rij een Studiejaar (geen nulls meer)."""
    obt = demo_obt["obt_inschrijvingen"]
    assert obt["Studiejaar"].null_count() == 0
