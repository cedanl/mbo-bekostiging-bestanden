"""Tests voor de sidebar-jaarselectie die consistent op data-feiten wordt toegepast.

De helpers leven in het package (``mbo_bekostiging_bestanden.filters``) zodat de
app-jaarselectie en de TBGI-bekostigingsfilter los van de UI getest kunnen worden.
"""

import polars as pl

from mbo_bekostiging_bestanden.filters import (
    filter_detail_op_inschrijvingen,
    filter_fact_bekostiging_op_jaar,
    periode_jaar_kolom,
)


def test_periode_jaar_kolom_kiest_periode_variant():
    """Studiejaar_periode heeft voorrang (correct voor periode-analyses)."""
    df = pl.DataFrame({"Studiejaar": [2025], "Studiejaar_periode": [2024]})
    assert periode_jaar_kolom(df) == "Studiejaar_periode"


def test_periode_jaar_kolom_fallbacks_naar_studiejaar():
    """Zonder periode-variant valt het terug op Studiejaar, anders None."""
    assert periode_jaar_kolom(pl.DataFrame({"Studiejaar": [2024]})) == "Studiejaar"
    assert periode_jaar_kolom(pl.DataFrame({"levering": ["h16"]})) is None


def test_bekostiging_filter_hanteert_periodejaar_niet_leveringjaar():
    """De sidebar selecteert op periodejaar; bekostiging moet datzelfde jaar aanhouden.

    Regressie: eerder werd op ``df["Studiejaar"]`` (leveringjaar) gefilterd, waardoor
    bij RO/GRONDSLAG/TBGI-combinaties andere jaren verschenen dan de selectie.
    """
    geselecteerd = pl.DataFrame(
        {
            "levering": ["h17/GRONDSLAG_IP_MBO_27DV_2025"],
            "Studiejaar": [2025],  # leveringjaar — misleidend
            "Studiejaar_periode": [2024],  # werkelijke periode (aug'24–jul'25)
        }
    )
    bek = pl.DataFrame(
        {
            "levering": ["h16/TBGI_25LX_2027", "h16/TBGI_25LX_2027"],
            "Studiejaar": [2024, 2025],  # afgeleid uit Teldatum
            "Bekostigingsstatus": ["Bekostigd", "Niet bekostigd"],
        }
    )

    resultaat = filter_fact_bekostiging_op_jaar(bek, geselecteerd)

    assert resultaat["Studiejaar"].to_list() == [2024]


def test_bekostiging_filter_behoudt_alle_rijen_bij_alle_jaren():
    """Wanneer alle periodejaren geselecteerd zijn, blijft alles behouden."""
    geselecteerd = pl.DataFrame({"Studiejaar_periode": [2024, 2025]})
    bek = pl.DataFrame(
        {
            "levering": ["h16/TBGI", "h16/TBGI", "h16/TBGI"],
            "Studiejaar": [2024, 2025, 2025],
        }
    )

    resultaat = filter_fact_bekostiging_op_jaar(bek, geselecteerd)

    assert resultaat.height == 3


def test_bekostiging_filter_leeg_zonder_selectie():
    """Geen geselecteerde jaren (of leeg df) levert een lege feitentabel."""
    leeg_df = pl.DataFrame(
        schema={
            "Studiejaar": pl.Int64,
            "Studiejaar_periode": pl.Int64,
        }
    )
    bek = pl.DataFrame({"levering": ["h16"], "Studiejaar": [2024]})

    assert filter_fact_bekostiging_op_jaar(bek, leeg_df).is_empty()


def test_bekostiging_filter_ongewijzigd_zonder_jaarkolom_in_feit():
    """Als fact_bekostiging geen Studiejaar kent is er niets te filteren."""
    bek = pl.DataFrame({"levering": ["h16"], "Teldatum": ["2024-10-01"]})
    geselecteerd = pl.DataFrame({"Studiejaar_periode": [2024]})

    resultaat = filter_fact_bekostiging_op_jaar(bek, geselecteerd)

    assert resultaat.height == 1


def test_bekostiging_filter_leeg_zonder_jaarkolom_in_selectie():
    """Als de inschrijvingen geen jaarkolom hebben kan er niet gefilterd worden."""
    bek = pl.DataFrame({"levering": ["h16"], "Studiejaar": [2024]})
    geselecteerd = pl.DataFrame({"levering": ["h17/..."]})

    assert filter_fact_bekostiging_op_jaar(bek, geselecteerd).is_empty()


def _twee_perioden() -> pl.DataFrame:
    """Eén inschrijving met twee ISP-perioden in verschillende studiejaren."""
    return pl.DataFrame(
        {
            "levering": ["L", "L"],
            "_persoon_id": ["p", "p"],
            "Inschrijvingvolgnummer": ["1", "1"],
            "_inschrijving_periode_id": ["p2024", "p2025"],
            "Studiejaar_periode": [2024, 2025],
        }
    )


def test_detailfilter_houdt_alleen_rijen_van_geselecteerde_periode():
    """Een BPV uit periode 2024 hoort niet bij een selectie van alleen 2025."""
    detail = pl.DataFrame(
        {
            "levering": ["L", "L"],
            "_persoon_id": ["p", "p"],
            "Inschrijvingvolgnummer": ["1", "1"],
            "_inschrijving_periode_id": ["p2024", "p2025"],
            "Volgnummer": [1, 2],
        }
    )
    selectie = _twee_perioden().filter(pl.col("Studiejaar_periode") == 2025)
    result = filter_detail_op_inschrijvingen(detail, selectie)
    assert result["Volgnummer"].to_list() == [2]


def test_detailfilter_zonder_periode_id_valt_terug_op_inschrijving_zonder_fanout():
    """Star-output zonder periodesleutel: filter op inschrijving, zonder fan-out."""
    detail = pl.DataFrame(
        {
            "levering": ["L"],
            "_persoon_id": ["p"],
            "Inschrijvingvolgnummer": ["1"],
            "Volgnummer": [1],
        }
    )
    result = filter_detail_op_inschrijvingen(detail, _twee_perioden())
    assert result.height == 1


def test_detailfilter_zonder_gedeelde_sleutel_of_selectie_geeft_leeg():
    detail = pl.DataFrame({"Volgnummer": [1]})
    assert filter_detail_op_inschrijvingen(detail, _twee_perioden()).is_empty()
    leeg = _twee_perioden().clear()
    met_sleutel = _twee_perioden().select("_inschrijving_periode_id")
    assert filter_detail_op_inschrijvingen(met_sleutel, leeg).is_empty()
