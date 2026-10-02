"""Sterbouw: transform.py en de domeinmodules daarachter (#198)."""

from datetime import date

import polars as pl
import pytest

from mbo_bekostiging_bestanden.contracts import BRON
from mbo_bekostiging_bestanden.details import (
    _bouw_detail_bekostiging,
    _bouw_detail_bekostiging_diploma,
    _resolve_inschrijving,
)
from mbo_bekostiging_bestanden.identiteit import (
    laad_pseudonimisering_salt,
    pseudoniem,
    pseudonimiseer,
)
from mbo_bekostiging_bestanden.inschrijvingen import _voeg_afgeleide_velden_toe
from mbo_bekostiging_bestanden.koppelingen import Koppelingen
from mbo_bekostiging_bestanden.opleidingsniveau import vul_niveau_aan
from mbo_bekostiging_bestanden.perioden import leid_studiejaar_af
from mbo_bekostiging_bestanden.transform import bouw_analysetabellen

# ---------------------------------------------------------------------------
# bouw_analysetabellen – input-validatie
# ---------------------------------------------------------------------------


def test_bouw_analysetabellen_raises_without_isp_and_inschrijving():
    with pytest.raises(ValueError, match="ISP"):
        bouw_analysetabellen({"PER": pl.DataFrame()})


def test_bouw_analysetabellen_raises_with_leeg_isp_en_geen_inschrijving():
    with pytest.raises(ValueError, match="ISP"):
        bouw_analysetabellen({"ISP": pl.DataFrame()})


def test_bouw_analysetabellen_tbgi_fallback_gebruikt_inschrijving_als_grain():
    """Zonder ISP maar met TBGI Inschrijving → inschrijvingen gevuld."""
    inschrijving = pl.DataFrame(
        {
            "levering": ["L1"],
            "BRIN": ["25LX"],
            "_persoon_id": ["BSN1"],
            "Inschrijvingvolgnummer": ["001"],
        }
    )
    result = bouw_analysetabellen({"Inschrijving": inschrijving})
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
            "_persoon_id": ["BSN1"],
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
    result = bouw_analysetabellen({"Inschrijving": inschrijving, "Teldatum": teldatum})
    detail = result["detail_bekostiging"]
    assert detail.height == 1
    assert "TBGI" in detail[BRON].to_list()


# ---------------------------------------------------------------------------
# bouw_analysetabellen – output-structuur
# ---------------------------------------------------------------------------


def test_bouw_analysetabellen_levert_alle_tabellen(demo_tabellen):
    assert set(demo_tabellen.keys()) == {
        "inschrijvingen",
        "detail_bpv",
        "detail_kzd_amo",
        "detail_bekostiging",
        "detail_bekostiging_diploma",
        "detail_geo",
        "meta_leveringen",
        "meta_canonicalisatie",
        "meta_koppelkeuzes",
    }


def test_inschrijvingen_grain_isp(demo_tabellen, demo_stacked):
    """inschrijvingen heeft precies één rij per (canonieke) ISP-periode.

    De demo bevat geen overlappende leveringen, dus niets wordt vervangen.
    """
    assert demo_tabellen["meta_canonicalisatie"].is_empty()
    isp = demo_tabellen["inschrijvingen"].filter(pl.col("Bron") == "ISP")
    assert isp.height == demo_stacked["ISP"].height


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
            "_persoon_id": ["P1"],
            "Inschrijvingvolgnummer": ["C1"],
            "Teldatum": ["2024-10-01"],
            "Recordsoort": ["BII"],
        }
    )
    detail = _bouw_detail_bekostiging({"BII": bii})
    assert "BII" in detail[BRON].unique().to_list()


def test_detail_bekostiging_bevat_tbgi(demo_tabellen):
    detail = demo_tabellen["detail_bekostiging"]
    assert "TBGI" in detail[BRON].unique().to_list()


# ---------------------------------------------------------------------------
# detail_bekostiging_diploma
# ---------------------------------------------------------------------------


