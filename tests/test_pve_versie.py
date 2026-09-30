"""De PvE-versie staat op één plek: ``metadata/pve_bron.json`` (#199, #298).

``bestandsbeschrijving_beknopt.pdf`` is de bron van de veldindelingen. Het
manifest noemt de versie van die PDF; de schema's verwijzen naar de PDF maar
herhalen de versie niet, zodat een versie-update één wijziging is.
"""

import re
import tomllib
from pathlib import Path

import pytest
from pypdf import PdfReader

from mbo_bekostiging_bestanden.metadata import pve_bron

PDF = Path("bestandsbeschrijving_beknopt.pdf")
METADATA = Path("src/mbo_bekostiging_bestanden/metadata")
SCHEMAS = sorted(METADATA.glob("*_schema.toml"))


def _pdf_versie() -> str:
    tekst = PdfReader(PDF).pages[1].extract_text()
    match = re.search(r"DUO versie (\d+\.\d+\.\d+)", tekst)
    assert match, "PvE-versie niet gevonden in de footer van de PDF"
    return match.group(1)


def test_er_zijn_schemas():
    assert {p.name for p in SCHEMAS} >= {
        "ro_schema.toml",
        "grondslag_schema.toml",
        "tbgi_schema.toml",
    }


def test_manifest_noemt_de_versie_van_de_pdf():
    assert pve_bron()["versie"] == _pdf_versie()


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda p: p.stem)
def test_schema_herhaalt_de_versie_niet(schema):
    tekst = schema.read_text(encoding="utf-8")
    assert "schema_version" not in tomllib.loads(tekst)
    # Een versie na "PvE" of "versie"; "PvE §15.5.2" is een paragraaf, geen versie.
    versie = re.search(r"(?i)(pve|versie)[^\n§]{0,40}?\b\d+\.\d+\.\d+", tekst)
    assert not versie, f"versie hoort in pve_bron.json: {versie and versie[0]!r}"


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda p: p.stem)
def test_schema_verwijst_naar_de_pdf(schema):
    assert PDF.name in schema.read_text(encoding="utf-8")
