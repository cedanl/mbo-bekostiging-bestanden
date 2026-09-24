"""Demo-kwaliteitsrapporten: SLR-totalen kloppen met de subset-aantallen.

Regressie #77: de demo-bestanden bevatten subsets, maar hun SLR-records
droegen oorspronkelijk controletotalen uit de volledige DUO-levering, waardoor
elk demo-onderdeel een misleidende SLR-mismatch liet zien.
"""

import json
from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline

DEMO_RAW = Path("data/01-raw/demo")


def _demo_bestandssoorten() -> list[Path]:
    """Alle ruwe demo-bestanden met een SLR-reconciliatie (CSV-typen)."""
    return [
        f
        for f in sorted(DEMO_RAW.rglob("*"))
        if f.suffix.lower() == ".csv" and "SLR" in f.read_text(encoding="utf-8")
    ]


@pytest.mark.parametrize(
    "bestand", _demo_bestandssoorten(), ids=lambda p: str(p)
)
def test_demo_quality_slr_status_is_match(tmp_path, bestand):
    """Het demo-bestand reconcilieert zonder mismatch tegen zijn eigen SLR."""
    run_auto_pipeline(bestand, tmp_path / bestand.stem)
    report = json.loads(
        (tmp_path / bestand.stem / "quality.json").read_text(encoding="utf-8")
    )
    assert report["slr_status"] == "match", (
        f"{bestand.name}: verwacht 'match', kreeg "
        f"{report['slr_status']!r}: {report['slr_details']}"
    )
