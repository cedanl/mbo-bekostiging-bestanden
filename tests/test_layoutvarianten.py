"""Officiële PvE-layout naast de praktijkvariant (#236 GRONDSLAG-VLP, #321 RO-DIP).

De verwachtingen hieronder komen rechtstreeks uit de PvE-tabellen (4.8.2/4.8.3:
§17.5 Voorlooprecord, §15.5.7 DIP), niet uit de schema-TOML die getest wordt:
zo is de test een onafhankelijk oracle. Het schema kent de praktijkvariant
(demo-leveringen) als standaard en de officiële layout als variant.
"""

import json
from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.ingest import (
    layoutvarianten,
    read_grondslag,
    read_ro,
)
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline

DEMO = Path("data/01-raw/demo")

# PvE §17.5: Recordsoort, Studiejaar, Aanmaakdatum, Bekostiging — geen BRIN.
_VLP_OFFICIEEL = "VLP;2025;20251119;V"
_VLP_PRAKTIJK = "VLP;97XX;2025;20251119;V"
_GRONDSLAG_REST = """PER;900000001;17;18;19;20;V;1234
ISG;900000001;97XX;INS1;20240801;20270731
ISP;900000001;97XX;INS1;20240801;20250615;25655;MBO-4;BOL;VSV001;1
SLR;1;1;1;0;0;0;0;0;0;0;0
"""
_GRONDSLAG_NAAM = "GRONDSLAG_IP_MBO_97XX_20251119_2025.csv"

# PvE §15.5.7: na Datum resultaat direct Indicatie bekostigbaar (9 velden).
_DIP_OFFICIEEL = "DIP|900000001||R1|25655|20250615|J|INS1|101A001"
_DIP_PRAKTIJK = "DIP|900000001||R1|25655|20250615||J|INS1|101A001"
_RO_KOP = """VLP|99XX|2025-08-01|2026-07-31|2026-08-01
PER|900000001||2001-05-17|V
ISG|900000001||INS1|2025-08-01|2027-07-31
"""
_RO_NAAM = "RO_99XX_20250801_20260731.csv"


def _bestand(tmp_path: Path, naam: str, inhoud: str) -> Path:
    pad = tmp_path / naam
    pad.write_text(inhoud, encoding="utf-8")
    return pad


def _grondslag(tmp_path: Path, vlp: str, naam: str = _GRONDSLAG_NAAM) -> Path:
    return _bestand(tmp_path, naam, f"{vlp}\n{_GRONDSLAG_REST}")


def _ro(tmp_path: Path, *dip: str) -> Path:
    return _bestand(tmp_path, _RO_NAAM, _RO_KOP + "".join(f"{r}\n" for r in dip))


def test_officiele_vlp_landt_in_de_juiste_kolommen(tmp_path):
    vlp = read_grondslag(_grondslag(tmp_path, _VLP_OFFICIEEL))["VLP"].row(0, named=True)
    assert (vlp["Studiejaar"], vlp["DatumAanmaak"], vlp["BekostigingsType"]) == (
        "2025",
        "20251119",
        "V",
    )


def test_officiele_vlp_krijgt_brin_uit_de_bestandsnaam(tmp_path):
    """PvE §17.3: GRONDSLAG_IP_MBO_<BRIN>_<einddatum>_<studiejaar>.csv."""
    pad = _grondslag(tmp_path, _VLP_OFFICIEEL)
    assert read_grondslag(pad)["VLP"]["BRIN"].to_list() == ["97XX"]
    vlp = layoutvarianten(pad, "grondslag")["VLP"]
    assert vlp["variant"] == "officieel"
    assert vlp["uit_bestandsnaam"] == {"BRIN": "97XX"}


def test_officiele_vlp_zonder_brin_in_de_bestandsnaam_faalt(tmp_path):
    pad = _grondslag(tmp_path, _VLP_OFFICIEEL, naam="levering.csv")
    with pytest.raises(ValueError, match="bestandsnaam"):
        read_grondslag(pad)


def test_praktijk_vlp_blijft_werken(tmp_path):
    pad = _grondslag(tmp_path, _VLP_PRAKTIJK)
    vlp = read_grondslag(pad)["VLP"].row(0, named=True)
    assert (vlp["BRIN"], vlp["Studiejaar"]) == ("97XX", "2025")
    assert layoutvarianten(pad, "grondslag")["VLP"]["variant"] == "praktijk"


