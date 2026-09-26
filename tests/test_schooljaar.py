"""fact_inschrijving_schooljaar: één rij per persoon × BRIN × inschrijving × schooljaar.

Schooljaar t loopt van 1-8-t t/m 31-7-(t+1); de peildatum is 1-10-t. Een
ISP-periode telt in elk schooljaar waarvan zij de peildatum dekt (#193); een
open periode loopt tot de peildatum van de levering. Vlaggen gelden per
schooljaar (#164), het JR-diplomavenster is het schooljaar zelf (#194).

De verwachte waarden hieronder zijn met de hand afgeleid uit die definities,
niet uit pipeline-output.
"""

from datetime import date

import polars as pl
import pytest

from mbo_bekostiging_bestanden.schooljaar import bouw_inschrijving_schooljaar

_PEILGRENS = date(2026, 3, 24)


def _periode(
    begin: date,
    *,
    levering: str = "L",
    brin: str = "27DV",
    persoon: str = "P",
    nr: str = "1",
    eind: date | None = None,
    uitschrijving: date | None = None,
    niveau: str = "MBO-4",
    crebo: str = "25000",
    bekostigbaar: str = "J",
    diploma: date | None = None,
) -> dict:
    return {
        "levering": levering,
        "BRIN": brin,
        "_persoon_id": persoon,
        "Inschrijvingvolgnummer": nr,
        "DatumBegin": begin,
        "DatumEind": eind,
        "DatumUitschrijvingWerkelijk": uitschrijving,
        "Niveau": niveau,
        "Opleidingcode": crebo,
        "Leertraject": "BOL",
        "IndicatieBekostigbaar": bekostigbaar,
        "DIP_DatumResultaat": diploma,
        "_inschrijving_periode_id": f"{levering}|{persoon}|{nr}|{begin}",
    }


def _inschrijvingen(*perioden: dict) -> pl.DataFrame:
    return pl.DataFrame(
        list(perioden),
        schema_overrides={
            "DatumEind": pl.Date,
            "DatumUitschrijvingWerkelijk": pl.Date,
            "DIP_DatumResultaat": pl.Date,
        },
    )


def _leveringen(**peilgrenzen: date | None) -> pl.DataFrame:
    namen = peilgrenzen or {"L": _PEILGRENS}
    return pl.DataFrame(
        {
            "levering": list(namen),
            "DatumEindePeriode": list(namen.values()),
            "DatumAanmaak": [None] * len(namen),
        },
        schema_overrides={"DatumEindePeriode": pl.Date, "DatumAanmaak": pl.Date},
    )


def _bouw(*perioden: dict, leveringen: pl.DataFrame | None = None) -> pl.DataFrame:
    return bouw_inschrijving_schooljaar(
        _inschrijvingen(*perioden),
        leveringen if leveringen is not None else _leveringen(),
    ).sort("_persoon_id", "BRIN", "Inschrijvingvolgnummer", "Schooljaar")


def _jaren(df: pl.DataFrame) -> list[int]:
    return df["Schooljaar"].to_list()


# ---------------------------------------------------------------------------
# Welke schooljaren (#193)
# ---------------------------------------------------------------------------


def test_periode_over_meerdere_jaren_telt_elk_gedekt_schooljaar():
    df = _bouw(
        _periode(date(2022, 1, 10)),
        _periode(date(2024, 11, 21)),
    )
    # 2022-01-10 t/m 2024-11-20 dekt 1-10-2022, 1-10-2023 en 1-10-2024.
    eerste = df.filter(pl.col("DatumBegin") == date(2022, 1, 10))
    assert _jaren(eerste) == [2022, 2023, 2024]


def test_start_na_peildatum_telt_pas_volgend_schooljaar():
    df = _bouw(_periode(date(2023, 10, 2), eind=date(2024, 12, 31)))
    assert _jaren(df) == [2024]


def test_peildatum_is_1_oktober_van_het_schooljaar():
    df = _bouw(_periode(date(2023, 8, 1), eind=date(2024, 7, 31)))
    assert df.select("Schooljaar", "Peildatum").rows() == [(2023, date(2023, 10, 1))]


def test_open_periode_loopt_tot_peildatum_van_levering():
    lev = _leveringen(L=date(2025, 11, 19))
    assert _jaren(_bouw(_periode(date(2023, 8, 1)), leveringen=lev)) == [
        2023,
        2024,
        2025,
    ]


def test_peildatum_levering_voor_1_oktober_telt_dat_jaar_niet():
    lev = _leveringen(L=date(2025, 9, 30))
    assert _jaren(_bouw(_periode(date(2023, 8, 1)), leveringen=lev)) == [2023, 2024]


