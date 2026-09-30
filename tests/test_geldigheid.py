"""Tijdsgebonden geldigheid van waardedomeinen (#325).

PvE §16.6 geeft per waarde een geldigheidsperiode, bijv. ``BOL_DT`` t/m
31-07-2023. Een tijdloos domein accepteerde ``BOL_DT`` op elke datum. De
toets gebruikt de ``peildatum`` van het recordtype uit het schema, getypeerd
door decode (zelfde rijvolgorde als de ruwe frames).
"""

import json
from datetime import date

import polars as pl
import pytest

from mbo_bekostiging_bestanden.metadata import load_schema
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline
from mbo_bekostiging_bestanden.waardenlijsten import (
    controleer_waardedomeinen,
    waardedomein,
)


def _toets(veld: str, waarden: list[str], data: list[date | None]) -> dict:
    ruw = {"ISP": pl.DataFrame({veld: waarden})}
    getypeerd = {
        "ISP": pl.DataFrame({"DatumBegin": data}, schema={"DatumBegin": pl.Date})
    }
    return controleer_waardedomeinen(ruw, "ro", getypeerd).get("ISP", {})


@pytest.mark.parametrize(
    ("datum", "buiten"),
    [(date(2023, 7, 31), False), (date(2023, 8, 1), True), (date(2024, 8, 1), True)],
)
def test_bol_dt_is_geldig_tot_en_met_31_juli_2023(datum, buiten):
    afwijking = _toets("Leertraject", ["BOL_DT"], [datum])
    assert ("Leertraject" in afwijking) is buiten
    if buiten:
        assert afwijking["Leertraject"]["buiten_geldigheid"] == 1


def test_leerroutefase_is_pas_geldig_vanaf_1_augustus_2020():
    afwijking = _toets(
        "Leerroutefase", ["VO", "MBO"], [date(2020, 7, 31), date(2020, 8, 1)]
    )
    assert afwijking["Leerroutefase"]["buiten_geldigheid"] == 1


def test_rij_zonder_peildatum_krijgt_geen_tijdstoets_maar_telt_wel():
    """Alle leertrajecten hebben in §16.6 een begindatum, dus beide tellen.
    Leertraject is verplicht (#354), dus lege waarde is een error."""
    afwijking = _toets("Leertraject", ["BOL_DT", "BOL", ""], [None, None, None])
    assert afwijking["Leertraject"] == {
        "aantal": 1,
        "ernst": "error",
        "leeg": 1,
        "zonder_peildatum": 2,
    }


def test_zonder_getypeerde_frames_geen_tijdstoets():
    ruw = {"ISP": pl.DataFrame({"Leertraject": ["BOL_DT"]})}
    assert controleer_waardedomeinen(ruw, "ro") == {}


def test_audit_bewijs_via_de_pipeline(tmp_path):
    """Audit F-04: ``BOL_DT`` met ``DatumBegin = 2024-08-01`` gaf ``{}``."""
    bron = tmp_path / "RO_99XX_20240801_20250731.csv"
    bron.write_text(
        "VLP|99XX|2024-08-01|2025-07-31|2025-08-01\n"
        "PER|BSN1||2001-05-17|V\n"
        "ISG|BSN1||1|2024-08-01|2026-07-31||\n"
        "ISP|BSN1||1|2024-08-01|25618|BOL_DT||J||101A741|100X974|||\n"
        "SLR|1|1|1|0|0|0|0|0|0\n",
        encoding="utf-8",
    )
    run_auto_pipeline(bron, tmp_path / "uit", fail_on_errors=False)
    rapport = json.loads((tmp_path / "uit" / "quality.json").read_text("utf-8"))
    assert rapport["domeinafwijkingen"]["ISP"]["Leertraject"]["buiten_geldigheid"] == 1
    # Leertraject is verplicht en buiten geldigheid geeft error (#354)
    assert any("buiten hun domein" in e for e in rapport["errors"])


@pytest.mark.parametrize("schema", ["ro", "grondslag", "tbgi"])
def test_tijdgebonden_domein_heeft_een_peildatum_in_het_schema(schema):
    for rt, spec in load_schema(schema).items():
        for veld, naam in spec.get("domeinen", {}).items():
            if waardedomein(naam).get("geldigheid"):
                assert spec.get("peildatum") in spec.get("date_fields", []), (rt, veld)


def test_alleen_waarden_uit_het_domein_hebben_een_periode():
    for naam in ("leertraject", "leerroutefase"):
        domein = waardedomein(naam)
        assert set(domein["geldigheid"]) <= set(domein["waarden"])
