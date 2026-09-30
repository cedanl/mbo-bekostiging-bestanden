"""Waardedomeincontrole vangt een verschoven veldindeling (#205).

Positioneel parsen merkt niet dat een veld op de verkeerde plek staat: een
tekstwaarde past in elke tekstkolom. Per veld is in het schema een domein
(waardenlijst of patroon) vastgelegd; waarden daarbuiten worden per levering
geteld en gemeld. Lege waarden tellen alleen bij een verplicht domein
(``verplicht = true``, #320); bij optionele velden niet.
"""

import json
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.ingest import read_grondslag, read_ro
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline
from mbo_bekostiging_bestanden.waardenlijsten import controleer_waardedomeinen

DEMO = Path("data/01-raw/demo")

# RO-DIP in de praktijklayout (positie 7 leeg) en de officiële PvE-layout (#321).
DIP_MET_POS_7 = "DIP|BSN1||8286771|25655|2025-06-15||J|1|101A741"
DIP_OFFICIEEL = "DIP|BSN1||8286771|25655|2025-06-15|J|1|101A741"
# Alle verplichte recordtypes (#322); ``{vlp}`` en ``{dip}`` zijn het variabele deel.
_RO = (
    "{vlp}\nPER|BSN1||2001-05-17|V\nISG|BSN1||1|2025-08-01|2027-07-31||\n"
    "ISP|BSN1||1|2025-08-01|25618|BBL||J||101A741|100X974|||\n{dip}\n"
    "SLR|1|1|1|0|0|1|0|0|0\n"
)
_VLP = "VLP|99XX|2025-08-01|2026-07-31|2026-08-01"


def _ro_frames(tmp_path: Path, dip: str) -> dict[str, pl.DataFrame]:
    pad = tmp_path / "RO_99XX_20250801_20260731.csv"
    pad.write_text(_RO.format(vlp=_VLP, dip=dip), encoding="utf-8")
    return read_ro(pad)


def test_gevulde_positie_7_is_een_error():
    """Vangnet naast de layoutherkenning (#287): die laat zo'n regel niet door,
    maar een frame van buiten de ingest kan het nog bevatten."""
    frames = {"DIP": pl.DataFrame({"_onbekend": ["J", ""]})}
    assert controleer_waardedomeinen(frames, "ro") == {
        "DIP": {"_onbekend": {"aantal": 1, "ernst": "error"}}
    }


@pytest.mark.parametrize("dip", [DIP_MET_POS_7, DIP_OFFICIEEL])
def test_dip_in_beide_layouts_heeft_geen_afwijking(tmp_path, dip):
    assert controleer_waardedomeinen(_ro_frames(tmp_path, dip), "ro") == {}


def test_waarden_worden_genormaliseerd_vergeleken():
    frames = {
        "KZD": pl.DataFrame({"Resultaat": ["Niet  behaald", " behaald", "Deels"]})
    }
    assert controleer_waardedomeinen(frames, "ro") == {
        "KZD": {"Resultaat": {"aantal": 1, "ernst": "warning"}}
    }


def test_lege_waarden_tellen_niet():
    frames = {"ISP": pl.DataFrame({"Onderwijsaanbieder": ["", None, "101A741"]})}
    assert controleer_waardedomeinen(frames, "ro") == {}


def test_pipeline_leest_officiele_dip_zonder_meldingen(tmp_path):
    """Vóór #321 schoof deze regel één kolom op en meldde de pipeline een error."""
    bron = tmp_path / "RO_99XX_20250801_20260731.csv"
    bron.write_text(_RO.format(vlp=_VLP, dip=DIP_OFFICIEEL), encoding="utf-8")
    doel = tmp_path / "prepared"
    run_auto_pipeline(bron, doel)
    rapport = json.loads((doel / "quality.json").read_text(encoding="utf-8"))
    assert rapport["domeinafwijkingen"] == {}
    assert rapport["layoutvarianten"] == {"DIP": {"variant": "officieel"}}


@pytest.mark.parametrize(
    "bron", sorted(DEMO.glob("h1[57]/*.csv")), ids=lambda p: p.stem
)
def test_demo_valt_binnen_de_waardedomeinen(bron):
    grondslag = bron.name.startswith("GRONDSLAG")
    frames = (read_grondslag if grondslag else read_ro)(bron)
    assert controleer_waardedomeinen(frames, "grondslag" if grondslag else "ro") == {}


def test_ongeldig_brin_wordt_als_error_gemeld():
    """BRIN is structureel: een afwijking wijst op een verschoven layout (#238)."""
    frames = {"VLP": pl.DataFrame({"BRIN": ["27DV", "NIET-EEN-BRIN"]})}
    assert controleer_waardedomeinen(frames, "ro") == {
        "VLP": {"BRIN": {"aantal": 1, "ernst": "error"}}
    }