def test_aanmaakdatum_is_peildatum_zonder_einde_periode():
    lev = pl.DataFrame(
        {
            "levering": ["L"],
            "DatumEindePeriode": [None],
            "DatumAanmaak": [date(2024, 11, 19)],
        },
        schema_overrides={"DatumEindePeriode": pl.Date},
    )
    assert _jaren(_bouw(_periode(date(2023, 8, 1)), leveringen=lev)) == [2023, 2024]


def test_open_periode_zonder_peildatum_alleen_startschooljaar():
    lev = _leveringen(L=None)
    assert _jaren(_bouw(_periode(date(2023, 8, 1)), leveringen=lev)) == [2023]


def test_uitschrijving_voor_peildatum_is_harde_grens():
    df = _bouw(_periode(date(2023, 8, 1), uitschrijving=date(2025, 9, 16)))
    assert _jaren(df) == [2023, 2024]


def test_einddatum_na_peildatum_levering_wordt_begrensd():
    lev = _leveringen(L=date(2025, 11, 19))
    df = _bouw(_periode(date(2025, 8, 1), eind=date(2027, 7, 31)), leveringen=lev)
    assert _jaren(df) == [2025]


def test_periode_zonder_peildatum_valt_weg():
    df = _bouw(_periode(date(2024, 8, 1), eind=date(2024, 9, 30)))
    assert df.is_empty()


# ---------------------------------------------------------------------------
# Hoofdinschrijving per persoon × BRIN × schooljaar
# ---------------------------------------------------------------------------


def _hoofd(df: pl.DataFrame) -> dict[tuple[str, int], bool]:
    return {
        (r["Inschrijvingvolgnummer"], r["Schooljaar"]): r["_hoofdinschrijving"]
        for r in df.iter_rows(named=True)
    }


def test_hoogste_niveau_wordt_hoofdinschrijving():
    df = _bouw(
        _periode(date(2024, 8, 1), nr="1", niveau="MBO-3", eind=date(2025, 7, 31)),
        _periode(date(2024, 8, 1), nr="2", niveau="MBO-4", eind=date(2025, 7, 31)),
    )
    assert _hoofd(df) == {("1", 2024): False, ("2", 2024): True}


def test_gelijk_niveau_laagste_crebo_wint():
    df = _bouw(
        _periode(date(2024, 8, 1), nr="1", crebo="25999", eind=date(2025, 7, 31)),
        _periode(date(2024, 8, 1), nr="2", crebo="25001", eind=date(2025, 7, 31)),
    )
    assert _hoofd(df) == {("1", 2024): False, ("2", 2024): True}


def test_een_hoofdinschrijving_over_leveringen_heen():
    """Na canonicalisatie kunnen inschrijvingen uit verschillende leveringen komen."""
    lev = _leveringen(L_a=_PEILGRENS, L_b=_PEILGRENS)
    df = _bouw(
        _periode(date(2024, 8, 1), levering="L_a", nr="1", eind=date(2025, 7, 31)),
        _periode(date(2024, 8, 1), levering="L_b", nr="2", eind=date(2025, 7, 31)),
        leveringen=lev,
    )
    assert df["_hoofdinschrijving"].sum() == 1


def test_andere_instelling_eigen_hoofdinschrijving():
    df = _bouw(
        _periode(date(2024, 8, 1), brin="21CY", eind=date(2025, 7, 31)),
        _periode(date(2024, 8, 1), brin="27DV", eind=date(2025, 7, 31)),
    )
    assert df["_hoofdinschrijving"].to_list() == [True, True]


def test_hoofdinschrijving_per_schooljaar_opnieuw_gekozen():
    df = _bouw(
        _periode(date(2023, 8, 1), nr="1", niveau="MBO-4", eind=date(2024, 7, 31)),
        _periode(date(2023, 8, 1), nr="2", niveau="MBO-3", eind=date(2025, 7, 31)),
    )
    assert _hoofd(df) == {("1", 2023): True, ("2", 2023): False, ("2", 2024): True}


# ---------------------------------------------------------------------------
# Telling, bekostiging, JR (#194)
# ---------------------------------------------------------------------------


def test_telling_is_hoofdinschrijving():
    df = _bouw(
        _periode(date(2024, 8, 1), nr="1", niveau="MBO-3", eind=date(2025, 7, 31)),
        _periode(date(2024, 8, 1), nr="2", niveau="MBO-4", eind=date(2025, 7, 31)),
    )
    assert df["_telling"].to_list() == df["_hoofdinschrijving"].to_list()


def test_bekostigd_volgt_indicatie_van_de_periode():
    df = _bouw(_periode(date(2024, 8, 1), bekostigbaar="N", eind=date(2025, 7, 31)))
    assert df["_bekostigd"].to_list() == [False]


