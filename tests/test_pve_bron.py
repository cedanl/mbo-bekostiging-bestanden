"""De PvE-bron is één manifest waar schema's en bronbestand aan vastzitten (#299).

De 4.8.2→4.8.3-drift werd handmatig gevonden. Deze test breekt in CI zodra het
bronbestand verandert zonder dat het manifest is bijgewerkt; dat de schema's de
versie niet zelf herhalen, toetst ``test_pve_versie.py`` (#298).
"""

import hashlib
import importlib.util
from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.metadata import pve_bron

_REPO = Path(__file__).parent.parent
_SCRIPT = _REPO / "scripts" / "controleer_pve_upstream.py"


def _upstream_module():
    pytest.importorskip("pypdf")
    spec = importlib.util.spec_from_file_location("controleer_pve_upstream", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bronbestand_komt_overeen_met_het_manifest():
    bestand = _REPO / pve_bron()["bestand"]
    assert hashlib.sha256(bestand.read_bytes()).hexdigest() == pve_bron()["sha256"]


def test_manifest_heeft_alle_velden():
    assert set(pve_bron()) == {
        "versie",
        "datum",
        "bestand",
        "sha256",
        "sha256_volledig",
        "bron_url",
    }


def test_versie_uit_het_voorblad():
    module = _upstream_module()
    voorblad = "Programma van Eisen\n\nVersie: 4.8.3   Datum: 12-05-2026\n"
    assert module.pve_versie(voorblad) == ("4.8.3", "12-05-2026")


def test_voorblad_zonder_versie():
    assert _upstream_module().pve_versie("iets anders") is None


_VOORBLAD = ("4.8.3", "12-05-2026")


def test_gelijke_versie_en_inhoud_is_geen_fout():
    bron = pve_bron()
    fouten, meldingen = _upstream_module().beoordeel(
        _VOORBLAD, [], bron["sha256_volledig"], bron
    )
    assert (fouten, meldingen) == ([], [])


def test_gewijzigde_inhoud_op_dezelfde_versie_faalt():
    """#368: DUO wijzigt de PDF zonder het versienummer te verhogen."""
    bron = pve_bron()
    fouten, _ = _upstream_module().beoordeel(
        _VOORBLAD, [174, 175], bron["sha256_volledig"], bron
    )
    assert len(fouten) == 1
    assert "[174, 175]" in fouten[0]


def test_andere_versie_faalt_zonder_paginavergelijking():
    bron = pve_bron()
    fouten, _ = _upstream_module().beoordeel(("4.9.0", "01-01-2027"), [], "x", bron)
    assert "4.9.0" in fouten[0]


def test_andere_hash_bij_gelijke_inhoud_is_alleen_een_melding():
    fouten, meldingen = _upstream_module().beoordeel(
        _VOORBLAD, [], "afwijkend", pve_bron()
    )
    assert fouten == []
    assert "inhoud is gelijk" in meldingen[0]


def test_geen_versie_op_het_voorblad_faalt():
    fouten, _ = _upstream_module().beoordeel(None, [], "x", pve_bron())
    assert fouten
