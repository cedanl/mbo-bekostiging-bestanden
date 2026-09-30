"""Meervoudige matches bij links-joins: een vaste regel per koppeling (#209, #239).

Voorheen koos ``_join_left`` stil de eerste rij in bestandsvolgorde; sinds #209
is de keuze deterministisch. Sinds #239 heeft elke koppeling een declaratieve
regel in ``KOPPELREGELS``: ``uniek`` (het PvE staat hoogstens één kandidaat
toe, een tweede is een bronfout), ``hoogste`` (de voorkeurkolom wint) of
``ambigu`` (geen businessregel; deterministisch op inhoud). De regel en haar
reden staan in ``meta_koppelkeuzes`` en ``quality.json``.
"""

from datetime import date

import polars as pl
import pytest

from mbo_bekostiging_bestanden.koppelingen import (
    AMBIGU,
    HOOGSTE,
    KOPPELREGELS,
    UNIEK,
    Koppelingen,
    Koppelregel,
)
from mbo_bekostiging_bestanden.quality import compile_quality_report

LINKS = pl.DataFrame({"k": ["a", "b", "c"]})
RECHTS = pl.DataFrame(
    {
        "k": ["a", "a", "b"],
        "d": [date(2024, 1, 1), date(2025, 1, 1), date(2023, 1, 1)],
    }
)
_NIEUWSTE = Koppelregel(HOOGSTE, "test: nieuwste datum", voorkeur=("d",))
_AMBIGU = Koppelregel(AMBIGU, "test: geen businessregel")
_UNIEK = Koppelregel(UNIEK, "test: PvE staat één kandidaat toe")


def test_hoogste_kiest_de_meest_recente_ongeacht_rijvolgorde():
    for rechts in (RECHTS, RECHTS.reverse()):
        uit = Koppelingen().links(LINKS, rechts, on=["k"], naam="X", regel=_NIEUWSTE)
        assert uit.height == LINKS.height
        assert uit.filter(pl.col("k") == "a")["d"].item() == date(2025, 1, 1)


def test_ambigu_is_rijvolgorde_onafhankelijk():
    vooruit = Koppelingen().links(LINKS, RECHTS, on=["k"], naam="X", regel=_AMBIGU)
    achteruit = Koppelingen().links(
        LINKS, RECHTS.reverse(), on=["k"], naam="X", regel=_AMBIGU
    )
    assert vooruit.equals(achteruit)


def test_hoogste_zonder_voorkeur_kan_niet():
    with pytest.raises(ValueError, match="voorkeur"):
        Koppelregel(HOOGSTE, "zonder kolom")


def test_onbekende_soort_regel_kan_niet():
    with pytest.raises(ValueError, match="soort"):
        Koppelregel("eerste", "rijvolgorde")


def test_koppeling_zonder_regel_faalt():
    with pytest.raises(KeyError, match="ONBEKEND"):
        Koppelingen().links(LINKS, RECHTS, on=["k"], naam="ONBEKEND")


def test_overzicht_noemt_regel_en_reden_en_telt_per_koppeling():
    koppelingen = Koppelingen()
    koppelingen.links(LINKS, RECHTS, on=["k"], naam="A", regel=_NIEUWSTE)
    koppelingen.links(LINKS, RECHTS.unique("k"), on=["k"], naam="B", regel=_UNIEK)
    overzicht = {
        r["koppeling"]: r for r in koppelingen.overzicht().iter_rows(named=True)
    }
    assert overzicht["A"] == {
        "koppeling": "A",
        "sleutel": "k",
        "regel": HOOGSTE,
        "toelichting": "test: nieuwste datum",
        "meervoudige_sleutels": 1,
        "weggelaten_rijen": 1,
    }
    assert overzicht["B"]["meervoudige_sleutels"] == 0


def test_alleen_sleutels_die_links_voorkomen_tellen():
    """Een dubbele kandidaat voor een sleutel die links ontbreekt, is geen keuze."""
    rechts = pl.DataFrame({"k": ["z", "z"], "d": [date(2024, 1, 1)] * 2})
    koppelingen = Koppelingen()
    koppelingen.links(LINKS, rechts, on=["k"], naam="X", regel=_AMBIGU)
    assert koppelingen.overzicht()["meervoudige_sleutels"].to_list() == [0]


def test_elke_koppeling_in_de_ster_heeft_een_geregistreerde_regel(demo_star):
    keuzes = demo_star["meta_koppelkeuzes"]
    assert keuzes.height > 0
    assert set(keuzes["koppeling"]) <= set(KOPPELREGELS)
    assert keuzes["toelichting"].null_count() == 0
    assert keuzes["meervoudige_sleutels"].sum() == 0


def _rapport(regel: str) -> dict:
    star = {
        "meta_koppelkeuzes": pl.DataFrame(
            {
                "koppeling": ["DIP"],
                "sleutel": ["levering, _persoon_id, Inschrijvingvolgnummer"],
                "regel": [regel],
                "toelichting": ["waarom"],
                "meervoudige_sleutels": [2],
                "weggelaten_rijen": [3],
            }
        )
    }
    return compile_quality_report(star)


@pytest.mark.parametrize(
    ("regel", "status"), [(HOOGSTE, "warn"), (AMBIGU, "warn"), (UNIEK, "fail")]
)
def test_quality_ernst_volgt_de_regel(regel, status):
    """Bij ``uniek`` is een tweede kandidaat een schending van het PvE."""
    rapport = _rapport(regel)
    assert rapport["star"]["join_keuzes"][0]["regel"] == regel
    assert rapport["summary"]["status"] == status
