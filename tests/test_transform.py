"""Tests voor transform.py (analysetabel-bouwfuncties)."""

from datetime import date

import polars as pl
import pytest

from mbo_bekostiging_bestanden.transform import (
    _add_persoon_id,
    _bouw_analysetabellen,
    _bouw_detail_bekostiging,
    _bouw_detail_bekostiging_diploma,
    _leid_studiejaar_af,
    _resolve_inschrijving,
    _voeg_afgeleide_velden_toe,
    _voeg_bekostigingsvlaggen_toe,
    _voeg_entree_vlaggen_toe,
    _voeg_sr_vlaggen_toe,
    _voeg_telling_en_jr_vlaggen_toe,
    _vul_niveau_aan,
    pseudoniem,
)

# ---------------------------------------------------------------------------
# _bouw_analysetabellen – input-validatie
# ---------------------------------------------------------------------------


def test_bouw_analysetabellen_raises_without_isp_and_inschrijving():
    with pytest.raises(ValueError, match="ISP"):
        _bouw_analysetabellen({"PER": pl.DataFrame()})


def test_bouw_analysetabellen_raises_with_leeg_isp_en_geen_inschrijving():
    with pytest.raises(ValueError, match="ISP"):
        _bouw_analysetabellen({"ISP": pl.DataFrame()})


def test_bouw_analysetabellen_tbgi_fallback_gebruikt_inschrijving_als_grain():
    """Zonder ISP maar met TBGI Inschrijving → inschrijvingen gevuld."""
    inschrijving = pl.DataFrame(
        {
            "levering": ["L1"],
            "BRIN": ["25LX"],
            "Burgerservicenummer": ["BSN1"],
            "Onderwijsnummer": [None],
            "Inschrijvingvolgnummer": ["001"],
        }
    )
    result = _bouw_analysetabellen({"Inschrijving": inschrijving})
    assert result["inschrijvingen"].height == 1
    assert "_persoon_id" in result["inschrijvingen"].columns
    # Ook zonder begindatum een sleutel (#109): de inschrijving is de periode.
    assert result["inschrijvingen"]["_inschrijving_periode_id"].null_count() == 0


def test_bouw_analysetabellen_tbgi_fallback_detail_bekostiging_gevuld():
    """Teldatum verschijnt in detail_bekostiging ook als ISP ontbreekt."""
    inschrijving = pl.DataFrame(
        {
            "levering": ["L1"],
            "BRIN": ["25LX"],
            "Burgerservicenummer": ["BSN1"],
            "Onderwijsnummer": [None],
            "Inschrijvingvolgnummer": ["001"],
        }
    )
    teldatum = pl.DataFrame(
        {
            "levering": ["L1"],
            "BRIN": ["25LX"],
            "Inschrijvingvolgnummer": ["001"],
            "Teldatum": ["2025-10-01"],
            "Bekostigingsstatus": ["A"],
        }
    )
    result = _bouw_analysetabellen({"Inschrijving": inschrijving, "Teldatum": teldatum})
    detail = result["detail_bekostiging"]
    assert detail.height == 1
    assert "TBGI" in detail["_bron"].to_list()


# ---------------------------------------------------------------------------
# _bouw_analysetabellen – output-structuur
# ---------------------------------------------------------------------------


def test_bouw_analysetabellen_returns_zeven_tables(demo_tabellen):
    assert set(demo_tabellen.keys()) == {
        "inschrijvingen",
        "detail_bpv",
        "detail_kzd_amo",
        "detail_bekostiging",
        "detail_bekostiging_diploma",
        "detail_geo",
        "meta_leveringen",
    }


def test_inschrijvingen_grain_isp(demo_tabellen, demo_stacked):
    """inschrijvingen behoudt exact het aantal ISP-rijen."""
    assert demo_tabellen["inschrijvingen"].height == demo_stacked["ISP"].height


def test_inschrijvingen_heeft_persoon_id(demo_tabellen):
    assert "_persoon_id" in demo_tabellen["inschrijvingen"].columns


# ---------------------------------------------------------------------------
# KZD/AMO – DIP-fallback voor Inschrijvingvolgnummer
# ---------------------------------------------------------------------------


def test_kzd_aantal_bsn1_ingevuld(demo_tabellen):
    """BSN1 heeft 2 KZD-records; na DIP-fallback is KZD_Aantal=2 (niet null)."""
    df = demo_tabellen["inschrijvingen"]
    bsn1_pseudoniem = pseudoniem("PGN", "BSN1")
    bsn1 = df.filter(
        (pl.col("_persoon_id") == bsn1_pseudoniem)
        & (pl.col("levering") == "h17/GRONDSLAG_IP_MBO_27DV_20251119_2025")
    )
    assert bsn1.height >= 1
    assert bsn1["KZD_Aantal"].to_list()[0] == 2


def test_kzd_behaald_bsn1_ingevuld(demo_tabellen):
    df = demo_tabellen["inschrijvingen"]
    bsn1_pseudoniem = pseudoniem("PGN", "BSN1")
    bsn1 = df.filter(
        (pl.col("_persoon_id") == bsn1_pseudoniem)
        & (pl.col("levering") == "h17/GRONDSLAG_IP_MBO_27DV_20251119_2025")
    )
    assert bsn1["KZD_AantalBehaald"].to_list()[0] == 2