def test_praktijk_vlp_zonder_bekostiging_schuift_niet_naar_officieel(tmp_path):
    """Vier velden, maar ``97XX`` is geen studiejaar: geen van beide layouts."""
    with pytest.raises(ValueError, match="geen enkele layout"):
        read_grondslag(_grondslag(tmp_path, "VLP;97XX;2025;20251119"))


def test_officiele_dip_landt_in_de_juiste_kolommen(tmp_path):
    dip = read_ro(_ro(tmp_path, _DIP_OFFICIEEL))["DIP"].row(0, named=True)
    assert dip["IndicatieBekostigbaar"] == "J"
    assert dip["Inschrijvingvolgnummer"] == "INS1"
    assert dip["Onderwijsaanbieder"] == "101A001"
    assert dip["_onbekend"] == ""


def test_officiele_dip_zonder_optionele_staart(tmp_path):
    pad = _ro(tmp_path, "DIP|900000001||R1|25655|20250615|N")
    dip = read_ro(pad)["DIP"].row(0, named=True)
    assert (dip["IndicatieBekostigbaar"], dip["Inschrijvingvolgnummer"]) == ("N", "")
    assert layoutvarianten(pad, "ro")["DIP"]["variant"] == "officieel"


def test_praktijk_dip_met_positie_7_blijft_werken(tmp_path):
    pad = _ro(tmp_path, _DIP_PRAKTIJK)
    dip = read_ro(pad)["DIP"].row(0, named=True)
    assert (dip["_onbekend"], dip["IndicatieBekostigbaar"]) == ("", "J")
    assert dip["Onderwijsaanbieder"] == "101A001"
    assert layoutvarianten(pad, "ro")["DIP"]["variant"] == "praktijk"


def test_dip_die_op_geen_layout_past_faalt(tmp_path):
    """Positie 7 gevuld met iets anders dan J/N: praktijk verwacht daar leeg,
    officieel een indicatie bekostigbaar. Nooit stil verschuiven."""
    with pytest.raises(ValueError, match=r"regel 4 \(DIP\).*geen enkele layout"):
        read_ro(_ro(tmp_path, "DIP|900000001||R1|25655|20250615|X|J"))


def test_dip_met_gevulde_positie_7_legt_de_afgewezen_praktijklayout_vast(tmp_path):
    """#358: een praktijkregel met ``J`` op positie 7 past alleen nog op de
    officiële layout en wordt daar gelezen; dat moet in het rapport zichtbaar
    zijn, anders lijkt het een gewone officiële levering."""
    pad = _ro(tmp_path, _DIP_OFFICIEEL)
    dip = layoutvarianten(pad, "ro")["DIP"]
    assert dip["variant"] == "officieel"
    assert dip["afgewezen"].keys() == {"praktijk"}
    assert "_onbekend" in dip["afgewezen"]["praktijk"]


def test_afgewezen_noemt_de_andere_kandidaat_ook_bij_de_praktijklayout(tmp_path):
    dip = layoutvarianten(_ro(tmp_path, _DIP_PRAKTIJK), "ro")["DIP"]
    assert dip["variant"] == "praktijk"
    assert dip["afgewezen"].keys() == {"officieel"}


def test_gemengde_layouts_in_een_bestand_falen(tmp_path):
    with pytest.raises(ValueError, match="meerdere layouts"):
        read_ro(_ro(tmp_path, _DIP_PRAKTIJK, _DIP_OFFICIEEL))


def test_demo_gebruikt_de_praktijkvarianten():
    ro = next(DEMO.glob("h15/RO_27DV_*.csv"))
    grondslag = next(DEMO.glob("h17/GRONDSLAG_*.csv"))
    assert layoutvarianten(ro, "ro")["DIP"]["variant"] == "praktijk"
    assert layoutvarianten(grondslag, "grondslag")["VLP"]["variant"] == "praktijk"


def test_quality_json_legt_de_gekozen_variant_vast(tmp_path):
    bron = _grondslag(tmp_path, _VLP_OFFICIEEL)
    frames = run_auto_pipeline(bron, tmp_path / "uit")
    rapport = json.loads((tmp_path / "uit" / "quality.json").read_text("utf-8"))
    assert rapport["layoutvarianten"]["VLP"]["variant"] == "officieel"
    assert frames["VLP"]["BRIN"].to_list() == ["97XX"]
