"""Ingest gooit niets stil weg (#120), en faalt sinds #257 fail-closed.

Positioneel parsen neemt per recordtype alleen de velden uit het schema. Een
onbekend recordtype en gevulde velden voorbij de schemabreedte verdwenen
voorheen zonder spoor; de SLR-reconciliatie bleef "match". Sinds #257 breekt
``read_multi_record_csv`` de ingest op precies die twee gevallen, in plaats
van ze stil te negeren/afknippen. ``inventariseer_regels`` telt daarom alleen
nog ``spiegel_afwijkingen``, dat wél door de pipeline heen komt (#292).
"""

from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.ingest import (
    inventariseer_regels,
    read_multi_record_csv,
)
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline
from mbo_bekostiging_bestanden.quality import QualityReport

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


def test_inventaris_bevat_alleen_categorieen_die_kunnen_voorkomen(tmp_path):
    """Onbekende recordtypes en velden voorbij het schema breken de ingest
    (#257) en horen dus niet meer in het rapport (#292)."""
    inv = inventariseer_regels(_bestand(tmp_path, "RO_99XX_1_2.csv", RO), "ro")
    assert set(inv) == {"spiegel_afwijkingen"}


def test_spiegelvelden_die_kloppen_zijn_geen_afwijking(tmp_path):
    pad = _bestand(tmp_path, "GRONDSLAG_IP_MBO_99XX_1_2.csv", GRONDSLAG_SPIEGEL)
    inv = inventariseer_regels(pad, "grondslag")
    assert inv["spiegel_afwijkingen"] == {}


def test_spiegelveld_dat_afwijkt_wordt_geteld(tmp_path):
    pad = _bestand(tmp_path, "GRONDSLAG_IP_MBO_99XX_1_2.csv", GRONDSLAG_AFWIJKEND)
    inv = inventariseer_regels(pad, "grondslag")
    assert inv["spiegel_afwijkingen"] == {"PER": {"Postcodecijfers_positie19": 1}}


def test_pipeline_faalt_bij_onbekend_recordtype(tmp_path):
    """Fail-closed (#257): geen quality.json meer, de ingest breekt meteen."""
    bron = _bestand(
        tmp_path,
        "RO_99XX_20250801_20260731.csv",
        "VLP|99XX|2025-08-01|2026-07-31|2026-08-01\nXYZ|iets\n",
    )
    doel = tmp_path / "prepared"
    with pytest.raises(ValueError, match="XYZ"):
        run_auto_pipeline(bron, doel)
    assert not (doel / "quality.json").exists()


def test_pipeline_faalt_bij_velden_voorbij_schema(tmp_path):
    """Fail-closed (#257): een gevuld veld voorbij het schema breekt de ingest."""
    bron = _bestand(
        tmp_path,
        "RO_99XX_20250801_20260731.csv",
        "VLP|99XX|2025-08-01|2026-07-31|2026-08-01\n"
        "ISG|BSN2||1|2025-08-01|2027-07-31|||ONVERWACHT\n",
    )
    doel = tmp_path / "prepared"
    with pytest.raises(ValueError, match="ISG"):
        run_auto_pipeline(bron, doel)


def test_demo_grondslag_positie_19_is_niet_altijd_een_spiegel():
    """Data-eigenschap van de demo: 1 van 10 PER-rijen heeft op positie 19 een
    andere postcode dan ``Postcodecijfers``. Afknippen verloor die stil."""
    bron = DEMO / "h17" / "GRONDSLAG_IP_MBO_27DV_20251119_2025.csv"
    inv = inventariseer_regels(bron, "grondslag")
    assert inv["spiegel_afwijkingen"] == {"PER": {"Postcodecijfers_positie19": 1}}


# --- Posities buiten het PvE bewaren (#260) ---------------------------------
# Of positie 19 een verschoven postcode is of een eerdere waarde, staat niet in
# het PvE. Zolang dat open is: bewaren onder hun positie, niet interpreteren.
_EXTRA_POSITIES = {
    "Postcodecijfers_positie19": "9999",
    "Verblijfstitel_positie20": "01",
    "Nationaliteit1_positie21": "0001",
}


def test_extra_posities_worden_bewaard_in_de_brondata(tmp_path):
    pad = _bestand(tmp_path, "GRONDSLAG_IP_MBO_99XX_1_2.csv", GRONDSLAG_AFWIJKEND)
    per = read_multi_record_csv(pad, "grondslag")["PER"].row(0, named=True)
    assert {k: per[k] for k in _EXTRA_POSITIES} == _EXTRA_POSITIES
    assert per["Postcodecijfers"] == "1234"


def test_extra_posities_zijn_leeg_als_de_regel_ze_niet_heeft(tmp_path):
    pad = _bestand(
        tmp_path, "GRONDSLAG_IP_MBO_99XX_1_2.csv", f"VLP;99XX;2025;20251119;V\n{_PER}\n"
    )
    per = read_multi_record_csv(pad, "grondslag")["PER"].row(0, named=True)
    assert all(per[k] == "" for k in _EXTRA_POSITIES)


def test_extra_posities_blijven_buiten_het_analysemodel(demo_star):
    """Onbekende betekenis is geen analysekeuze; bovendien persoonsgegevens."""
    for naam, tabel in demo_star.items():
        assert not set(_EXTRA_POSITIES) & set(tabel.columns), naam


def test_melding_suggereert_geen_verschuiving():
    rapport = QualityReport(levering="L", schema_type="grondslag")
    rapport.meld_regelinventaris(
        {"spiegel_afwijkingen": {"PER": {"Postcodecijfers_positie19": 1}}}
    )
    [melding] = rapport.warnings
    assert "verschoven" not in melding
    assert "Postcodecijfers_positie19" in melding
