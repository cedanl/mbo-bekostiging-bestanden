"""Waardedomeincontrole vangt een verschoven veldindeling (#205).

Positioneel parsen merkt niet dat een veld op de verkeerde plek staat: een
tekstwaarde past in elke tekstkolom. Per veld is in het schema een domein
(waardenlijst of patroon) vastgelegd; waarden daarbuiten worden per levering
geteld en gemeld. Lege waarden tellen niet (optionele velden).
"""

import json
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.ingest import read_grondslag, read_ro
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline
from mbo_bekostiging_bestanden.waardenlijsten import controleer_waardedomeinen

DEMO = Path("data/01-raw/demo")

# RO-DIP met positie 7 (_onbekend, altijd leeg); zonder die positie schuift alles op.
DIP_MET_POS_7 = "DIP|BSN1||8286771|25655|2025-06-15||J|1|101A741"
DIP_ZONDER_POS_7 = "DIP|BSN1||8286771|25655|2025-06-15|J|1|101A741"
_RO = "VLP|99XX|2025-08-01|2026-07-31|2026-08-01\nPER|BSN1||2001-05-17|V\n{dip}\n"


def _ro_frames(tmp_path: Path, dip: str) -> dict[str, pl.DataFrame]:
    pad = tmp_path / "RO_99XX_20250801_20260731.csv"
    pad.write_text(_RO.format(dip=dip), encoding="utf-8")
    return read_ro(pad)


def test_dip_zonder_positie_7_wordt_gesignaleerd(tmp_path):
    """``J`` schuift naar ``_onbekend``; ``1`` naar IndicatieBekostigbaar is toevallig
    ook geldig, dus juist het verplicht lege veld verraadt de verschuiving."""
    frames = _ro_frames(tmp_path, DIP_ZONDER_POS_7)
    assert controleer_waardedomeinen(frames, "ro") == {"DIP": {"_onbekend": 1}}


def test_dip_volgens_praktijklayout_heeft_geen_afwijking(tmp_path):
    assert controleer_waardedomeinen(_ro_frames(tmp_path, DIP_MET_POS_7), "ro") == {}


def test_waarden_worden_genormaliseerd_vergeleken():
    frames = {
        "KZD": pl.DataFrame({"Resultaat": ["Niet  behaald", " behaald", "Deels"]})
    }
    assert controleer_waardedomeinen(frames, "ro") == {"KZD": {"Resultaat": 1}}


def test_lege_waarden_tellen_niet():
    frames = {"ISP": pl.DataFrame({"Onderwijsaanbieder": ["", None, "101A741"]})}
    assert controleer_waardedomeinen(frames, "ro") == {}


def test_pipeline_meldt_domeinafwijkingen(tmp_path):
    bron = tmp_path / "RO_99XX_20250801_20260731.csv"
    bron.write_text(_RO.format(dip=DIP_ZONDER_POS_7), encoding="utf-8")
    doel = tmp_path / "prepared"
    run_auto_pipeline(bron, doel)
    rapport = json.loads((doel / "quality.json").read_text(encoding="utf-8"))
    assert rapport["domeinafwijkingen"]["DIP"]["_onbekend"] == 1
    assert any("_onbekend" in w for w in rapport["warnings"])


@pytest.mark.parametrize(
    "bron", sorted(DEMO.glob("h1[57]/*.csv")), ids=lambda p: p.stem
)
def test_demo_valt_binnen_de_waardedomeinen(bron):
    grondslag = bron.name.startswith("GRONDSLAG")
    frames = (read_grondslag if grondslag else read_ro)(bron)
    assert controleer_waardedomeinen(frames, "grondslag" if grondslag else "ro") == {}
