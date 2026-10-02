"""Afhankelijkheidsrichting en modulegrenzen (``docs/architectuur.md``).

Een kwaliteitscontrole die de code importeert die ze beoordeelt, kan een fout
in die code niet onafhankelijk signaleren (#365). De scan volgt imports
transitief: ``quality → schooljaar → transform`` telt ook.

Een module gebruikt van een andere module alleen publieke namen (#198): een
private naam is geen contract en kan zonder waarschuwing veranderen.
"""

import ast
from pathlib import Path

import pytest

PACKAGE = "mbo_bekostiging_bestanden"
SRC = Path(__file__).parents[1] / "src" / PACKAGE

# De lagen die de ster bouwen; ``quality`` mag daar niet (indirect) van afhangen.
# identiteit hoort sinds #173 bij decode: de privacygrens ligt bij de brondata.
STERBOUW = {
    "transform",
    "perioden",
    "inschrijvingen",
    "opleidingsniveau",
    "details",
    "star",
    "schooljaar",
    "enrich",
}
APP = SRC.parents[1] / "app"


def _module_bestand(module: str) -> Path | None:
    pad = SRC.joinpath(*module.split("."))
    for kandidaat in (pad.with_suffix(".py"), pad / "__init__.py"):
        if kandidaat.exists():
            return kandidaat
    return None


def _package_imports(bron: str) -> set[str]:
    """Package-modules (zonder prefix) die ``bron`` importeert, ook binnen functies.

    Imports onder ``if TYPE_CHECKING`` tellen niet mee: die bestaan alleen
    voor de typechecker.
    """
    boom = ast.parse(bron)
    alleen_types = {
        id(knoop)
        for blok in ast.walk(boom)
        if isinstance(blok, ast.If) and "TYPE_CHECKING" in ast.unparse(blok.test)
        for knoop in ast.walk(blok)
    }
    gevonden: set[str] = set()
    for knoop in ast.walk(boom):
        if id(knoop) in alleen_types:
            continue
        if isinstance(knoop, ast.ImportFrom) and knoop.module:
            if knoop.module == PACKAGE:
                gevonden |= {alias.name for alias in knoop.names}
            elif knoop.module.startswith(f"{PACKAGE}."):
                gevonden.add(knoop.module.removeprefix(f"{PACKAGE}."))
        elif isinstance(knoop, ast.Import):
            gevonden |= {
                alias.name.removeprefix(f"{PACKAGE}.")
                for alias in knoop.names
                if alias.name.startswith(f"{PACKAGE}.")
            }
    return {m for m in gevonden if _module_bestand(m)}


def _afhankelijkheden(module: str) -> set[str]:
    bezocht: set[str] = set()
    te_doen = [module]
    while te_doen:
        huidig = te_doen.pop()
        bestand = _module_bestand(huidig)
        if huidig in bezocht or bestand is None:
            continue
        bezocht.add(huidig)
        te_doen.extend(_package_imports(bestand.read_text(encoding="utf-8")))
    return bezocht - {module}


def test_quality_hangt_niet_af_van_de_sterbouw():
    assert _afhankelijkheden("quality") & STERBOUW == set()


@pytest.mark.parametrize(
    "bron",
    [
        f"from {PACKAGE}.transform import BRON",
        f"from {PACKAGE} import star",
        f"import {PACKAGE}.schooljaar",
        f"def f():\n    from {PACKAGE}.transform import BRON",
    ],
)
def test_scan_ziet_een_verboden_import(bron):
    """De scan zelf: een expres toegevoegde import moet opvallen."""
    assert _package_imports(bron) & STERBOUW


def test_scan_negeert_imports_voor_de_typechecker():
    bron = f"if TYPE_CHECKING:\n    from {PACKAGE}.transform import BRON"
    assert _package_imports(bron) == set()


def _private_imports(bron: str) -> list[str]:
    """``module.naam`` voor elke private naam die ``bron`` uit package of app haalt."""
    return [
        f"{knoop.module}.{alias.name}"
        for knoop in ast.walk(ast.parse(bron))
        if isinstance(knoop, ast.ImportFrom)
        and knoop.module
        and (knoop.module.startswith(PACKAGE) or knoop.module.startswith("_"))
        for alias in knoop.names
        if alias.name.startswith("_")
    ]


def test_geen_private_imports_tussen_modules():
    bestanden = [*SRC.rglob("*.py"), *APP.rglob("*.py")]
    gevonden = {
        str(pad.relative_to(SRC.parents[1])): namen
        for pad in bestanden
        if (namen := _private_imports(pad.read_text(encoding="utf-8")))
    }
    assert gevonden == {}


def test_scan_ziet_een_private_import():
    bron = f"from {PACKAGE}.perioden import _koppel_via, koppel_periode_id"
    assert _private_imports(bron) == [f"{PACKAGE}.perioden._koppel_via"]
