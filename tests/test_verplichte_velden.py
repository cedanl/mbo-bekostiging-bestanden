"""Verplichtheid per veld volgens het PvE, niet per waardedomein (#416, #419).

Voorheen telde een lege waarde alleen als afwijking bij een domein met
``verplicht = true`` (#320). Een PvE-verplicht veld zonder zo'n domein, zoals
RO-VLP ``DatumEindePeriode`` of RO-ISP ``Opleidingcode``, ging leeg zonder
melding door. Nu staat per recordtype ``verplichte_velden`` in het schema
(PvE "Verplicht: Ja" / "V"); een lege waarde daarin is een error.
"""

from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.metadata import load_schema
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline
from mbo_bekostiging_bestanden.quality import KwaliteitsFout
from mbo_bekostiging_bestanden.waardenlijsten import (
    controleer_waardedomeinen,
    waardedomein,
)

DEMO_RO = Path("data/01-raw/demo/h15/RO_21CY_20250730_20250731.csv")
SCHEMAS = ("ro", "grondslag", "tbgi")


@pytest.mark.parametrize(
    ("schema", "recordtype", "veld"),
    [
        ("ro", "VLP", "DatumEindePeriode"),  # PvE §15.5.1
        ("ro", "ISP", "Opleidingcode"),  # PvE §15.5.4
        ("tbgi", "Diploma", "Inschrijvingvolgnummer"),  # PvE §16.5.6
    ],
)
@pytest.mark.parametrize("leeg", ["", "  ", None])
def test_leeg_verplicht_veld_is_een_error(schema, recordtype, veld, leeg):
    frames = {recordtype: pl.DataFrame({veld: ["x", leeg]}, schema={veld: pl.Utf8})}
    afwijking = controleer_waardedomeinen(frames, schema)[recordtype][veld]
    assert afwijking["ernst"] == "error"
    assert afwijking["leeg"] == 1


def test_leeg_optioneel_veld_telt_niet():
    """GRONDSLAG-DIP ``IndicatieBekostigbaar`` is "O" in PvE §17.5."""
    frames = {"DIP": pl.DataFrame({"IndicatieBekostigbaar": ["1", ""]})}
    assert controleer_waardedomeinen(frames, "grondslag") == {}


def test_leeg_en_buiten_domein_samen_blijft_error():
    """Een waarde buiten een warning-domein naast een leeg verplicht veld."""
    frames = {"ISP": pl.DataFrame({"Opleidingcode": ["ABC", ""]})}
    afwijking = controleer_waardedomeinen(frames, "ro")["ISP"]["Opleidingcode"]
    assert afwijking == {"aantal": 2, "ernst": "error", "leeg": 1}


@pytest.mark.parametrize("schema", SCHEMAS)
def test_verplichte_velden_staan_in_het_recordtype(schema):
    for recordtype, spec in load_schema(schema).items():
        verplicht = set(spec.get("verplichte_velden", []))
        assert verplicht <= set(spec["fields"]), recordtype
        assert "Recordsoort" not in verplicht, recordtype
        # Een optioneel achterveld mag ontbreken (#281), dus niet verplicht zijn.
        assert not verplicht & set(spec.get("optionele_achtervelden", [])), recordtype


@pytest.mark.parametrize("schema", SCHEMAS)
def test_domeinen_bepalen_geen_verplichtheid(schema):
    """Eén bron: verplichtheid staat in het schema, niet in waardenlijsten.toml."""
    for spec in load_schema(schema).values():
        for naam in spec.get("domeinen", {}).values():
            assert "verplicht" not in waardedomein(naam), naam


def test_pipeline_faalt_bij_lege_opleidingcode(tmp_path):
    regels = DEMO_RO.read_text(encoding="utf-8").splitlines(keepends=True)
    i = next(n for n, r in enumerate(regels) if r.startswith("ISP;"))
    velden = regels[i].split(";")
    velden[load_schema("ro")["ISP"]["fields"].index("Opleidingcode")] = ""
    regels[i] = ";".join(velden)
    bron = tmp_path / DEMO_RO.name
    bron.write_text("".join(regels), encoding="utf-8")

    with pytest.raises(KwaliteitsFout):
        run_auto_pipeline(bron, tmp_path / "prepared")
