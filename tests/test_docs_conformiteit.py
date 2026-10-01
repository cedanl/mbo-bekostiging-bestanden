"""De docs noemen de sleutels van het conformiteitsblok zoals ze nu bestaan (#364)."""

import json
from pathlib import Path

DOCS = Path("docs")
SCHEMA = DOCS / "quality.schema.json"
BESCHRIJVING = DOCS / "aan-de-slag.md"
# Vervallen sleutels: de docs mogen ze alleen als vervallen noemen.
VERVALLEN = ("pve_schema",)


def test_aan_de_slag_noemt_elke_conformiteitssleutel():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    sleutels = schema["properties"]["conformiteit"]["properties"]
    tekst = BESCHRIJVING.read_text(encoding="utf-8")
    ontbrekend = [s for s in sleutels if f"`{s}`" not in tekst]
    assert not ontbrekend, f"Niet beschreven in {BESCHRIJVING}: {ontbrekend}"


def test_docs_beschrijven_geen_vervallen_conformiteitssleutel_als_actueel():
    for pad in DOCS.glob("*.md"):
        for regel in pad.read_text(encoding="utf-8").splitlines():
            for sleutel in VERVALLEN:
                if sleutel in regel:
                    assert "vervallen" in regel, f"{pad}: {regel[:80]}"