def test_detail_kzd_amo_geen_lege_inschrijvingvolgnummer(demo_tabellen):
    """Na DIP-fallback: geen enkel KZD/AMO-record heeft een leeg
    Inschrijvingvolgnummer.
    """
    detail = demo_tabellen["detail_kzd_amo"]
    assert detail["Inschrijvingvolgnummer"].null_count() == 0
    leeg = (detail["Inschrijvingvolgnummer"] == "").sum()
    assert leeg == 0


# ---------------------------------------------------------------------------
# GEO – dynamische pivot
# ---------------------------------------------------------------------------


def test_geo_kolommen_aanwezig(demo_tabellen):
    df = demo_tabellen["inschrijvingen"]
    geo_cols = [c for c in df.columns if c.startswith("GEO_")]
    assert len(geo_cols) > 0


def test_geo_pivot_naam_formaat(demo_tabellen):
    """GEO-kolomnamen volgen het patroon GEO_{code}_{veld}."""
    df = demo_tabellen["inschrijvingen"]
    for col in df.columns:
        if col.startswith("GEO_"):
            parts = col.split("_")
            assert len(parts) >= 3, f"Onverwacht GEO-kolomformaat: {col}"


# ---------------------------------------------------------------------------
# detail_bpv
# ---------------------------------------------------------------------------


def test_detail_bpv_niet_leeg(demo_tabellen):
    assert demo_tabellen["detail_bpv"].height > 0


def test_detail_bpv_heeft_persoon_id(demo_tabellen):
    assert "_persoon_id" in demo_tabellen["detail_bpv"].columns


def test_detail_bpv_geen_rijen_verloren(demo_tabellen, demo_stacked):
    assert demo_tabellen["detail_bpv"].height == demo_stacked["BPV"].height


# ---------------------------------------------------------------------------
# detail_kzd_amo
# ---------------------------------------------------------------------------


def test_detail_kzd_amo_bron_waarden(demo_tabellen):
    bronnen = set(demo_tabellen["detail_kzd_amo"]["_bron"].unique().to_list())
    assert bronnen <= {"KZD", "AMO"}


def test_detail_kzd_amo_alle_records(demo_tabellen, demo_stacked):
    amo = demo_stacked.get("AMO", pl.DataFrame())
    verwacht = demo_stacked["KZD"].height + amo.height
    assert demo_tabellen["detail_kzd_amo"].height == verwacht


# ---------------------------------------------------------------------------
# detail_bekostiging
# ---------------------------------------------------------------------------


def test_detail_bekostiging_bevat_bii_indien_aanwezig():
    """BII-records komen in detail_bekostiging als ze aanwezig zijn in stacked."""
    bii = pl.DataFrame(
        {
            "levering": ["L1"],
            "Burgerservicenummer": ["P1"],
            "Inschrijvingvolgnummer": ["C1"],
            "Teldatum": ["2024-10-01"],
            "Recordsoort": ["BII"],
        }
    )
    detail = _bouw_detail_bekostiging({"BII": bii})
    assert "BII" in detail["_bron"].unique().to_list()


def test_detail_bekostiging_bevat_tbgi(demo_tabellen):
    detail = demo_tabellen["detail_bekostiging"]
    assert "TBGI" in detail["_bron"].unique().to_list()


# ---------------------------------------------------------------------------
# detail_bekostiging_diploma
# ---------------------------------------------------------------------------


def test_detail_bekostiging_diploma_leeg_zonder_diploma():
    """Zonder Diploma-sleutel geeft de functie een leeg DataFrame."""
    assert _bouw_detail_bekostiging_diploma({}).is_empty()


def test_detail_bekostiging_diploma_persoon_id_aanwezig():
    """_persoon_id gepseudonimiseerd van Burgerservicenummer; BSN verwijderd."""
    dip = pl.DataFrame(
        {
            "levering": ["L1"],
            "BRIN": ["25LX"],
            "Burgerservicenummer": ["900000001"],
            "Inschrijvingvolgnummer": ["001"],
            "Resultaatvolgnummer": ["1362433"],
            "BijdrageDiplomawaarde": ["5"],
            "Bekostigingsstatus": ["true"],
        }
    )
    result = _bouw_detail_bekostiging_diploma({"Diploma": dip})
    assert "_persoon_id" in result.columns
    assert "Burgerservicenummer" not in result.columns
    expected_pseudoniem = pseudoniem("BSN", "900000001")
    assert result["_persoon_id"][0] == expected_pseudoniem
    assert result["BijdrageDiplomawaarde"][0] == "5"


def test_detail_bekostiging_diploma_in_demo_tabellen(demo_tabellen):
    """Demo TBGI levert één Diploma-rij op in detail_bekostiging_diploma."""
    detail = demo_tabellen["detail_bekostiging_diploma"]
    assert not detail.is_empty()
    assert "BijdrageDiplomawaarde" in detail.columns
    assert "Burgerservicenummer" not in detail.columns


# ---------------------------------------------------------------------------
# meta_leveringen
# ---------------------------------------------------------------------------


def test_meta_leveringen_bevat_alle_leveringen(demo_tabellen, demo_stacked):
    leveringen = set(demo_tabellen["meta_leveringen"]["levering"].unique().to_list())
    leveringen_stacked = set(demo_stacked["VLP"]["levering"].unique().to_list())
    assert leveringen_stacked <= leveringen


# ---------------------------------------------------------------------------
# _resolve_inschrijving – unit
# ---------------------------------------------------------------------------


