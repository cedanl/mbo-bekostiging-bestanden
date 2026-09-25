"""Tests voor de hoofdinschrijving-selectie (issue #117, #144).

Per persoon × schooljaar (peildatum) × levering × instelling hoort precies één
hoofdinschrijving uit de periodes die op 1 oktober actief zijn: hoogste niveau,
dan laagste CREBO, dan meest recente ``DatumBegin``.
"""

from datetime import date

import polars as pl

from mbo_bekostiging_bestanden.transform import (
    _bepaal_actief_per_schooljaar,
    _voeg_sr_vlaggen_toe,
)


def _isp_met_periodes(
    *rijen: tuple[str, str, str, str, date, date | None],
) -> pl.DataFrame:
    """ISP-rijen met periodes: (levering, BRIN, niveau, crebo, begin, eind)."""
    return pl.DataFrame(
        {
            "levering": [r[0] for r in rijen],
            "BRIN": [r[1] for r in rijen],
            "_persoon_id": ["P"] * len(rijen),
            "Inschrijvingvolgnummer": [str(i + 1) for i in range(len(rijen))],
            "Studiejaar": [2025] * len(rijen),
            "Niveau": [r[2] for r in rijen],
            "Opleidingcode": [r[3] for r in rijen],
            "DatumBegin": [r[4] for r in rijen],
            "DatumEind": [r[5] for r in rijen],
            "IndicatieBekostigbaar": ["J"] * len(rijen),
            "DatumInschrijving": [date(2023, 8, 1)] * len(rijen),
            "DatumUitschrijvingWerkelijk": [None] * len(rijen),
        },
        schema_overrides={"DatumEind": pl.Date, "DatumUitschrijvingWerkelijk": pl.Date},
    )


def _hoofd(df: pl.DataFrame) -> list[bool]:
    """Voer volledige pipeline uit: actief per schooljaar → hoofdinschrijving."""
    df = _bepaal_actief_per_schooljaar(df)
    return _voeg_sr_vlaggen_toe(df)["_hoofdinschrijving"].to_list()


def test_oudere_kandidaat_wordt_toch_hoofdinschrijving():
    """Oudere kandidaat met hoger niveau wint als beide periodes
    actief op 1-okt-2025."""
    df = _isp_met_periodes(
        ("L", "A", "MBO-4", "40000", date(2024, 8, 1), date(2025, 10, 15)),
        ("L", "A", "MBO-3", "30000", date(2025, 8, 1), None),
    )
    assert _hoofd(df) == [True, False]


def test_gelijke_kandidaten_meest_recente_wint():
    """Bij gelijke niveau en CREBO wint meest recente DatumBegin."""
    df = _isp_met_periodes(
        ("L", "A", "MBO-4", "40000", date(2024, 8, 1), date(2025, 9, 15)),
        ("L", "A", "MBO-4", "40000", date(2025, 2, 1), None),
    )
    assert _hoofd(df) == [False, True]


def test_gelijke_datums_geven_precies_een_hoofdinschrijving():
    """Bij identieke periodes wordt er precies één gekozen (deterministisch)."""
    df = _isp_met_periodes(
        ("L", "A", "MBO-4", "40000", date(2024, 8, 1), date(2025, 10, 15)),
        ("L", "A", "MBO-4", "40000", date(2024, 8, 1), date(2025, 10, 15)),
    )
    assert sum(_hoofd(df)) == 1


def test_elke_instelling_heeft_eigen_hoofdinschrijving():
    """Per BRIN wordt een eigen hoofdinschrijving gekozen."""
    df = _isp_met_periodes(
        ("L", "A", "MBO-4", "40000", date(2024, 8, 1), date(2025, 10, 15)),
        ("L", "B", "MBO-2", "20000", date(2025, 8, 1), None),
    )
    assert _hoofd(df) == [True, True]


def test_elke_levering_heeft_eigen_hoofdinschrijving():
    """Een hoger niveau in levering L1 mag L2 niet zonder hoofdinschrijving laten."""
    df = _isp_met_periodes(
        ("L1", "A", "MBO-4", "40000", date(2024, 8, 1), date(2025, 10, 15)),
        ("L2", "A", "MBO-3", "30000", date(2025, 8, 1), None),
    )
    assert _hoofd(df) == [True, True]


def test_zonder_datumbegin_telt_niveau_en_crebo():
    """Zonder DatumBegin kan geen actieve periode bepaald worden
    -> geen hoofdinschrijving."""
    df = _isp_met_periodes(
        ("L", "A", "MBO-4", "40000", date(2024, 8, 1), date(2025, 9, 15)),
        ("L", "A", "MBO-4", "30000", date(2024, 8, 1), date(2025, 9, 15)),
    ).drop("DatumBegin")
    assert _hoofd(df) == [False, False]


def test_demo_star_heeft_precies_een_hoofdinschrijving_per_groep(demo_star, demo_tabellen):
    """Precies één per groep met een actieve periode op 1 oktober (#117, #144).

    Groepeert per (levering, BRIN, _persoon_id, schooljaar_peildatum) door
    _schooljaren_actief te exploderen (uit de transform-laag, niet uit star).

    _schooljaren_actief is een interne kolom en wordt uit de ster verwijderd (#171).
    We testen de invariant via de prepared inschrijvingen-tabel.
    """
    # Neem inschrijvingen uit analysetabellen (bevat _schooljaren_actief)
    inschrijvingen = demo_tabellen["inschrijvingen"]
    fact = demo_star["fact_inschrijving"]

    # Explodeer _schooljaren_actief om per schooljaar te groeperen
    inschrijvingen_exploded = inschrijvingen.explode("_schooljaren_actief").rename(
        {"_schooljaren_actief": "_schooljaar_peildatum"}
    )

    # Map naar star met behoud van hoofdinschrijving-indicator
    fact_exploded = inschrijvingen_exploded.join(
        fact.select("_inschrijving_periode_id", "_hoofdinschrijving"),
        on="_inschrijving_periode_id",
        how="inner",
    )

    groep = ["levering", "BRIN", "_persoon_id", "_schooljaar_peildatum"]
    per_groep = (
        fact_exploded.group_by(groep)
        .agg(
            pl.col("_hoofdinschrijving").sum().alias("n"),
            pl.col("_actief_1_oktober").any().alias("heeft_actief"),
        )
    )
    actieve_groepen = per_groep.filter(pl.col("heeft_actief"))
    assert actieve_groepen["n"].to_list() == [1] * actieve_groepen.height
    inactieve_groepen = per_groep.filter(~pl.col("heeft_actief"))
    assert inactieve_groepen["n"].to_list() == [0] * inactieve_groepen.height
