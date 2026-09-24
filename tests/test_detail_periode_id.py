"""Tests voor ``_inschrijving_periode_id`` op de detail-feiten (issues #63, #90).

De detail-feiten moeten via de stabiele periodesleutel zonder fan-out terug te
koppelen zijn aan ``fact_inschrijving``. Getoetst op de echte star-output van
de demo-data en op de toewijzingsregel zelf.
"""

from datetime import date

import polars as pl
import pytest

from mbo_bekostiging_bestanden.transform import _koppel_periode_id

SLEUTEL = "_inschrijving_periode_id"
INSCHRIJVING = ["levering", "_persoon_id", "Inschrijvingvolgnummer"]
DETAIL_FEITEN = [
    "fact_bpv",
    "fact_kzd",
    "fact_amo",
    "fact_geo",
    "fact_bekostiging",
    "fact_bekostiging_diploma",
]


@pytest.mark.parametrize("naam", DETAIL_FEITEN)
def test_detail_feit_heeft_periode_id(demo_star, naam):
    assert SLEUTEL in demo_star[naam].columns, f"{naam} mist {SLEUTEL}"


@pytest.mark.parametrize("naam", DETAIL_FEITEN)
def test_periode_id_verwijst_naar_bestaande_inschrijving(demo_star, naam):
    fi = demo_star["fact_inschrijving"].select(SLEUTEL)
    wees = demo_star[naam].drop_nulls(SLEUTEL).join(fi, on=SLEUTEL, how="anti")
    assert wees.is_empty(), f"{naam}: {wees.height} sleutels zonder inschrijving"


@pytest.mark.parametrize("naam", DETAIL_FEITEN)
def test_geen_fanout_bij_join_op_periode_id(demo_star, naam):
    detail = demo_star[naam].drop_nulls(SLEUTEL)
    fi = demo_star["fact_inschrijving"].select(SLEUTEL)
    joined = detail.join(fi, on=SLEUTEL, how="inner")
    assert joined.height == detail.height, (
        f"{naam}: fan-out {detail.height} -> {joined.height}"
    )


@pytest.mark.parametrize("naam", ["fact_bpv", "fact_kzd", "fact_amo", "fact_geo"])
def test_koppelbare_detailrijen_krijgen_periode_id(demo_star, naam):
    """Elke detailrij met een bestaande inschrijving krijgt een periodesleutel."""
    inschrijvingen = demo_star["fact_inschrijving"].select(INSCHRIJVING).unique()
    koppelbaar = demo_star[naam].join(inschrijvingen, on=INSCHRIJVING, how="semi")
    assert koppelbaar[SLEUTEL].null_count() == 0


def _perioden() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "levering": ["L"] * 2,
            "_persoon_id": ["p"] * 2,
            "Inschrijvingvolgnummer": ["1"] * 2,
            "DatumBegin": [date(2024, 8, 1), date(2025, 2, 1)],
            SLEUTEL: ["eerste", "tweede"],
        }
    )


def _detail(*datums: date | None) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "levering": ["L"] * len(datums),
            "_persoon_id": ["p"] * len(datums),
            "Inschrijvingvolgnummer": ["1"] * len(datums),
            "Datum": list(datums),
        },
        schema_overrides={"Datum": pl.Date},
    )


def test_detail_krijgt_periode_waarin_datum_valt():
    detail = _detail(date(2024, 9, 1), date(2025, 3, 1), date(2025, 2, 1))
    result = _koppel_periode_id(detail, _perioden(), "Datum")
    assert result[SLEUTEL].to_list() == ["eerste", "tweede", "tweede"]


def test_datum_voor_eerste_periode_of_leeg_valt_terug_op_eerste_periode():
    result = _koppel_periode_id(_detail(date(2020, 1, 1), None), _perioden(), "Datum")
    assert result[SLEUTEL].to_list() == ["eerste", "eerste"]


def test_rijvolgorde_en_rijtal_blijven_behouden():
    detail = _detail(date(2025, 3, 1), None, date(2024, 9, 1))
    result = _koppel_periode_id(detail, _perioden(), "Datum")
    assert result.drop(SLEUTEL).equals(detail)


def test_detail_zonder_inschrijving_krijgt_lege_sleutel():
    detail = _detail(date(2024, 9, 1)).with_columns(
        pl.lit("onbekend").alias("Inschrijvingvolgnummer")
    )
    result = _koppel_periode_id(detail, _perioden(), "Datum")
    assert result[SLEUTEL].to_list() == [None]
