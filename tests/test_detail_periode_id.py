"""Tests voor ``_inschrijving_periode_id`` op de detail-feiten (issues #63, #90).

De detail-feiten moeten via de stabiele periodesleutel zonder fan-out terug te
koppelen zijn aan ``fact_inschrijving``. Getoetst op de echte star-output van
de demo-data en op de toewijzingsregel zelf.
"""

import warnings
from datetime import date

import polars as pl
import pytest

from mbo_bekostiging_bestanden.contracts import KOPPELSTATUSSEN
from mbo_bekostiging_bestanden.quality import compile_quality_report
from mbo_bekostiging_bestanden.transform import (
    _koppel_periode_id,
    _koppel_periode_id_met_terugval,
)

SLEUTEL = "_inschrijving_periode_id"
STATUS = "_periode_koppel_status"
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
    assert result.drop(SLEUTEL, STATUS).equals(detail)


def test_detail_zonder_inschrijving_krijgt_lege_sleutel():
    detail = _detail(date(2024, 9, 1)).with_columns(
        pl.lit("onbekend").alias("Inschrijvingvolgnummer")
    )
    result = _koppel_periode_id(detail, _perioden(), "Datum")
    assert result[SLEUTEL].to_list() == [None]


def test_periode_zonder_begindatum_is_nooit_de_eerste_periode():
    perioden = pl.concat(
        [
            _perioden(),
            _perioden()
            .head(1)
            .with_columns(
                pl.lit(None, dtype=pl.Date).alias("DatumBegin"),
                pl.lit("zonder_begin").alias(SLEUTEL),
            ),
        ]
    )
    result = _koppel_periode_id(_detail(None), perioden, "Datum")
    assert result[SLEUTEL].to_list() == ["eerste"]


def test_detail_zonder_koppelkolommen_krijgt_lege_sleutel():
    detail = _detail(date(2024, 9, 1)).drop("Inschrijvingvolgnummer")
    result = _koppel_periode_id(detail, _perioden(), "Datum")
    assert result[SLEUTEL].to_list() == [None]


def test_tekstdatum_koppelt_zonder_deprecation_warning():
    """ISO-tekst wordt expliciet geparsed, niet via de deprecated cast (#123)."""
    detail = _detail(date(2024, 9, 1), date(2025, 3, 1)).with_columns(
        pl.col("Datum").dt.to_string()
    )
    with warnings.catch_warnings(record=True) as gevangen:
        warnings.simplefilter("always")
        result = _koppel_periode_id(detail, _perioden(), "Datum")
    assert result[SLEUTEL].to_list() == ["eerste", "tweede"]
    assert not [w for w in gevangen if issubclass(w.category, DeprecationWarning)]


# ---------------------------------------------------------------------------
# Koppelstatus (#121): waarom een detailrij aan haar periode hangt
# ---------------------------------------------------------------------------
def test_koppelstatus_onderscheidt_elke_toewijzing():
    detail = pl.concat(
        [
            _detail(date(2025, 3, 1), None, date(2020, 1, 1)),
            _detail(date(2024, 9, 1)).with_columns(
                pl.lit("onbekend").alias("Inschrijvingvolgnummer")
            ),
        ]
    )
    result = _koppel_periode_id(detail, _perioden(), "Datum")
    assert result.select(SLEUTEL, STATUS).rows() == [
        ("tweede", "binnen_periode"),
        ("eerste", "datum_leeg"),
        ("eerste", "voor_eerste_periode"),
        (None, "geen_inschrijving"),
    ]


def test_koppelstatus_zonder_datumkolom():
    result = _koppel_periode_id(_detail(date(2024, 9, 1)), _perioden(), "Bestaat")
    assert result.select(SLEUTEL, STATUS).rows() == [("eerste", "geen_datumkolom")]


def test_koppelstatus_zonder_koppelkolommen():
    detail = _detail(date(2024, 9, 1)).drop("Inschrijvingvolgnummer")
    result = _koppel_periode_id(detail, _perioden(), "Datum")
    assert result[STATUS].to_list() == ["geen_inschrijving"]


def test_koppelstatus_volgt_de_sleutel_die_koppelde():
    """Bij terugval (#112) telt de status van de sleutel die de periode gaf."""
    detail = _detail(date(2025, 3, 1), None).with_columns(
        pl.lit("andere").alias("levering")
    )
    zonder_levering = ["_persoon_id", "Inschrijvingvolgnummer"]
    result = _koppel_periode_id_met_terugval(
        detail, _perioden(), "Datum", (INSCHRIJVING, zonder_levering)
    )
    assert result.select(SLEUTEL, STATUS).rows() == [
        ("tweede", "binnen_periode"),
        ("eerste", "datum_leeg"),
    ]


@pytest.mark.parametrize("naam", DETAIL_FEITEN)
def test_detail_feit_heeft_koppelstatus(demo_star, naam):
    statussen = set(demo_star[naam][STATUS])
    assert statussen <= set(KOPPELSTATUSSEN)
    gekoppeld = demo_star[naam].filter(pl.col(STATUS) != "geen_inschrijving")
    assert gekoppeld[SLEUTEL].null_count() == 0


def test_quality_telt_koppelstatus_per_detailfeit(demo_star):
    telling = compile_quality_report(demo_star)["star"]["periode_koppelstatus"]
    assert set(telling) == set(DETAIL_FEITEN)
    for naam, per_status in telling.items():
        assert sum(per_status.values()) == demo_star[naam].height
