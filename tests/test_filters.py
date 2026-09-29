"""Sidebar-jaarselectie, consistent toegepast op de feiten.

De helpers leven in het package (``mbo_bekostiging_bestanden.filters``) zodat de
app-jaarselectie los van de UI getest kan worden.
"""

from datetime import date

import polars as pl

from mbo_bekostiging_bestanden.filters import (
    beschikbare_schooljaren,
    filter_bekostiging_op_schooljaren,
    filter_detail_op_inschrijvingen,
    filter_op_schooljaren,
    filter_perioden_op_schooljaren,
)

# ---------------------------------------------------------------------------
# Jaarselectie op schooljaar (#240)
# ---------------------------------------------------------------------------
# Eén selector, elk feit met zijn eigen jaarbetekenis: Schooljaar in de
# schooljaar-fact, het schooljaar van Teldatum in de bekostiging. Een TBGI-only
# inschrijving heeft een pseudo-periode vanaf DatumInschrijving (2023) maar telt
# in het schooljaar van haar Teldatum (2025).


def _bekostiging(*teldata: date) -> pl.DataFrame:
    return pl.DataFrame({"Teldatum": list(teldata)})


def test_beschikbare_schooljaren_is_unie_van_schooljaar_en_teldatum():
    jaren = pl.DataFrame({"Schooljaar": [2024, 2024]})
    bek = _bekostiging(date(2025, 10, 1), date(2026, 2, 1))
    assert beschikbare_schooljaren(jaren, bek) == [2024, 2025]


def test_beschikbare_schooljaren_zonder_feiten_is_leeg():
    assert beschikbare_schooljaren(pl.DataFrame(), pl.DataFrame()) == []


def test_schooljaar_fact_filtert_op_schooljaar():
    jaren = pl.DataFrame({"Schooljaar": [2023, 2024, 2025]})
    assert filter_op_schooljaren(jaren, [2024, 2025])["Schooljaar"].to_list() == [
        2024,
        2025,
    ]


def test_bekostiging_filtert_op_schooljaar_van_teldatum():
    """1-2-2026 is schooljaar 2025; 1-10-2024 is 2024."""
    bek = _bekostiging(date(2024, 10, 1), date(2026, 2, 1))
    resultaat = filter_bekostiging_op_schooljaren(bek, [2025])
    assert resultaat["Teldatum"].to_list() == [date(2026, 2, 1)]


def test_perioden_die_in_het_schooljaar_beginnen_of_op_1_oktober_actief_zijn():
    """Een korte periode zonder 1 oktober blijft zichtbaar in haar beginjaar;
    een TBGI-pseudo-periode (begin 2023) telt in het jaar van haar teldatum."""
    perioden = pl.DataFrame(
        {
            "_inschrijving_periode_id": ["kort", "tbgi", "ander"],
            "Studiejaar_periode": [2025, 2023, 2023],
        }
    )
    jaren = pl.DataFrame(
        {"_inschrijving_periode_id": ["tbgi", "ander"], "Schooljaar": [2025, 2023]}
    )
    resultaat = filter_perioden_op_schooljaren(perioden, jaren, [2025])
    assert resultaat["_inschrijving_periode_id"].to_list() == ["kort", "tbgi"]


def test_lege_selectie_geeft_lege_feiten():
    jaren = pl.DataFrame({"Schooljaar": [2024], "_inschrijving_periode_id": ["a"]})
    perioden = pl.DataFrame(
        {"_inschrijving_periode_id": ["a"], "Studiejaar_periode": [2024]}
    )
    assert filter_op_schooljaren(jaren, []).is_empty()
    assert filter_bekostiging_op_schooljaren(
        _bekostiging(date(2024, 10, 1)), []
    ).is_empty()
    assert filter_perioden_op_schooljaren(perioden, jaren, []).is_empty()


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
