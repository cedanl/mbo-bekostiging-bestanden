"""Parseverlies: gevulde bronwaarden die na typering leeg zijn (#129).

De datumparsing kiest één formaat per bestand en parst niet-strikt; ook
getallen worden niet-strikt gecast. Wat daarbij verloren gaat, moet zichtbaar
zijn in quality.json in plaats van stil null te worden. Synthetische data: de
demo wordt nooit aangepast, alleen een kopie in tmp_path.
"""

import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.decode import decode_ro
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline
from mbo_bekostiging_bestanden.quality import KwaliteitsFout, tel_parseverlies

RO_DEMO = Path("data/01-raw/demo/h15/RO_25LX_20250101_20251231.csv")


def test_telt_gevulde_waarden_die_leeg_werden():
    ruw = {
        "ISG": pl.DataFrame(
            {
                "DatumInschrijving": ["2025-08-01", "31-02-2025", "", None],
                "Code": ["a", "b", "c", "d"],
            }
        )
    }
    getypeerd = {
        "ISG": pl.DataFrame(
            {
                "DatumInschrijving": [date(2025, 8, 1), None, None, None],
                "Code": ["a", "b", "c", "d"],
            }
        )
    }
    assert tel_parseverlies(ruw, getypeerd) == {"ISG": {"DatumInschrijving": 1}}


def test_geen_verlies_geeft_leeg_resultaat():
    ruw = {"ISG": pl.DataFrame({"Omvang": ["10", ""]})}
    getypeerd = {"ISG": pl.DataFrame({"Omvang": [10, None]})}
    assert tel_parseverlies(ruw, getypeerd) == {}


def test_alleen_witruimte_is_geen_parseverlies():
    """Decode trimt witruimte en maakt een lege cel null (#392); dat is de
    eigen normalisatie en geen verlies. Voorheen blokkeerde een spatie in een
    datumveld de run, terwijl dezelfde spatie in een tekstveld stil null werd
    (#418)."""
    ruw = {"BPV": pl.DataFrame({"Recordsoort": ["BPV", "BPV"], "Omvang": [" ", "x "]})}
    getypeerd = decode_ro(ruw)
    assert tel_parseverlies(ruw, getypeerd) == {"BPV": {"Omvang": 1}}


def test_ongeldig_getal_wordt_null_in_plaats_van_crash():
    ruw = {"BPV": pl.DataFrame({"Recordsoort": ["BPV", "BPV"], "Omvang": ["900", "x"]})}
    getypeerd = decode_ro(ruw)
    assert getypeerd["BPV"]["Omvang"].to_list() == [900, None]
    assert tel_parseverlies(ruw, getypeerd) == {"BPV": {"Omvang": 1}}


def test_pipeline_meldt_parseverlies_in_quality_json(tmp_path):
    bron = tmp_path / RO_DEMO.name
    tekst = RO_DEMO.read_text(encoding="utf-8")
    # 31 februari bestaat niet: de datum is gevuld maar niet te parsen.
    bron.write_text(tekst.replace(";1-8-2023;", ";31-2-2023;", 1), encoding="utf-8")
    doel = tmp_path / "prepared"

    run_auto_pipeline(bron, doel, fail_on_errors=False)

    rapport = json.loads((doel / "quality.json").read_text(encoding="utf-8"))
    assert rapport["parseverlies"] == {"ISG": {"DatumInschrijving": 1}}
    assert any("ISG.DatumInschrijving: 1" in e for e in rapport["errors"])


def test_pipeline_meldt_onbekende_datum_als_warning(tmp_path):
    """#391: ``00-00-0000`` als geboortedatum is geen fout maar wel zichtbaar."""
    bron = tmp_path / RO_DEMO.name
    regels = RO_DEMO.read_text(encoding="utf-8").splitlines(keepends=True)
    i = next(i for i, r in enumerate(regels) if r.startswith("PER;"))
    velden = regels[i].split(";")
    velden[3] = "0-0-0000"  # Geboortedatum (PER veld 4)
    regels[i] = ";".join(velden)
    bron.write_text("".join(regels), encoding="utf-8")
    doel = tmp_path / "prepared"

    run_auto_pipeline(bron, doel)

    rapport = json.loads((doel / "quality.json").read_text(encoding="utf-8"))
    assert rapport["onbekende_datums"] == {"PER": {"Geboortedatum": 1}}
    assert rapport["errors"] == []
    assert any("PER.Geboortedatum: 1" in w for w in rapport["warnings"])


def test_parseverlies_blokkeert_standaard(tmp_path):
    """#390: een verloren waarde was een warning bij een geslaagde run (exit 0)."""
    bron = tmp_path / RO_DEMO.name
    tekst = RO_DEMO.read_text(encoding="utf-8")
    bron.write_text(tekst.replace(";1-8-2023;", ";31-2-2023;", 1), encoding="utf-8")

    with pytest.raises(KwaliteitsFout, match="quality.json"):
        run_auto_pipeline(bron, tmp_path / "prepared")