def test_resolve_inschrijving_vult_via_dip():
    """Lege Inschrijvingvolgnummer wordt via ResultaatvolgnummerDiploma → DIP gevuld."""
    p1_pseudoniem = pseudoniem("BSN", "P1")
    kzd = pl.DataFrame(
        {
            "levering": ["L1"],
            "_persoon_id": [p1_pseudoniem],
            "Inschrijvingvolgnummer": [""],
            "ResultaatvolgnummerDiploma": ["REF1"],
        }
    )
    dip = pl.DataFrame(
        {
            "levering": ["L1"],
            "Burgerservicenummer": ["P1"],
            "Resultaatvolgnummer": ["REF1"],
            "Inschrijvingvolgnummer": ["C3"],
        }
    )
    result = _resolve_inschrijving(kzd, dip)
    assert result["Inschrijvingvolgnummer"].to_list() == ["C3"]


def test_resolve_inschrijving_behoudt_ingevuld_volgnummer():
    """Al ingevuld Inschrijvingvolgnummer wordt niet overschreven."""
    kzd = pl.DataFrame(
        {
            "levering": ["L1"],
            "_persoon_id": ["P1"],
            "Inschrijvingvolgnummer": ["A1"],
            "ResultaatvolgnummerDiploma": ["REF1"],
        }
    )
    dip = pl.DataFrame(
        {
            "levering": ["L1"],
            "Burgerservicenummer": ["P1"],
            "Resultaatvolgnummer": ["REF1"],
            "Inschrijvingvolgnummer": ["C9"],
        }
    )
    result = _resolve_inschrijving(kzd, dip)
    assert result["Inschrijvingvolgnummer"].to_list() == ["A1"]


def test_resolve_inschrijving_zonder_dip():
    """Zonder DIP-tabel blijft de DataFrame ongewijzigd (geen crash)."""
    df = pl.DataFrame(
        {
            "levering": ["L1"],
            "_persoon_id": ["P1"],
            "Inschrijvingvolgnummer": [""],
        }
    )
    result = _resolve_inschrijving(df, None)
    assert result["Inschrijvingvolgnummer"].to_list() == [None]


def test_resolve_inschrijving_zonder_resultaatvolgnummer_kolom():
    """DataFrame zonder ResultaatvolgnummerDiploma wordt ongewijzigd teruggegeven."""
    df = pl.DataFrame(
        {
            "levering": ["L1"],
            "_persoon_id": ["P1"],
            "Inschrijvingvolgnummer": ["A1"],
        }
    )
    dip = pl.DataFrame(
        {
            "levering": ["L1"],
            "Burgerservicenummer": ["P1"],
            "Resultaatvolgnummer": ["REF1"],
            "Inschrijvingvolgnummer": ["C9"],
        }
    )
    result = _resolve_inschrijving(df, dip)
    assert result["Inschrijvingvolgnummer"].to_list() == ["A1"]


# ---------------------------------------------------------------------------
# _voeg_bekostigingsvlaggen_toe – unit
# ---------------------------------------------------------------------------


def _rij(**kwargs) -> pl.DataFrame:
    return pl.DataFrame({"Studiejaar": [2025], **kwargs})


