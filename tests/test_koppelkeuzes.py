"""Meervoudige matches bij links-joins worden deterministisch opgelost en gemeld (#209).

Voorheen koos ``_join_left`` stil de eerste rij in bestandsvolgorde. Nu is de
keuze inhoudelijk vastgelegd (``voorkeur``) of anders op inhoud gesorteerd, en
telt het overzicht per koppeling hoeveel sleutels meer dan één kandidaat hadden.
"""

from datetime import date

import polars as pl

from mbo_bekostiging_bestanden.koppelingen import Koppelingen
from mbo_bekostiging_bestanden.quality import compile_quality_report

LINKS = pl.DataFrame({"k": ["a", "b", "c"]})
RECHTS = pl.DataFrame(
    {
        "k": ["a", "a", "b"],
        "d": [date(2024, 1, 1), date(2025, 1, 1), date(2023, 1, 1)],
    }
)


def test_voorkeur_kiest_meest_recente_ongeacht_rijvolgorde():
    for rechts in (RECHTS, RECHTS.reverse()):
        uit = Koppelingen().links(LINKS, rechts, on=["k"], naam="DIP", voorkeur=["d"])
        assert uit.height == LINKS.height
        assert uit.filter(pl.col("k") == "a")["d"].item() == date(2025, 1, 1)


def test_zonder_voorkeur_is_de_keuze_rijvolgorde_onafhankelijk():
    vooruit = Koppelingen().links(LINKS, RECHTS, on=["k"], naam="X")
    achteruit = Koppelingen().links(LINKS, RECHTS.reverse(), on=["k"], naam="X")
    assert vooruit.equals(achteruit)


def test_overzicht_telt_meervoudige_sleutels_per_koppeling():
    koppelingen = Koppelingen()
    koppelingen.links(LINKS, RECHTS, on=["k"], naam="DIP", voorkeur=["d"])
    koppelingen.links(LINKS, RECHTS.unique("k"), on=["k"], naam="ISG")
    overzicht = {
        r["koppeling"]: r for r in koppelingen.overzicht().iter_rows(named=True)
    }
    assert overzicht["DIP"]["meervoudige_sleutels"] == 1
    assert overzicht["DIP"]["weggelaten_rijen"] == 1
    assert overzicht["ISG"]["meervoudige_sleutels"] == 0


def test_alleen_sleutels_die_links_voorkomen_tellen():
    """Een dubbele kandidaat voor een sleutel die links ontbreekt, is geen keuze."""
    rechts = pl.DataFrame({"k": ["z", "z"], "d": [date(2024, 1, 1)] * 2})
    koppelingen = Koppelingen()
    koppelingen.links(LINKS, rechts, on=["k"], naam="X")
    assert koppelingen.overzicht()["meervoudige_sleutels"].to_list() == [0]


def test_demo_star_heeft_koppelkeuzes_zonder_meervoudige_matches(demo_star):
    keuzes = demo_star["meta_koppelkeuzes"]
    assert keuzes.height > 0
    assert keuzes["meervoudige_sleutels"].sum() == 0


def test_quality_meldt_meervoudige_match_als_warning():
    star = {
        "meta_koppelkeuzes": pl.DataFrame(
            {
                "koppeling": ["DIP"],
                "sleutel": ["levering, _persoon_id, Inschrijvingvolgnummer"],
                "meervoudige_sleutels": [2],
                "weggelaten_rijen": [3],
            }
        )
    }
    rapport = compile_quality_report(star)
    assert rapport["star"]["join_keuzes"] == [
        {
            "koppeling": "DIP",
            "sleutel": "levering, _persoon_id, Inschrijvingvolgnummer",
            "meervoudige_sleutels": 2,
            "weggelaten_rijen": 3,
        }
    ]
    assert rapport["summary"]["total_warnings"] == 1