def test_detail_bekostiging_diploma_leeg_zonder_diploma():
    """Zonder Diploma-sleutel geeft de functie een leeg DataFrame."""
    assert _bouw_detail_bekostiging_diploma({}, Koppelingen()).is_empty()


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
    kzd = pl.DataFrame(
        {
            "levering": ["L1"],
            "_persoon_id": ["P1"],
            "Inschrijvingvolgnummer": [""],
            "ResultaatvolgnummerDiploma": ["REF1"],
        }
    )
    dip = pl.DataFrame(
        {
            "levering": ["L1"],
            "_persoon_id": ["P1"],
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
            "_persoon_id": ["P1"],
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
            "_persoon_id": ["P1"],
            "Resultaatvolgnummer": ["REF1"],
            "Inschrijvingvolgnummer": ["C9"],
        }
    )
    result = _resolve_inschrijving(df, dip)
    assert result["Inschrijvingvolgnummer"].to_list() == ["A1"]


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


def test_afgeleide_velden_in_demo(demo_tabellen):
    """Afgeleide velden zijn aanwezig in de inschrijvingen-tabel; er is geen
    apart, over-instellingen-heen tellend ``_tellingen_aanwezig``-veld (de
    duplicaatdetectie over leveringen doet de canonicalisatie, #210)."""
    df = demo_tabellen["inschrijvingen"]
    assert "Niveau_gecombineerd" in df.columns
    assert "_tellingen_aanwezig" not in df.columns


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
    result = vul_niveau_aan(df)
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
    result = vul_niveau_aan(df)
    assert result["Niveau"][0] == "MBO-3"


def test_vul_niveau_aan_via_sbb_bij_nieuwe_codering():
    """Nieuwe codering (23xxx) mist niveau in crebo.csv; S-BB kent het (#130)."""
    result = vul_niveau_aan(
        pl.DataFrame({"Opleidingcode": ["23023"], "Niveau": [None]})
    )
    assert result["Niveau"][0] == "MBO-4"


def test_vul_niveau_aan_legt_herkomst_vast():
    """Onbekend niveau is iets anders dan niveau 1: de herkomst maakt dat zichtbaar."""
    df = pl.DataFrame(
        {
            "Opleidingcode": ["25655", "25655", "23023", "22001", "99999"],
            "Niveau": ["MBO-3", None, None, None, None],
        }
    )
    result = vul_niveau_aan(df)
    assert result["Niveau"].to_list() == ["MBO-3", "MBO-4", "MBO-4", None, None]
    assert result["_niveau_herkomst"].to_list() == [
        "bron",
        "crebo",
        "sbb",
        "sbb_nvt",
        "onbekend",
    ]


def test_vul_niveau_aan_zonder_ontbrekend_niveau_heeft_herkomst_bron():
    result = vul_niveau_aan(
        pl.DataFrame({"Opleidingcode": ["25655"], "Niveau": ["MBO-4"]})
    )
    assert result["_niveau_herkomst"].to_list() == ["bron"]


def test_vul_niveau_aan_voegt_alleen_herkomst_toe():
    """Geen interne join-sleutels in de output (#145)."""
    df = pl.DataFrame({"Opleidingcode": ["23023"], "Niveau": [None]})
    assert set(vul_niveau_aan(df).columns) - set(df.columns) == {"_niveau_herkomst"}


def test_vul_niveau_aan_onbekende_code():
    """Onbekende Opleidingcode laat Niveau op null."""
    df = pl.DataFrame(
        {
            "Opleidingcode": ["99999"],
            "Niveau": [None],
        }
    )
    result = vul_niveau_aan(df)
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
    result = leid_studiejaar_af(df)
    assert result["Studiejaar"][0] == 2025


def test_studiejaar_afgeleid_uit_datumbegin_januari():
    """DatumBegin in januari → studiejaar = jaar - 1."""
    df = pl.DataFrame(
        {
            "DatumBegin": pl.Series([date(2026, 1, 15)], dtype=pl.Date),
        }
    )
    result = leid_studiejaar_af(df)
    assert result["Studiejaar"][0] == 2025


