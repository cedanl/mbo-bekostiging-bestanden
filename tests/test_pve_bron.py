"""De PvE-bron is één manifest waar schema's en bronbestand aan vastzitten (#299).

De 4.8.2→4.8.3-drift werd handmatig gevonden. Deze test breekt in CI zodra een
schema een andere versie noemt dan het manifest, of het bronbestand verandert
zonder dat het manifest is bijgewerkt.
"""

import hashlib
import importlib.util
from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.metadata import pve_bron, schema_versie

_REPO = Path(__file__).parent.parent
_SCRIPT = _REPO / "scripts" / "controleer_pve_upstream.py"


def _upstream_module():
    pytest.importorskip("pypdf")
    spec = importlib.util.spec_from_file_location("controleer_pve_upstream", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("schema", ["ro", "grondslag", "tbgi"])
def test_schema_verwijst_naar_de_versie_in_het_manifest(schema):
    assert schema_versie(schema) == pve_bron()["versie"]


def test_bronbestand_komt_overeen_met_het_manifest():
    bestand = _REPO / pve_bron()["bestand"]
    assert hashlib.sha256(bestand.read_bytes()).hexdigest() == pve_bron()["sha256"]


def test_manifest_heeft_alle_velden():
    assert set(pve_bron()) == {"versie", "datum", "bestand", "sha256", "bron_url"}


def test_versie_uit_het_voorblad():
    module = _upstream_module()
    voorblad = "Programma van Eisen\n\nVersie: 4.8.3   Datum: 12-05-2026\n"
    assert module.pve_versie(voorblad) == ("4.8.3", "12-05-2026")


def test_voorblad_zonder_versie():
    assert _upstream_module().pve_versie("iets anders") is None