@pytest.mark.parametrize(
    ("diploma", "verwacht"),
    [
        (date(2025, 7, 7), True),  # binnen schooljaar 2024
        (date(2024, 8, 1), True),  # eerste dag schooljaar 2024
        (date(2025, 7, 31), True),  # laatste dag schooljaar 2024
        (date(2024, 7, 31), False),  # schooljaar 2023
        (date(2025, 8, 1), False),  # schooljaar 2025
    ],
)
def test_jr_diplomavenster_is_het_schooljaar_zelf(diploma, verwacht):
    df = _bouw(
        _periode(date(2024, 5, 7), uitschrijving=date(2025, 7, 7), diploma=diploma)
    )
    rij = df.filter(pl.col("Schooljaar") == 2024)
    assert rij.select("_gediplomeerd_in_jaar", "_jr_noemer", "_jr_teller").row(0) == (
        verwacht,
        True,
        verwacht,
    )


def test_jr_teller_alleen_voor_hoofdinschrijving():
    df = _bouw(
        _periode(date(2024, 8, 1), nr="1", niveau="MBO-3", diploma=date(2025, 6, 1)),
        _periode(date(2024, 8, 1), nr="2", niveau="MBO-4", eind=date(2025, 7, 31)),
    )
    teller = df.filter(pl.col("Schooljaar") == 2024)["_jr_teller"].to_list()
    assert teller == [False, False]


# ---------------------------------------------------------------------------
# DR: uitstroom alleen als het volgende schooljaar waarneembaar is
# ---------------------------------------------------------------------------


def _dr(df: pl.DataFrame) -> dict[int, tuple[bool, bool]]:
    return {
        r["Schooljaar"]: (r["_dr_noemer"], r["_dr_teller"])
        for r in df.iter_rows(named=True)
    }


def test_uitstromer_zonder_inschrijving_volgend_schooljaar():
    df = _bouw(
        _periode(
            date(2023, 8, 1), uitschrijving=date(2024, 7, 31), diploma=date(2024, 7, 1)
        )
    )
    assert _dr(df) == {2023: (True, True)}


def test_doorlopende_inschrijving_is_geen_uitstromer():
    df = _bouw(_periode(date(2023, 8, 1), uitschrijving=date(2025, 7, 31)))
    assert _dr(df) == {2023: (False, False), 2024: (True, False)}


def test_laatste_waarneembare_schooljaar_is_geen_uitstroom():
    """Of iemand in t+1 nog staat ingeschreven, kan de levering niet weten."""
    lev = _leveringen(L=date(2025, 11, 19))
    df = _bouw(_periode(date(2024, 8, 1)), leveringen=lev)
    assert _dr(df) == {2024: (False, False), 2025: (False, False)}


def test_dr_alleen_vanaf_niveau_2():
    df = _bouw(
        _periode(date(2023, 8, 1), niveau="MBO-1", uitschrijving=date(2024, 7, 31))
    )
    assert _dr(df) == {2023: (False, False)}


# ---------------------------------------------------------------------------
# Star-output op de demo
# ---------------------------------------------------------------------------


def test_demo_grain_is_uniek(demo_star):
    feit = demo_star["fact_inschrijving_schooljaar"]
    sleutel = ["BRIN", "_persoon_id", "Inschrijvingvolgnummer", "Schooljaar"]
    assert feit.height > 0
    assert not feit.select(sleutel).is_duplicated().any()


def test_demo_precies_een_hoofdinschrijving_per_persoon_instelling_schooljaar(
    demo_star,
):
    per_groep = (
        demo_star["fact_inschrijving_schooljaar"]
        .group_by("BRIN", "_persoon_id", "Schooljaar")
        .agg(pl.col("_hoofdinschrijving").sum().alias("n"))
    )
    assert per_groep["n"].unique().to_list() == [1]


def test_demo_heeft_positieve_jr_teller(demo_star):
    """Regressie #194: de demo bevat gediplomeerden die in hun schooljaar tellen."""
    assert demo_star["fact_inschrijving_schooljaar"]["_jr_teller"].sum() > 0


def test_demo_periode_fk_bestaat_in_fact_inschrijving(demo_star):
    jaren = demo_star["fact_inschrijving_schooljaar"]
    perioden = demo_star["fact_inschrijving"]
    wees = jaren.join(perioden, on="_inschrijving_periode_id", how="anti")
    assert wees.is_empty()


def test_tbgi_only_inschrijving_is_de_periode(tbgi_star):
    """Zonder ISP telt de TBGI-inschrijving vanaf DatumInschrijving (geen VLP)."""
    jaren = tbgi_star["fact_inschrijving_schooljaar"]
    assert jaren.height > 0
    assert not jaren.join(
        tbgi_star["fact_inschrijving"], on="_inschrijving_periode_id", how="anti"
    ).height
