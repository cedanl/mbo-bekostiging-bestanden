"""Elke star-check staat in één register en komt overal terecht (#329).

Een check die wel berekend wordt maar niet in ``quality.json``, de status of de
meldingenweergave landt, was met de oude if-keten een reëel risico. De test
vervangt per check de meldingen door één error-sentinel en eist dat die in
``summary`` en :func:`kwaliteitsmeldingen` verschijnt; zo geldt het voor elke
toekomstige check zonder dat de test die hoeft te kennen.
"""

import dataclasses
import json
from pathlib import Path

import pytest

from mbo_bekostiging_bestanden import quality
from mbo_bekostiging_bestanden.quality import (
    Melding,
    compile_quality_report,
    kwaliteitsmeldingen,
)

SCHEMA = json.loads(Path("docs/quality.schema.json").read_text(encoding="utf-8"))
_SENTINEL = Melding(quality.ERNST_ERROR, "test", "sentinel")
_CHECKS = quality._STER_CHECKS


def test_register_dekt_precies_de_star_sectie_van_het_schema():
    sleutels = [check.sleutel for check in _CHECKS]
    assert len(sleutels) == len(set(sleutels))
    assert set(sleutels) == set(SCHEMA["properties"]["star"]["required"])


@pytest.mark.parametrize("index", range(len(_CHECKS)), ids=lambda i: _CHECKS[i].sleutel)
def test_check_bereikt_quality_json_status_en_meldingen(monkeypatch, index):
    checks = list(_CHECKS)
    checks[index] = dataclasses.replace(checks[index], meldingen=lambda _: [_SENTINEL])
    monkeypatch.setattr(quality, "_STER_CHECKS", tuple(checks))

    rapport = compile_quality_report({})

    assert checks[index].sleutel in rapport["star"]
    assert rapport["summary"]["total_errors"] == 1
    assert rapport["summary"]["status"] == "fail"
    assert kwaliteitsmeldingen(rapport) == [_SENTINEL]


def test_check_zonder_sleutel_in_een_oud_rapport_meldt_niets():
    """Rapporten van vóór een check missen zijn sleutel; dat is geen bevinding."""
    assert kwaliteitsmeldingen({"deliveries": [], "star": {}}) == []
