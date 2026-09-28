"""Ingest gooit niets stil weg: afwijkende regels worden geteld en gemeld (#120).

Positioneel parsen neemt per recordtype alleen de velden uit het schema. Een
onbekend recordtype en gevulde velden voorbij de schemabreedte verdwenen
voorheen zonder spoor; de SLR-reconciliatie bleef "match". Nu staan ze per
levering in ``quality.json`` (``regelinventaris``) met een waarschuwing.
"""

import json
from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.ingest import inventariseer_regels
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline

DEMO = Path("data/01-raw/demo")

RO = """VLP|99XX|2025-08-01|2026-07-31|2026-08-01
PER|BSN1||2001-05-17|V
ISG|BSN1||1|2025-08-01|2027-07-31||
ISG|BSN2||1|2025-08-01|2027-07-31|||ONVERWACHT
XYZ|iets
CTR|3
SLR|1|2|0|0|0|0|0|0|0
"""

# GRONDSLAG-PER: posities 19–21 spiegelen Postcodecijfers/Verblijfstitel/Nationaliteit1.
_PER = "PER;900000001;17;18;19;20;V;1234;;;;6030;6031;6032;6033;01;0001;0002"
GRONDSLAG_SPIEGEL = f"VLP;99XX;2025;20251119;V\n{_PER};1234;01;0001\n"
GRONDSLAG_AFWIJKEND = f"VLP;99XX;2025;20251119;V\n{_PER};9999;01;0001\n"


def _bestand(tmp_path: Path, naam: str, inhoud: str) -> Path:
    pad = tmp_path / naam
    pad.write_text(inhoud, encoding="utf-8")
    return pad


def test_onbekende_recordtypes_worden_geteld(tmp_path):
    inv = inventariseer_regels(_bestand(tmp_path, "RO_99XX_1_2.csv", RO), "ro")
    assert inv["onbekende_recordtypes"] == {"CTR": 1, "XYZ": 1}


def test_gevulde_velden_voorbij_het_schema_worden_geteld(tmp_path):
    inv = inventariseer_regels(_bestand(tmp_path, "RO_99XX_1_2.csv", RO), "ro")
    assert inv["velden_voorbij_schema"] == {"ISG": 1}


def test_spiegelvelden_die_kloppen_zijn_geen_afwijking(tmp_path):
    pad = _bestand(tmp_path, "GRONDSLAG_IP_MBO_99XX_1_2.csv", GRONDSLAG_SPIEGEL)
    inv = inventariseer_regels(pad, "grondslag")
    assert inv["velden_voorbij_schema"] == {}
    assert inv["spiegel_afwijkingen"] == {}


def test_spiegelveld_dat_afwijkt_wordt_geteld(tmp_path):
    pad = _bestand(tmp_path, "GRONDSLAG_IP_MBO_99XX_1_2.csv", GRONDSLAG_AFWIJKEND)
    inv = inventariseer_regels(pad, "grondslag")
    assert inv["spiegel_afwijkingen"] == {"PER": {"Postcodecijfers": 1}}


def test_pipeline_meldt_inventaris_in_quality_json(tmp_path):
    bron = _bestand(tmp_path, "RO_99XX_20250801_20260731.csv", RO)
    doel = tmp_path / "prepared"
    run_auto_pipeline(bron, doel)
    rapport = json.loads((doel / "quality.json").read_text(encoding="utf-8"))
    assert rapport["regelinventaris"]["onbekende_recordtypes"] == {"CTR": 1, "XYZ": 1}
    assert any("XYZ" in w for w in rapport["warnings"])
    assert any("ISG" in w for w in rapport["warnings"])


@pytest.mark.parametrize(
    "bron", sorted(DEMO.glob("h1[57]/*.csv")), ids=lambda p: p.stem
)
def test_demo_heeft_geen_onbekende_regels_of_extra_velden(bron):
    schema = "grondslag" if bron.name.startswith("GRONDSLAG") else "ro"
    inv = inventariseer_regels(bron, schema)
    assert inv["onbekende_recordtypes"] == {}
    assert inv["velden_voorbij_schema"] == {}


def test_demo_grondslag_positie_19_is_niet_altijd_een_spiegel():
    """Data-eigenschap van de demo: 1 van 10 PER-rijen heeft op positie 19 een
    andere postcode dan ``Postcodecijfers``. Afknippen verloor die stil."""
    bron = DEMO / "h17" / "GRONDSLAG_IP_MBO_27DV_20251119_2025.csv"
    inv = inventariseer_regels(bron, "grondslag")
    assert inv["spiegel_afwijkingen"] == {"PER": {"Postcodecijfers": 1}}