def test_actief_1_oktober_true():
    df = _rij(
        DatumInschrijving=pl.Series([date(2025, 9, 1)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["J"],
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_actief_1_oktober"][0] is True


def test_actief_1_oktober_false_na_1okt_ingeschreven():
    df = _rij(
        DatumInschrijving=pl.Series([date(2025, 10, 15)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["J"],
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_actief_1_oktober"][0] is False


def test_actief_1_oktober_false_uitgeschreven_voor_1okt():
    df = _rij(
        DatumInschrijving=pl.Series([date(2025, 8, 15)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([date(2025, 9, 15)], dtype=pl.Date),
        IndicatieBekostigbaar=["J"],
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_actief_1_oktober"][0] is False


def test_actief_1_oktober_true_uitgeschreven_na_1okt():
    df = _rij(
        DatumInschrijving=pl.Series([date(2025, 8, 1)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([date(2025, 11, 1)], dtype=pl.Date),
        IndicatieBekostigbaar=["J"],
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_actief_1_oktober"][0] is True


def test_bekostigd_eerste_1okt_true():
    df = _rij(
        DatumInschrijving=pl.Series([date(2025, 9, 1)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["J"],
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_bekostigd_eerste_1okt"][0] is True


def test_bekostigd_eerste_1okt_false_niet_bekostigbaar():
    df = _rij(
        DatumInschrijving=pl.Series([date(2025, 9, 1)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["N"],
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_bekostigd_eerste_1okt"][0] is False


def test_bekostigd_eerste_1okt_false_niet_actief():
    df = _rij(
        DatumInschrijving=pl.Series([date(2025, 10, 15)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["J"],
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_bekostigd_eerste_1okt"][0] is False


def test_gediplomeerd_in_jaar_true():
    df = _rij(
        DIP_DatumResultaat=pl.Series([date(2025, 6, 15)], dtype=pl.Date),
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_gediplomeerd_in_jaar"][0] is True


def test_gediplomeerd_in_jaar_true_grenswaarden():
    df = pl.DataFrame(
        {
            "Studiejaar": [2025, 2025],
            "DIP_DatumResultaat": pl.Series(
                [date(2024, 8, 1), date(2025, 7, 31)], dtype=pl.Date
            ),
        }
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_gediplomeerd_in_jaar"].to_list() == [True, True]


def test_gediplomeerd_in_jaar_false_buiten_jaar():
    df = _rij(
        DIP_DatumResultaat=pl.Series([date(2025, 8, 1)], dtype=pl.Date),
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_gediplomeerd_in_jaar"][0] is False


def test_gediplomeerd_in_jaar_false_null_datum():
    df = _rij(
        DIP_DatumResultaat=pl.Series([None], dtype=pl.Date),
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_gediplomeerd_in_jaar"][0] is False


def test_gediplomeerd_in_jaar_false_kolom_ontbreekt():
    df = _rij()
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_gediplomeerd_in_jaar"][0] is False


def test_ingeschreven_jaar_later_true():
    df = _rij(
        DatumInschrijving=pl.Series([date(2025, 10, 15)], dtype=pl.Date),
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_ingeschreven_jaar_later"][0] is True


def test_ingeschreven_jaar_later_false():
    df = _rij(
        DatumInschrijving=pl.Series([date(2025, 9, 1)], dtype=pl.Date),
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_ingeschreven_jaar_later"][0] is False


def test_ingeschreven_jaar_later_false_op_1okt():
    df = _rij(
        DatumInschrijving=pl.Series([date(2025, 10, 1)], dtype=pl.Date),
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_ingeschreven_jaar_later"][0] is False


def test_ingeschreven_jaar_later_false_bij_null_datum():
    df = _rij(
        DatumInschrijving=pl.Series([None], dtype=pl.Date),
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_ingeschreven_jaar_later"][0] is False


def test_ontbrekend_studiejaar_geeft_none_vlaggen():
    df = pl.DataFrame({"IndicatieBekostigbaar": ["J"]})
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_actief_1_oktober"][0] is None
    assert result["_bekostigd_eerste_1okt"][0] is None
    assert result["_ingeschreven_jaar_later"][0] is None


def test_ontbrekend_studiejaar_gediplomeerd_false():
    df = pl.DataFrame({"IndicatieBekostigbaar": ["J"]})
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_gediplomeerd_in_jaar"][0] is False


def test_ontbrekende_datuminschrijving_geeft_none():
    df = _rij(IndicatieBekostigbaar=["J"])
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_actief_1_oktober"][0] is None
    assert result["_ingeschreven_jaar_later"][0] is None


# ---------------------------------------------------------------------------
# _voeg_bekostigingsvlaggen_toe – opbrengstjaar-logica
# ---------------------------------------------------------------------------


def test_opbrengstjaar_uitsplitsing_gelijk_aan_studiejaar():
    df = _rij()
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["Opbrengstjaar_uitsplitsing"][0] == 2025


def test_driejaars_teljaar_true_binnen_periode():
    df = pl.DataFrame({"Studiejaar": [2023, 2024, 2025]})
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_driejaars_teljaar"].to_list() == [True, True, True]


def test_driejaars_teljaar_false_buiten_periode():
    df = pl.DataFrame({"Studiejaar": [2021, 2022, 2023, 2024, 2025]})
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_driejaars_teljaar"].to_list() == [False, False, True, True, True]


def test_opbrengstjaar_3jaars_voortschrijdend_label():
    df = pl.DataFrame({"Studiejaar": [2023, 2024, 2025]})
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["Opbrengstjaar_3jaars_voortschrijdend"][0] == "2023-2025"


def test_num_opbrengstjaar_3jr_rang():
    df = pl.DataFrame({"Studiejaar": [2025, 2023, 2024]})
    result = _voeg_bekostigingsvlaggen_toe(df)
    rang = dict(
        zip(
            result["Studiejaar"].to_list(),
            result["_num_opbrengstjaar_3jr"].to_list(),
            strict=True,
        )
    )
    assert rang[2023] == 1
    assert rang[2024] == 2
    assert rang[2025] == 3


def test_opbrengstjaar_ontbreekt_studiejaar_geeft_none():
    df = pl.DataFrame({"IndicatieBekostigbaar": ["J"]})
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["Opbrengstjaar_uitsplitsing"][0] is None
    assert result["_driejaars_teljaar"][0] is None
    assert result["Opbrengstjaar_3jaars_voortschrijdend"][0] is None
    assert result["_num_opbrengstjaar_3jr"][0] is None


# ---------------------------------------------------------------------------
# _voeg_bekostigingsvlaggen_toe – _deelnemer_niet_bekostigd_eerste_1okt
# ---------------------------------------------------------------------------


def test_deelnemer_niet_bekostigd_eerste_1okt_true():
    df = _rij(
        DatumInschrijving=pl.Series([date(2025, 9, 1)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["N"],
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_deelnemer_niet_bekostigd_eerste_1okt"][0] is True


def test_deelnemer_niet_bekostigd_eerste_1okt_false_als_bekostigd():
    df = _rij(
        DatumInschrijving=pl.Series([date(2025, 9, 1)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["J"],
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_deelnemer_niet_bekostigd_eerste_1okt"][0] is False


def test_deelnemer_niet_bekostigd_eerste_1okt_false_niet_actief():
    df = _rij(
        DatumInschrijving=pl.Series([date(2025, 10, 15)], dtype=pl.Date),
        DatumUitschrijvingWerkelijk=pl.Series([None], dtype=pl.Date),
        IndicatieBekostigbaar=["N"],
    )
    result = _voeg_bekostigingsvlaggen_toe(df)
    assert result["_deelnemer_niet_bekostigd_eerste_1okt"][0] is False


# ---------------------------------------------------------------------------
# _voeg_sr_vlaggen_toe – unit
# ---------------------------------------------------------------------------


def test_sr_hoogste_niveau():
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1", "P1"],
            "Studiejaar": [2025, 2025],
            "Niveau": ["4", "3"],
            "Opleidingcode": ["A", "B"],
        }
    )
    result = _voeg_sr_vlaggen_toe(df)
    hoofd = dict(
        zip(
            result["Niveau"].to_list(),
            result["_hoogste_niveau"].to_list(),
            strict=True,
        )
    )
    assert hoofd["4"] is True
    assert hoofd["3"] is False


def test_sr_laagste_crebo():
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1", "P1"],
            "Studiejaar": [2025, 2025],
            "Niveau": ["4", "4"],
            "Opleidingcode": ["A", "B"],
        }
    )
    result = _voeg_sr_vlaggen_toe(df)
    crebo = dict(
        zip(
            result["Opleidingcode"].to_list(),
            result["_laagste_CREBO"].to_list(),
            strict=True,
        )
    )
    assert crebo["A"] is True
    assert crebo["B"] is False


def test_sr_hoofdinschrijving_selecteert_juiste_rij():
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1", "P1", "P2"],
            "Studiejaar": [2025, 2025, 2025],
            "Niveau": ["4", "3", "2"],
            "Opleidingcode": ["X", "Y", "Z"],
        }
    )
    result = _voeg_sr_vlaggen_toe(df)
    hoofd = result.filter(pl.col("_hoofdinschrijving")).to_dicts()
    assert len(hoofd) == 2
    p1 = [r for r in hoofd if r["_persoon_id"] == "P1"]
    assert len(p1) == 1
    assert p1[0]["Opleidingcode"] == "X"


def test_sr_hoofdinschrijving_gelijke_niveaus_kiest_laagste_crebo():
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1", "P1"],
            "Studiejaar": [2025, 2025],
            "Niveau": ["4", "4"],
            "Opleidingcode": ["C002", "C001"],
        }
    )
    result = _voeg_sr_vlaggen_toe(df)
    hoofd = result.filter(pl.col("_hoofdinschrijving")).to_dicts()
    assert len(hoofd) == 1
    assert hoofd[0]["Opleidingcode"] == "C001"


def test_sr_vlaggen_ontbrekende_kolommen_geeft_none():
    df = pl.DataFrame({"Studiejaar": [2025], "Niveau": ["4"]})
    result = _voeg_sr_vlaggen_toe(df)
    assert result["_hoogste_niveau"][0] is None
    assert result["_laagste_CREBO"][0] is None
    assert result["_hoofdinschrijving"][0] is None


def test_sr_niveau_numeriek_mbo_prefix():
    """Niveau "MBO-4" moet hoger zijn dan "MBO-3" via numerieke extractie."""
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1", "P1"],
            "Studiejaar": [2025, 2025],
            "Niveau": ["MBO-4", "MBO-3"],
            "Opleidingcode": ["A", "B"],
        }
    )
    result = _voeg_sr_vlaggen_toe(df)
    hoofd = dict(
        zip(
            result["Niveau"].to_list(),
            result["_hoogste_niveau"].to_list(),
            strict=True,
        )
    )
    assert hoofd["MBO-4"] is True
    assert hoofd["MBO-3"] is False


# ---------------------------------------------------------------------------
# _voeg_telling_en_jr_vlaggen_toe – unit
# ---------------------------------------------------------------------------


def test_telling_true_actief_en_hoofdinschrijving():
    df = pl.DataFrame(
        {
            "_actief_1_oktober": [True],
            "_hoofdinschrijving": [True],
            "_gediplomeerd_in_jaar": [False],
            "_ingeschreven_jaar_later": [True],
        }
    )
    result = _voeg_telling_en_jr_vlaggen_toe(df)
    assert result["_telling"][0] is True


def test_telling_false_niet_actief():
    df = pl.DataFrame(
        {
            "_actief_1_oktober": [False],
            "_hoofdinschrijving": [True],
            "_gediplomeerd_in_jaar": [False],
            "_ingeschreven_jaar_later": [False],
        }
    )
    result = _voeg_telling_en_jr_vlaggen_toe(df)
    assert result["_telling"][0] is False


def test_telling_false_niet_hoofdinschrijving():
    df = pl.DataFrame(
        {
            "_actief_1_oktober": [True],
            "_hoofdinschrijving": [False],
            "_gediplomeerd_in_jaar": [False],
            "_ingeschreven_jaar_later": [False],
        }
    )
    result = _voeg_telling_en_jr_vlaggen_toe(df)
    assert result["_telling"][0] is False


def test_telling_false_bij_null_actief():
    df = pl.DataFrame(
        {
            "_actief_1_oktober": pl.Series([None], dtype=pl.Boolean),
            "_hoofdinschrijving": [True],
            "_gediplomeerd_in_jaar": [False],
            "_ingeschreven_jaar_later": [False],
        }
    )
    result = _voeg_telling_en_jr_vlaggen_toe(df)
    assert result["_telling"][0] is False


def test_jr_noemer_gelijk_aan_telling():
    df = pl.DataFrame(
        {
            "_actief_1_oktober": [True],
            "_hoofdinschrijving": [True],
            "_gediplomeerd_in_jaar": [False],
            "_ingeschreven_jaar_later": [False],
        }
    )
    result = _voeg_telling_en_jr_vlaggen_toe(df)
    assert result["_jr_noemer"][0] == result["_telling"][0]


def test_jr_teller_true_gediplomeerd():
    df = pl.DataFrame(
        {
            "_actief_1_oktober": [True],
            "_hoofdinschrijving": [True],
            "_gediplomeerd_in_jaar": [True],
            "_ingeschreven_jaar_later": [False],
        }
    )
    result = _voeg_telling_en_jr_vlaggen_toe(df)
    assert result["_jr_teller"][0] is True


def test_jr_teller_false_niet_in_noemer():
    df = pl.DataFrame(
        {
            "_actief_1_oktober": [False],
            "_hoofdinschrijving": [True],
            "_gediplomeerd_in_jaar": [True],
            "_ingeschreven_jaar_later": [True],
        }
    )
    result = _voeg_telling_en_jr_vlaggen_toe(df)
    assert result["_jr_teller"][0] is False


def test_jr_teller_false_geen_resultaat():
    df = pl.DataFrame(
        {
            "_actief_1_oktober": [True],
            "_hoofdinschrijving": [True],
            "_gediplomeerd_in_jaar": [False],
            "_ingeschreven_jaar_later": [False],
        }
    )
    result = _voeg_telling_en_jr_vlaggen_toe(df)
    assert result["_jr_teller"][0] is False


# ---------------------------------------------------------------------------
# IndicatieBekostigbaar normalisatie (decode-fase)
# ---------------------------------------------------------------------------


def test_indicatie_bekostigbaar_normalisatie_in_demo(demo_tabellen):
    """Na decode-normalisatie bevat inschrijvingen alleen 'J' of 'N' (of null)."""
    df = demo_tabellen["inschrijvingen"]
    if "IndicatieBekostigbaar" in df.columns:
        waarden = set(df["IndicatieBekostigbaar"].drop_nulls().unique().to_list())
        assert waarden <= {"J", "N"}, f"Onverwachte waarden: {waarden}"


# ---------------------------------------------------------------------------
# _voeg_entree_vlaggen_toe – unit
# ---------------------------------------------------------------------------


def test_entree_uitstroom_true_mbo1_uitgeschreven():
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1"],
            "Niveau": ["MBO-1"],
            "DatumUitschrijvingWerkelijk": pl.Series([date(2025, 6, 1)], dtype=pl.Date),
            "DatumUitschrijvingGepland": pl.Series([date(2025, 7, 31)], dtype=pl.Date),
        }
    )
    result = _voeg_entree_vlaggen_toe(df)
    assert result["_entree_uitstroom"][0] is True


def test_entree_uitstroom_false_mbo4():
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1"],
            "Niveau": ["MBO-4"],
            "DatumUitschrijvingWerkelijk": pl.Series([date(2025, 6, 1)], dtype=pl.Date),
            "DatumUitschrijvingGepland": pl.Series([date(2025, 7, 31)], dtype=pl.Date),
        }
    )
    result = _voeg_entree_vlaggen_toe(df)
    assert result["_entree_uitstroom"][0] is False


def test_entree_uitstroom_false_niet_uitgeschreven():
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1"],
            "Niveau": ["MBO-1"],
            "DatumUitschrijvingWerkelijk": pl.Series([None], dtype=pl.Date),
            "DatumUitschrijvingGepland": pl.Series([date(2025, 7, 31)], dtype=pl.Date),
        }
    )
    result = _voeg_entree_vlaggen_toe(df)
    assert result["_entree_uitstroom"][0] is False


def test_entree_doorstroom_true():
    """MBO-1 student met ook een MBO-4 inschrijving bij dezelfde instelling."""
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1", "P1"],
            "BRIN": ["01AA", "01AA"],
            "Niveau": ["MBO-1", "MBO-4"],
            "DatumUitschrijvingWerkelijk": pl.Series(
                [date(2025, 6, 1), None], dtype=pl.Date
            ),
            "DatumUitschrijvingGepland": pl.Series(
                [date(2025, 7, 31), date(2026, 7, 31)], dtype=pl.Date
            ),
        }
    )
    result = _voeg_entree_vlaggen_toe(df)
    doorstroom = dict(
        zip(
            result["Niveau"].to_list(),
            result["_entree_doorstroom"].to_list(),
            strict=True,
        )
    )
    assert doorstroom["MBO-1"] is True
    assert doorstroom["MBO-4"] is False


def test_entree_doorstroom_false_andere_instelling():
    """MBO-1 bij instelling A, MBO-4 bij instelling B → geen doorstroom."""
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1", "P1"],
            "BRIN": ["01AA", "02BB"],
            "Niveau": ["MBO-1", "MBO-4"],
            "DatumUitschrijvingWerkelijk": pl.Series(
                [date(2025, 6, 1), None], dtype=pl.Date
            ),
            "DatumUitschrijvingGepland": pl.Series(
                [date(2025, 7, 31), date(2026, 7, 31)], dtype=pl.Date
            ),
        }
    )
    result = _voeg_entree_vlaggen_toe(df)
    doorstroom = dict(
        zip(
            result["Niveau"].to_list(),
            result["_entree_doorstroom"].to_list(),
            strict=True,
        )
    )
    assert doorstroom["MBO-1"] is False


def test_entree_doorstroom_false_geen_vervolg():
    """MBO-1 student zonder hoger niveau → geen doorstroom."""
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1"],
            "BRIN": ["01AA"],
            "Niveau": ["MBO-1"],
            "DatumUitschrijvingWerkelijk": pl.Series([date(2025, 6, 1)], dtype=pl.Date),
            "DatumUitschrijvingGepland": pl.Series([date(2025, 7, 31)], dtype=pl.Date),
        }
    )
    result = _voeg_entree_vlaggen_toe(df)
    assert result["_entree_doorstroom"][0] is False


def test_entree_vlaggen_ontbrekende_kolommen():
    df = pl.DataFrame({"Studiejaar": [2025]})
    result = _voeg_entree_vlaggen_toe(df)
    assert result["_entree_uitstroom"][0] is None
    assert result["_entree_doorstroom"][0] is None


# ---------------------------------------------------------------------------
# _voeg_afgeleide_velden_toe – unit
# ---------------------------------------------------------------------------


def test_niveau_gecombineerd():
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1"],
            "Inschrijvingvolgnummer": ["1"],
            "Niveau": ["MBO-4"],
            "Leertraject": ["BOL"],
        }
    )
    result = _voeg_afgeleide_velden_toe(df)
    assert result["Niveau_gecombineerd"][0] == "MBO-4 BOL"


def test_niveau_gecombineerd_null_leertraject():
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1"],
            "Inschrijvingvolgnummer": ["1"],
            "Niveau": ["MBO-4"],
            "Leertraject": pl.Series([None], dtype=pl.Utf8),
        }
    )
    result = _voeg_afgeleide_velden_toe(df)
    assert result["Niveau_gecombineerd"][0] is None


def test_tellingen_aanwezig():
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1", "P1", "P2"],
            "Inschrijvingvolgnummer": ["1", "1", "1"],
            "levering": ["L1", "L2", "L1"],
        }
    )
    result = _voeg_afgeleide_velden_toe(df)
    p1 = result.filter(pl.col("_persoon_id") == "P1")
    assert p1["_tellingen_aanwezig"][0] == 2
    p2 = result.filter(pl.col("_persoon_id") == "P2")
    assert p2["_tellingen_aanwezig"][0] == 1


def test_afgeleide_velden_in_demo(demo_tabellen):
    """Afgeleide velden zijn aanwezig in de inschrijvingen-tabel."""
    df = demo_tabellen["inschrijvingen"]
    assert "Niveau_gecombineerd" in df.columns
    assert "_tellingen_aanwezig" in df.columns


# ---------------------------------------------------------------------------
# Niveau aanvullen vanuit CREBO
# ---------------------------------------------------------------------------


def test_vul_niveau_aan_vanuit_crebo():
    """Null Niveau wordt aangevuld via Opleidingcode → CREBO-tabel."""
    df = pl.DataFrame(
        {
            "Opleidingcode": ["25655", "23301"],
            "Niveau": [None, "MBO-1"],
        }
    )
    result = _vul_niveau_aan(df)
    assert result["Niveau"][0] == "MBO-4"
    assert result["Niveau"][1] == "MBO-1"


def test_vul_niveau_aan_behoudt_bestaand():
    """Bestaand Niveau wordt niet overschreven door CREBO."""
    df = pl.DataFrame(
        {
            "Opleidingcode": ["25655"],
            "Niveau": ["MBO-3"],
        }
    )
    result = _vul_niveau_aan(df)
    assert result["Niveau"][0] == "MBO-3"


def test_vul_niveau_aan_onbekende_code():
    """Onbekende Opleidingcode laat Niveau op null."""
    df = pl.DataFrame(
        {
            "Opleidingcode": ["99999"],
            "Niveau": [None],
        }
    )
    result = _vul_niveau_aan(df)
    assert result["Niveau"][0] is None


def test_vul_niveau_in_demo(demo_tabellen):
    """Na Niveau-aanvulling hebben de meeste rijen een Niveau."""
    df = demo_tabellen["inschrijvingen"]
    filled = df["Niveau"].drop_nulls().len()
    assert filled > 2


# ---------------------------------------------------------------------------
# Studiejaar afleiding
# ---------------------------------------------------------------------------


def test_studiejaar_afgeleid_uit_datumbegin_augustus():
    """DatumBegin in augustus → studiejaar = jaar van DatumBegin."""
    df = pl.DataFrame(
        {
            "DatumBegin": pl.Series([date(2025, 8, 1)], dtype=pl.Date),
        }
    )
    result = _leid_studiejaar_af(df)
    assert result["Studiejaar"][0] == 2025


def test_studiejaar_afgeleid_uit_datumbegin_januari():
    """DatumBegin in januari → studiejaar = jaar - 1."""
    df = pl.DataFrame(
        {
            "DatumBegin": pl.Series([date(2026, 1, 15)], dtype=pl.Date),
        }
    )
    result = _leid_studiejaar_af(df)
    assert result["Studiejaar"][0] == 2025


def test_studiejaar_afgeleid_uit_datumbegin_juli():
    """DatumBegin in juli → studiejaar = jaar - 1 (nog vorig studiejaar)."""
    df = pl.DataFrame(
        {
            "DatumBegin": pl.Series([date(2026, 7, 31)], dtype=pl.Date),
        }
    )
    result = _leid_studiejaar_af(df)
    assert result["Studiejaar"][0] == 2025


def test_studiejaar_behoudt_bestaande_waarde():
    """Bestaand Studiejaar wordt niet overschreven."""
    df = pl.DataFrame(
        {
            "DatumBegin": pl.Series([date(2025, 9, 1)], dtype=pl.Date),
            "Studiejaar": pl.Series([2024], dtype=pl.Int64),
        }
    )
    result = _leid_studiejaar_af(df)
    assert result["Studiejaar"][0] == 2024


def test_studiejaar_vult_null_aan():
    """Null Studiejaar wordt aangevuld, bestaande waarden blijven."""
    df = pl.DataFrame(
        {
            "DatumBegin": pl.Series(
                [date(2025, 9, 1), date(2024, 10, 1)], dtype=pl.Date
            ),
            "Studiejaar": pl.Series([None, 2024], dtype=pl.Int64),
        }
    )
    result = _leid_studiejaar_af(df)
    assert result["Studiejaar"].to_list() == [2025, 2024]


def test_studiejaar_uit_datuminschrijving():
    """Zonder DatumBegin wordt DatumInschrijving gebruikt (TBGI-pad)."""
    df = pl.DataFrame(
        {
            "DatumInschrijving": pl.Series([date(2024, 2, 1)], dtype=pl.Date),
        }
    )
    result = _leid_studiejaar_af(df)
    assert result["Studiejaar"][0] == 2023


def test_studiejaar_geen_datum_geen_crash():
    """Zonder datumvelden: voegt Studiejaar_*, Studiejaar toe (alle null)."""
    df = pl.DataFrame({"_persoon_id": ["P1"]})
    result = _leid_studiejaar_af(df)
    assert "Studiejaar_periode" in result.columns
    assert "Studiejaar_levering" in result.columns
    assert "Studiejaar" in result.columns
    assert result["Studiejaar"][0] is None
    assert result["Studiejaar_periode"][0] is None
    assert result["Studiejaar_levering"][0] is None


def test_studiejaar_afgeleid_in_demo(demo_tabellen):
    """Na afleiding heeft elke rij een Studiejaar (geen nulls meer)."""
    df = demo_tabellen["inschrijvingen"]
    assert df["Studiejaar"].null_count() == 0


# ---------------------------------------------------------------------------
# HMAC-pseudonimisering: salt-management tests
# ---------------------------------------------------------------------------


def test_laad_pseudonimisering_salt_from_env(monkeypatch):
    """Env var MBO_PSEUDONIMISERING_SALT takes precedence."""
    from mbo_bekostiging_bestanden.transform import _laad_pseudonimisering_salt

    monkeypatch.setenv("MBO_PSEUDONIMISERING_SALT", "test-env-salt-12345")
    # Clear the cache to force reload
    _laad_pseudonimisering_salt.cache_clear()

    salt = _laad_pseudonimisering_salt()
    assert salt == "test-env-salt-12345"

    # Cleanup
    _laad_pseudonimisering_salt.cache_clear()


def test_laad_pseudonimisering_salt_fails_without_env_or_config(monkeypatch, tmp_path):
    """If env var missing and no config.toml, should raise ValueError."""
    from mbo_bekostiging_bestanden.transform import _laad_pseudonimisering_salt

    # Remove env var if set
    monkeypatch.delenv("MBO_PSEUDONIMISERING_SALT", raising=False)
    # Clear cache
    _laad_pseudonimisering_salt.cache_clear()

    # When app/config.toml has no salt, should fail
    with pytest.raises(ValueError, match="Geen pseudonimisering_salt"):
        _laad_pseudonimisering_salt()

    # Cleanup
    _laad_pseudonimisering_salt.cache_clear()


def test_detail_bekostiging_gedeeld_volgnummer_geeft_geen_fan_out():
    """Twee personen met hetzelfde Inschrijvingvolgnummer (#125).

    Elke teldatum hoort bij precies één persoon; koppelen via
    (BRIN, Inschrijvingvolgnummer) zou elke teldatum aan beide personen hangen.
    """
    inschrijving = pl.DataFrame(
        {
            "levering": ["L1", "L1"],
            "BRIN": ["25LX", "25LX"],
            "Burgerservicenummer": ["P1", "P2"],
            "Onderwijsnummer": [None, None],
            "Inschrijvingvolgnummer": ["C1", "C1"],
        },
        schema_overrides={"Onderwijsnummer": pl.Utf8},
    )
    teldatum = inschrijving.with_columns(pl.lit("2025-10-01").alias("Teldatum"))

    detail = _bouw_detail_bekostiging(
        {"Inschrijving": inschrijving, "Teldatum": teldatum}
    )

    assert detail.height == 2
    assert detail["_persoon_id"].n_unique() == 2


# ---------------------------------------------------------------------------
# _add_persoon_id – identifierdomeinen (#128)
# ---------------------------------------------------------------------------
# GRONDSLAG levert een omgenummerd PGN, RO/TBGI een BSN of ONr (PvE 4.8.2
# §17.1). Gelijke cijfers uit verschillende domeinen zijn verschillende personen.


def _persoon_ids(**kolommen: list[str | None]) -> list[str | None]:
    df = pl.DataFrame(kolommen, schema=dict.fromkeys(kolommen, pl.Utf8))
    return _add_persoon_id(df)["_persoon_id"].to_list()


def test_zelfde_waarde_in_ander_identifierdomein_is_andere_persoon():
    pgn, bsn, onr = _persoon_ids(
        PseudoNummer=["123456789", None, None],
        Burgerservicenummer=[None, "123456789", None],
        Onderwijsnummer=[None, None, "123456789"],
    )
    assert len({pgn, bsn, onr}) == 3


def test_persoon_id_is_pseudoniem_van_domein_en_waarde():
    assert _persoon_ids(Burgerservicenummer=["123456789"]) == [
        pseudoniem("BSN", "123456789")
    ]


def test_lege_identifier_valt_door_naar_volgend_domein():
    assert _persoon_ids(Burgerservicenummer=[""], Onderwijsnummer=["987654321"]) == [
        pseudoniem("ONR", "987654321")
    ]


def test_zonder_identifier_geen_persoon_id():
    assert _persoon_ids(Burgerservicenummer=["", None]) == [None, None]
