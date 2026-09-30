"""Guard: de app gebruikt geen verouderde jaarvlaggen uit fact_inschrijving (#370).

De kolommen in ``contracts.VEROUDERDE_KOLOMMEN`` verdwijnen in
``VEROUDERD_TOT`` (#201). Een deel (``_telling``, ``_jr_*``, ``_dr_*``, …)
bestaat onder dezelfde naam in ``fact_inschrijving_schooljaar``, waar de app
ze terecht leest; een naamscan kan die niet onderscheiden. Voor die namen
bewijst ``test_dashboard_jaren.test_dashboard_leest_geen_verouderde_kolommen``
het gedrag op een ster zonder legacy-kolommen. Deze scan dekt de rest: namen
die alleen in de periode-fact bestaan, dus elk gebruik is legacy.
"""

import ast
from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.contracts import SCHOOLJAAR_FEIT, VEROUDERDE_KOLOMMEN

APP = Path(__file__).parents[1] / "app"

# Bestand → verouderde kolom → reden. Leeg houden; een nieuwe uitzondering
# verwijst naar #201.
UITZONDERINGEN: dict[str, dict[str, str]] = {}


@pytest.fixture(scope="module")
def alleen_legacy(demo_star) -> set[str]:
    return set(VEROUDERDE_KOLOMMEN) - set(demo_star[SCHOOLJAAR_FEIT].columns)


def _gebruikte_strings(bron: str) -> set[str]:
    """String-constanten in code; docstrings en comments tellen niet."""
    boom = ast.parse(bron)
    docstrings = {
        id(knoop.body[0].value)
        for knoop in ast.walk(boom)
        if isinstance(
            knoop, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
        )
        and knoop.body
        and isinstance(knoop.body[0], ast.Expr)
        and isinstance(knoop.body[0].value, ast.Constant)
    }
    return {
        knoop.value
        for knoop in ast.walk(boom)
        if isinstance(knoop, ast.Constant)
        and isinstance(knoop.value, str)
        and id(knoop) not in docstrings
    }


def test_er_zijn_kolommen_die_alleen_legacy_zijn(alleen_legacy):
    """Zonder deze namen zou de scan hieronder niets bewaken."""
    assert alleen_legacy


def test_app_gebruikt_geen_verouderde_kolommen(alleen_legacy):
    overtredingen = {
        str(bestand.relative_to(APP.parent)): sorted(gevonden)
        for bestand in sorted(APP.rglob("*.py"))
        if (
            gevonden := (
                _gebruikte_strings(bestand.read_text(encoding="utf-8")) & alleen_legacy
            )
            - set(UITZONDERINGEN.get(str(bestand.relative_to(APP.parent)), {}))
        )
    }
    assert overtredingen == {}, (
        "Gebruik fact_inschrijving_schooljaar; deze kolommen verdwijnen in v4.0.0 "
        f"(#201): {overtredingen}"
    )


def test_scan_ziet_een_expres_toegevoegd_gebruik(alleen_legacy):
    kolom = sorted(alleen_legacy)[0]
    bron = f'df.filter(pl.col("{kolom}"))\n'
    assert kolom in _gebruikte_strings(bron)


def test_scan_negeert_docstrings(alleen_legacy):
    kolom = sorted(alleen_legacy)[0]
    bron = f'"""{kolom}"""\n\n\nclass C:\n    """{kolom}"""\n'
    assert _gebruikte_strings(bron) == set()
