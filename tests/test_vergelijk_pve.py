"""Script dat twee PvE-versies op de bestandsbeschrijvingen vergelijkt (#298).

Hoofdstuk 13–17 (bestandsbeschrijvingen) zijn de bron van de schema's. Het
script vergelijkt die pagina's per paginanummer, zonder versiestrings en
witruimte, zodat een nieuwe PvE-versie een reproduceerbare diff krijgt in
plaats van een handmatige doorloop.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent / "scripts" / "vergelijk_pve.py"
_PDF = Path("bestandsbeschrijving_beknopt.pdf")


@pytest.fixture(scope="module")
def script():
    pytest.importorskip("pypdf")
    spec = importlib.util.spec_from_file_location("vergelijk_pve", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_versie_en_witruimte_tellen_niet(script):
    oud = "PvE MBO-instelling - DUO versie 4.8.2  12-05-2026\nVeld  A \n"
    nieuw = "PvE MBO-instelling - DUO versie 4.8.3 12-05-2026\nVeld A\n"
    assert script.normaliseer(oud) == script.normaliseer(nieuw)


def test_inhoudelijk_verschil_telt_wel(script):
    assert script.normaliseer("Omvang N1..4") != script.normaliseer("Omvang N1..5")


def test_paginanummer_uit_de_footer(script):
    assert script.paginanummer("x\nPagina 188 van 224\ny") == 188
    assert script.paginanummer("geen footer") is None


def test_beknopte_extractie_verschilt_niet_van_zichzelf(script):
    assert script.verschillen(_PDF, _PDF) == {}
