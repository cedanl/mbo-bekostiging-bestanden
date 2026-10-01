"""Elk veld heeft een waardedomein of een vastgelegde reden waarom niet (#288).

Velden zonder domein zijn de plekken waar een verschoven regel stil blijft: een
ontbrekend middenveld maakt de regel één veld korter, terwijl de aangrenzende
waarden vaak toevallig geldig blijven. Een getypeerd veld (datum, getal) is
gedekt via het parseverlies; ``Recordsoort`` via de ingest zelf.
"""

import json
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.metadata import load_schema
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline
from mbo_bekostiging_bestanden.waardenlijsten import (
    controleer_waardedomeinen,
    dekkingsoverzicht,
    domeindekking,
    velden_zonder_domein,
)

SCHEMAS = ("ro", "grondslag", "tbgi")


@pytest.mark.parametrize("schema", SCHEMAS)
def test_elk_veld_heeft_een_domein_of_een_reden(schema):
    ongedekt = {
        rt: [veld for veld, dekking in velden.items() if dekking is None]
        for rt, velden in domeindekking(schema).items()
    }
    assert {rt: v for rt, v in ongedekt.items() if v} == {}


def test_tbgi_dekkingsoverzicht_heeft_geen_ongedekte_velden():
    """#356: de belofte \"een domein of een reden per veld\" gold alleen voor RO en
    GRONDSLAG."""
    assert dekkingsoverzicht("tbgi")["geen"] == 0


def test_elke_reden_hoort_bij_een_veld_zonder_domein():
    """Een reden voor een veld dat nergens meer zonder domein staat, is dood."""
    in_gebruik = {
        veld
        for schema in SCHEMAS
        for velden in domeindekking(schema).values()
        for veld, dekking in velden.items()
        if dekking and dekking.startswith("reden:")
    }
    assert set(velden_zonder_domein()) == in_gebruik


@pytest.mark.parametrize(
    ("schema", "rt", "veld", "waarde"),
    [
        # Audit-bewijs: een verschoven datum in RedenUitschrijving gaf geen melding.
        ("grondslag", "ISG", "RedenUitschrijving", "20250101"),
        ("ro", "ISG", "RedenUitschrijving", "20250101"),
        ("ro", "PER", "Geslacht", "X"),
        ("grondslag", "PER", "Geslacht", "X"),
        ("grondslag", "VLP", "BekostigingsType", "X"),
        ("ro", "ISP", "Leerroutefase", "F1"),
        ("grondslag", "ISP", "Leerroute", "20250101"),
        ("ro", "ISP", "LocatiecodeVSV", "VSV001"),
        ("ro", "BPV", "Omvang", "20250101"),
        ("grondslag", "BII", "StatusBepalingBekostigingsstatus", "J"),
        ("grondslag", "BID", "IndicatieSpecialistendiploma", "1"),
        ("grondslag", "BID", "NiveauHoogstBekostigdeDiploma", "4"),
    ],
)
def test_waarde_buiten_het_pve_domein_wordt_gemeld(schema, rt, veld, waarde):
    frames = {rt: pl.DataFrame({veld: [waarde]})}
    assert veld in controleer_waardedomeinen(frames, schema)[rt]


def test_demo_krijgt_geen_nieuwe_meldingen(tmp_path):
    for bron in sorted(Path("data/01-raw/demo").glob("h1[57]/*.csv")):
        run_auto_pipeline(bron, tmp_path / bron.stem)
        rapport = json.loads((tmp_path / bron.stem / "quality.json").read_text("utf-8"))
        assert rapport["domeinafwijkingen"] == {}, bron.name


def test_dekking_noemt_de_soort():
    dekking = domeindekking("ro")
    assert dekking["PER"]["Geslacht"] == "domein:geslacht"
    assert dekking["PER"]["Geboortedatum"] == "type:datum"
    assert dekking["VLP"]["Recordsoort"] == "recordsoort"
    assert (dekking["PER"]["Burgerservicenummer"] or "").startswith("reden:")
    assert set(dekking) == set(load_schema("ro"))


def test_quality_json_rapporteert_de_dekking(tmp_path):
    bron = next(Path("data/01-raw/demo").glob("h17/GRONDSLAG_*.csv"))
    run_auto_pipeline(bron, tmp_path)
    dekking = json.loads((tmp_path / "quality.json").read_text("utf-8"))[
        "domeindekking"
    ]
    assert dekking["geen"] == 0
    assert sum(dekking.values()) == sum(
        len(spec["fields"]) for spec in load_schema("grondslag").values()
    )