def test_studiejaar_afgeleid_uit_datumbegin_juli():
    """DatumBegin in juli → studiejaar = jaar - 1 (nog vorig studiejaar)."""
    df = pl.DataFrame(
        {
            "DatumBegin": pl.Series([date(2026, 7, 31)], dtype=pl.Date),
        }
    )
    result = leid_studiejaar_af(df)
    assert result["Studiejaar"][0] == 2025


def test_studiejaar_behoudt_bestaande_waarde():
    """Bestaand Studiejaar wordt niet overschreven."""
    df = pl.DataFrame(
        {
            "DatumBegin": pl.Series([date(2025, 9, 1)], dtype=pl.Date),
            "Studiejaar": pl.Series([2024], dtype=pl.Int64),
        }
    )
    result = leid_studiejaar_af(df)
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
    result = leid_studiejaar_af(df)
    assert result["Studiejaar"].to_list() == [2025, 2024]


def test_studiejaar_uit_datuminschrijving():
    """Zonder DatumBegin wordt DatumInschrijving gebruikt (TBGI-pad)."""
    df = pl.DataFrame(
        {
            "DatumInschrijving": pl.Series([date(2024, 2, 1)], dtype=pl.Date),
        }
    )
    result = leid_studiejaar_af(df)
    assert result["Studiejaar"][0] == 2023


def test_studiejaar_geen_datum_geen_crash():
    """Zonder datumvelden: voegt Studiejaar_*, Studiejaar toe (alle null)."""
    df = pl.DataFrame({"_persoon_id": ["P1"]})
    result = leid_studiejaar_af(df)
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
    """De env-var gaat vóór ``config.toml``."""
    monkeypatch.setenv("MBO_PSEUDONIMISERING_SALT", "test-env-salt-12345")
    # De cache zou de net gewijzigde env-var maskeren zonder deze reset.
    laad_pseudonimisering_salt.cache_clear()

    salt = laad_pseudonimisering_salt()
    assert salt == "test-env-salt-12345"

    laad_pseudonimisering_salt.cache_clear()


def test_laad_pseudonimisering_salt_fails_without_env_or_config(monkeypatch, tmp_path):
    """Zonder env-var en zonder ``config.toml``: fail-closed."""
    monkeypatch.delenv("MBO_PSEUDONIMISERING_SALT", raising=False)
    laad_pseudonimisering_salt.cache_clear()

    with pytest.raises(ValueError, match="Geen pseudonimisering_salt"):
        laad_pseudonimisering_salt()

    laad_pseudonimisering_salt.cache_clear()


def test_detail_bekostiging_gedeeld_volgnummer_geeft_geen_fan_out():
    """Twee personen met hetzelfde Inschrijvingvolgnummer (#125).

    Elke teldatum hoort bij precies één persoon; koppelen via
    (BRIN, Inschrijvingvolgnummer) zou elke teldatum aan beide personen hangen.
    """
    inschrijving = pl.DataFrame(
        {
            "levering": ["L1", "L1"],
            "BRIN": ["25LX", "25LX"],
            "_persoon_id": ["P1", "P2"],
            "Inschrijvingvolgnummer": ["C1", "C1"],
        },
    )
    teldatum = inschrijving.with_columns(pl.lit("2025-10-01").alias("Teldatum"))

    detail = _bouw_detail_bekostiging(
        {"Inschrijving": inschrijving, "Teldatum": teldatum}
    )

    assert detail.height == 2
    assert detail["_persoon_id"].n_unique() == 2


# ---------------------------------------------------------------------------
# pseudonimiseer – identifierdomeinen (#128)
# ---------------------------------------------------------------------------
# GRONDSLAG levert een omgenummerd PGN, RO/TBGI een BSN of ONr (PvE 4.8.2
# §17.1). Gelijke cijfers uit verschillende domeinen zijn verschillende personen.


def _persoon_ids(**kolommen: list[str | None]) -> list[str | None]:
    df = pl.DataFrame(kolommen, schema=dict.fromkeys(kolommen, pl.Utf8))
    return pseudonimiseer(df)["_persoon_id"].to_list()


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
