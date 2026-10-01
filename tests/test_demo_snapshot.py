"""Snapshot van de demo-ster: rijen per tabel en indicatoren per schooljaar (#147).

Een contract: elke wijziging in de indicatorlogica of de rijtellingen moet een
bewuste aanpassing van de fixture zijn, niet een test die "ongeveer gelijk"
accepteert. De indicatoren staan sinds #201 alleen op de schooljaar-grain.
"""

import json
from pathlib import Path

import polars as pl
import pytest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "demo_snapshot_main_baseline.json"


TABLE_NAMES = [
    "dim_deelnemer",
    "dim_opleiding",
    "dim_instelling",
    "fact_inschrijving",
    "fact_inschrijving_schooljaar",
    "fact_bpv",
    "fact_kzd",
    "fact_amo",
    "fact_geo",
    "fact_bekostiging",
    "fact_bekostiging_diploma",
    "meta_leveringen",
    "meta_canonicalisatie",
]

SCHOOLJAAR_COLS = [
    "_telling",
    "_bekostigd",
    "_jr_noemer",
    "_jr_teller",
    "_dr_noemer",
    "_dr_teller",
]


@pytest.fixture(scope="session")
def demo_star_snapshot(demo_star):
    """De demo-ster naast de vastgelegde verwachting uit de fixture."""
    with open(FIXTURE_PATH) as f:
        expected = json.load(f)
    return demo_star, expected


def test_table_row_counts_match_snapshot(demo_star_snapshot):
    """Rijaantallen per star-tabel moeten exact overeenkomen."""
    star, expected = demo_star_snapshot

    for table_name in TABLE_NAMES:
        if table_name not in star:
            pytest.skip(f"Tabel {table_name} niet in star output")
        actual = star[table_name].height
        exp = expected["tables"][table_name]
        assert actual == exp, f"{table_name}: {actual} rijen != {exp} (fixture)"


def test_per_levering_rijen_match_snapshot(demo_star_snapshot):
    """Rijen per levering in fact_inschrijving moeten exact overeenkomen.

    De indicatoren staan sinds #201 alleen op de schooljaar-grain (zie
    :func:`test_schooljaar_indicatoren_match_snapshot`).
    """
    star, expected = demo_star_snapshot
    fact = star["fact_inschrijving"]

    if "levering" not in fact.columns:
        pytest.skip("Geen levering kolom in fact_inschrijving")

    for lev_name, lev_expected in expected["per_levering"].items():
        lev_fact = fact.filter(pl.col("levering") == lev_name)
        if lev_fact.is_empty():
            pytest.fail(f"Levering {lev_name} niet gevonden in fact_inschrijving")

        assert lev_fact.height == lev_expected["rows"], (
            f"{lev_name}: {lev_fact.height} rijen != {lev_expected['rows']} (fixture)"
        )


def test_snapshot_has_all_required_keys():
    """Valideer dat de fixture alle verwachte keys bevat."""
    with open(FIXTURE_PATH) as f:
        data = json.load(f)

    assert "metadata" in data
    assert "tables" in data
    assert "per_levering" in data
    assert "per_schooljaar" in data

    for table in TABLE_NAMES:
        assert table in data["tables"], f"Ontbrekende tabel in fixture: {table}"

    # Combinatie van alle leveringen in per_levering moet
    # totaal fact_inschrijving rijen opleveren
    total_rows = sum(v["rows"] for v in data["per_levering"].values())
    assert total_rows == data["tables"]["fact_inschrijving"], (
        f"Som per_levering rijen ({total_rows}) != fact_inschrijving totaal "
        f"({data['tables']['fact_inschrijving']})"
    )


def test_schooljaar_indicatoren_match_snapshot(demo_star_snapshot):
    """Rijen en indicatortotalen per schooljaar in fact_inschrijving_schooljaar."""
    star, expected = demo_star_snapshot
    actual = {
        str(r["Schooljaar"]): r
        for r in star["fact_inschrijving_schooljaar"]
        .group_by("Schooljaar")
        .agg(pl.len().alias("rows"), *[pl.col(c).sum() for c in SCHOOLJAAR_COLS])
        .iter_rows(named=True)
    }

    assert set(actual) == set(expected["per_schooljaar"])
    for jaar, verwacht in expected["per_schooljaar"].items():
        for kolom, waarde in verwacht.items():
            assert actual[jaar][kolom] == waarde, f"{jaar} {kolom}"
