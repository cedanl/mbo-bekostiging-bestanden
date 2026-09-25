"""Tests voor de hoofdinschrijving-selectie (issue #117, #144).

Per persoon × studiejaar × levering × instelling hoort precies één
hoofdinschrijving uit de perioden die op 1 oktober actief zijn: hoogste niveau,
dan laagste CREBO, dan meest recente ``DatumBegin``.
"""

from datetime import date

import polars as pl

from mbo_bekostiging_bestanden.transform import _voeg_sr_vlaggen_toe


def _isp(*rijen: tuple[str, str, str, str, date]) -> pl.DataFrame:
    """ISP-rijen voor P in 2025: (levering, BRIN, niveau, crebo, begin)."""
    return pl.DataFrame(
        {
            "levering": [r[0] for r in rijen],
            "BRIN": [r[1] for r in rijen],
            "_persoon_id": ["P"] * len(rijen),
            "Studiejaar": [2025] * len(rijen),
            "Niveau": [r[2] for r in rijen],
            "Opleidingcode": [r[3] for r in rijen],
            "DatumBegin": [r[4] for r in rijen],
        }
    )


def _hoofd(df: pl.DataFrame) -> list[bool]:
    return _voeg_sr_vlaggen_toe(df)["_hoofdinschrijving"].to_list()


def test_oudere_kandidaat_wordt_toch_hoofdinschrijving():
    df = _isp(
        ("L", "A", "MBO-4", "40000", date(2024, 8, 1)),
        ("L", "A", "MBO-3", "30000", date(2025, 8, 1)),
    )
    assert _hoofd(df) == [True, False]


def test_gelijke_kandidaten_meest_recente_wint():
    df = _isp(
        ("L", "A", "MBO-4", "40000", date(2024, 8, 1)),
        ("L", "A", "MBO-4", "40000", date(2025, 2, 1)),
    )
    assert _hoofd(df) == [False, True]


def test_gelijke_datums_geven_precies_een_hoofdinschrijving():
    df = _isp(
        ("L", "A", "MBO-4", "40000", date(2024, 8, 1)),
        ("L", "A", "MBO-4", "40000", date(2024, 8, 1)),
    )
    assert sum(_hoofd(df)) == 1


def test_elke_instelling_heeft_eigen_hoofdinschrijving():
    df = _isp(
        ("L", "A", "MBO-4", "40000", date(2024, 8, 1)),
        ("L", "B", "MBO-2", "20000", date(2025, 8, 1)),
    )
    assert _hoofd(df) == [True, True]


def test_elke_levering_heeft_eigen_hoofdinschrijving():
    """Een hoger niveau in levering L1 mag L2 niet zonder hoofdinschrijving laten."""
    df = _isp(
        ("L1", "A", "MBO-4", "40000", date(2024, 8, 1)),
        ("L2", "A", "MBO-3", "30000", date(2025, 8, 1)),
    )
    assert _hoofd(df) == [True, True]


def test_zonder_datumbegin_telt_niveau_en_crebo():
    df = _isp(
        ("L", "A", "MBO-4", "40000", date(2024, 8, 1)),
        ("L", "A", "MBO-4", "30000", date(2024, 8, 1)),
    ).drop("DatumBegin")
    assert _hoofd(df) == [False, True]


def test_demo_star_heeft_een_hoofdinschrijving_per_groep_met_actieve_periode(
    demo_star,
):
    """Precies één per groep met een periode op 1 oktober, anders geen (#144)."""
    groep = ["levering", "BRIN", "_persoon_id", "Studiejaar"]
    per_groep = (
        demo_star["fact_inschrijving"]
        .group_by(groep)
        .agg(
            pl.col("_hoofdinschrijving").sum().alias("n"),
            pl.col("_actief_1_oktober").fill_null(True).any().alias("actief"),
        )
    )
    verwacht = per_groep["actief"].cast(pl.UInt32).to_list()
    assert per_groep["n"].to_list() == verwacht
