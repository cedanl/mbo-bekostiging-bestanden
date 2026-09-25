"""Snapshot test voor demo-star indicatoruitkomsten (#147).

Deze test vastlegt de verwachte aantallen per indicator en per star-tabel
op de demo-data. Dit is een CONTRACT: elke wijziging aan indicator-logica
moet bewust en gedomineerd zijn, niet ongemerkt door een test die 'about equal' checkt.

De baseline is main e022f05 (voor PR #150 herontwerp).
"""

import json
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.stack import stack_prepared
from mbo_bekostiging_bestanden.star import build_star

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "demo_snapshot_main_baseline.json"

INDICATOR_COLS = [
    "_actief_1_oktober",
    "_hoofdinschrijving",
    "_telling",
    "_jr_noemer",
    "_jr_teller",
    "_dr_noemer",
    "_dr_teller",
    "_bekostigd_eerste_1okt",
]

TABLE_NAMES = [
    "dim_deelnemer",
    "dim_opleiding",
    "dim_instelling",
    "fact_inschrijving",
    "fact_bpv",
    "fact_kzd",
    "fact_amo",
    "fact_geo",
    "fact_bekostiging",
    "fact_bekostiging_diploma",
    "meta_leveringen",
]


@pytest.fixture(scope="session")
def demo_star_snapshot():
    """Bouw het demo-star schema (session-scoped voor snelheid)."""
    with open(FIXTURE_PATH) as f:
        expected = json.load(f)

    prepared_dir = Path("data/02-prepared/demo")
    sources = []
    for h in ["h15", "h16", "h17"]:
        h_dir = prepared_dir / h
        if h_dir.exists():
            for lev_dir in sorted(h_dir.iterdir()):
                if lev_dir.is_dir() and not lev_dir.name.startswith("."):
                    sources.append(lev_dir)

    stacked = stack_prepared(sources)
    star = build_star(stacked)
    return star, expected


def test_indicator_totals_match_snapshot(demo_star_snapshot):
    """Totaal aantallen per indicator moeten exact overeenkomen met fixture."""
    star, expected = demo_star_snapshot
    fact = star["fact_inschrijving"]

    for col in INDICATOR_COLS:
        if col not in fact.columns:
            pytest.skip(f"Kolom {col} niet in fact_inschrijving")
        actual_true = fact.filter(pl.col(col)).height
        actual_total = fact.height
        exp_true = expected["indicators"][col]["true"]
        exp_total = expected["indicators"][col]["total"]

        assert actual_total == exp_total, (
            f"{col}: totaal {actual_total} != {exp_total} (fixture)"
        )
        assert actual_true == exp_true, (
            f"{col}: true {actual_true} != {exp_true} (fixture)"
        )


def test_table_row_counts_match_snapshot(demo_star_snapshot):
    """Rijaantallen per star-tabel moeten exact overeenkomen."""
    star, expected = demo_star_snapshot

    for table_name in TABLE_NAMES:
        if table_name not in star:
            pytest.skip(f"Tabel {table_name} niet in star output")
        actual = star[table_name].height
        exp = expected["tables"][table_name]
        assert actual == exp, (
            f"{table_name}: {actual} rijen != {exp} (fixture)"
        )


def test_per_levering_indicators_match_snapshot(demo_star_snapshot):
    """Indicatoraantallen per levering moeten exact overeenkomen."""
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

        for col in INDICATOR_COLS:
            if col not in lev_fact.columns:
                continue
            actual_true = lev_fact.filter(pl.col(col)).height
            exp_true = lev_expected[col]
            assert actual_true == exp_true, (
                f"{lev_name}.{col}: true {actual_true} != {exp_true} (fixture)"
            )


def test_snapshot_has_all_required_keys():
    """Valideer dat de fixture alle verwachte keys bevat."""
    with open(FIXTURE_PATH) as f:
        data = json.load(f)

    assert "metadata" in data
    assert "indicators" in data
    assert "tables" in data
    assert "per_levering" in data

    for col in INDICATOR_COLS:
        assert col in data["indicators"], f"Ontbrekende indicator in fixture: {col}"
        assert "true" in data["indicators"][col]
        assert "total" in data["indicators"][col]

    for table in TABLE_NAMES:
        assert table in data["tables"], f"Ontbrekende tabel in fixture: {table}"

    # Combinatie van alle leveringen in per_levering moet
    # totaal fact_inschrijving rijen opleveren
    total_rows = sum(v["rows"] for v in data["per_levering"].values())
    assert total_rows == data["tables"]["fact_inschrijving"], (
        f"Som per_levering rijen ({total_rows}) != fact_inschrijving totaal "
        f"({data['tables']['fact_inschrijving']})"
    )