def test_verschoven_studiejaar_wordt_als_error_gemeld():
    """GRONDSLAG-VLP.Studiejaar buiten een 4-cijferig jaar wijst op een
    verschoven veldindeling, net als BRIN (#238)."""
    frames = {"VLP": pl.DataFrame({"Studiejaar": ["2025", "25"]})}
    assert controleer_waardedomeinen(frames, "grondslag") == {
        "VLP": {"Studiejaar": {"aantal": 1, "ernst": "error"}}
    }


def test_pipeline_meldt_domeinfout_als_error(tmp_path):
    """Een ongeldig BRIN in VLP komt in ``errors`` terecht, niet ``warnings`` (#238)."""
    bron = tmp_path / "RO_99XX_20250801_20260731.csv"
    bron.write_text(
        _RO.format(vlp="VLP|9X|2025-08-01|2026-07-31|2026-08-01", dip=DIP_MET_POS_7),
        encoding="utf-8",
    )
    doel = tmp_path / "prepared"
    run_auto_pipeline(bron, doel, fail_on_errors=False)
    rapport = json.loads((doel / "quality.json").read_text(encoding="utf-8"))
    assert rapport["domeinafwijkingen"]["VLP"]["BRIN"] == {
        "aantal": 1,
        "ernst": "error",
    }
    assert any("BRIN" in e for e in rapport["errors"])
    assert not any("BRIN" in w for w in rapport["warnings"])


@pytest.mark.parametrize("leeg", ["", None])
def test_lege_verplichte_brin_is_een_error(leeg):
    """BRIN is verplicht (PvE): leeg is geen 'optioneel veld' maar een gat (#320)."""
    frames = {"VLP": pl.DataFrame({"BRIN": ["27DV", leeg]})}
    assert controleer_waardedomeinen(frames, "ro") == {
        "VLP": {"BRIN": {"aantal": 1, "ernst": "error", "leeg": 1}}
    }


def test_lege_en_ongeldige_waarde_worden_apart_geteld():
    frames = {"VLP": pl.DataFrame({"BRIN": ["", "9X", "27DV"]})}
    assert controleer_waardedomeinen(frames, "ro") == {
        "VLP": {"BRIN": {"aantal": 2, "ernst": "error", "leeg": 1}}
    }


def test_leeg_studiejaar_in_grondslag_is_een_error():
    frames = {"VLP": pl.DataFrame({"Studiejaar": ["2025", "  "]})}
    assert controleer_waardedomeinen(frames, "grondslag") == {
        "VLP": {"Studiejaar": {"aantal": 1, "ernst": "error", "leeg": 1}}
    }


def test_lege_datumbeginperiode_in_ro_is_een_error():
    """§15.5.1: DatumBeginPeriode is verplicht in RO-VLP (#354)."""
    frames = {"VLP": pl.DataFrame({"DatumBeginPeriode": ["2025-08-01", ""]})}
    result = controleer_waardedomeinen(frames, "ro")
    assert result.get("VLP", {}).get("DatumBeginPeriode", {}).get("ernst") == "error"


def test_pipeline_faalt_op_lege_brin(tmp_path):
    """Voorheen: status ``pass`` en de instelling verdween stil uit de ster (#320)."""
    bron = tmp_path / "RO_99XX_20250801_20260731.csv"
    bron.write_text(
        _RO.format(vlp="VLP||2025-08-01|2026-07-31|2026-08-01", dip=DIP_MET_POS_7),
        encoding="utf-8",
    )
    doel = tmp_path / "prepared"
    run_auto_pipeline(bron, doel, fail_on_errors=False)
    rapport = json.loads((doel / "quality.json").read_text(encoding="utf-8"))
    assert rapport["domeinafwijkingen"]["VLP"]["BRIN"]["leeg"] == 1
    assert any("BRIN" in e and "leeg" in e for e in rapport["errors"])


@pytest.mark.parametrize("recordtype", ["PER", "ISG", "ISP", "SLR"])
def test_ingest_faalt_bij_ontbrekend_verplicht_recordtype(tmp_path, recordtype):
    """Voorheen een kale ``KeyError: 'PER'`` diep in ``build_star`` (#322)."""
    regels = _RO.format(vlp=_VLP, dip=DIP_MET_POS_7).splitlines()
    bron = tmp_path / "RO_99XX_20250801_20260731.csv"
    bron.write_text(
        "\n".join(r for r in regels if not r.startswith(recordtype)), encoding="utf-8"
    )
    with pytest.raises(ValueError, match=recordtype):
        run_auto_pipeline(bron, tmp_path / "prepared")


@pytest.mark.parametrize("recordtype", ["DIP", "ISE", "BPV", "GEO", "KZD", "AMO"])
def test_optioneel_recordtype_mag_ontbreken(tmp_path, recordtype):
    regels = _RO.format(vlp=_VLP, dip=DIP_MET_POS_7).splitlines()
    bron = tmp_path / "RO_99XX_20250801_20260731.csv"
    bron.write_text(
        "\n".join(r for r in regels if not r.startswith(recordtype)), encoding="utf-8"
    )
    run_auto_pipeline(bron, tmp_path / "prepared")
