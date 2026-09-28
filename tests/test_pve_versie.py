"""Schema's pinnen de PvE-versie van de bestandsbeschrijving in de repo (#199).

``bestandsbeschrijving_beknopt.pdf`` is de bron van de veldindelingen. Een
schema met een andere (of niet-bestaande) versie dan die PDF faalt, net als
een schema dat niet naar de PDF verwijst.
"""

import re
import tomllib
from pathlib import Path

import pytest
from pypdf import PdfReader

PDF = Path("bestandsbeschrijving_beknopt.pdf")
METADATA = Path("src/mbo_bekostiging_bestanden/metadata")
SCHEMAS = sorted(METADATA.glob("*_schema.toml"))


def _pve_versie() -> str:
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


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda p: p.stem)
def test_schema_versie_is_die_van_de_pdf(schema):
    versie = tomllib.loads(schema.read_text(encoding="utf-8"))["schema_version"]
    assert versie == _pve_versie()


@pytest.mark.parametrize("schema", SCHEMAS, ids=lambda p: p.stem)
def test_schema_verwijst_naar_de_pdf(schema):
    assert PDF.name in schema.read_text(encoding="utf-8")
