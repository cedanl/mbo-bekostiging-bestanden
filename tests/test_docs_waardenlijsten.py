"""``docs/waardenlijsten.md`` volgt ``waardenlijsten.toml`` (docs-audit, P1-3).

De pagina is handgeschreven omdat ze betekenissen toevoegt die niet in de TOML
staan. De waarden, hun volgorde-onafhankelijke verzameling en de geldigheidsdata
komen wel uit de TOML en mogen niet stil afwijken bij een PvE-wijziging.
"""

import re
import tomllib
from datetime import date
from pathlib import Path

from mbo_bekostiging_bestanden.metadata import SCHEMA_DIR

PAGINA = Path("docs/waardenlijsten.md")
# Domein in de TOML -> kop van de sectie op de pagina (een domein met `waarden`).
SECTIES = {
    "niveau": "Niveau",
    "leertraject": "Leertraject",
    "leerroutefase": "Leerroutefase",
    "geslacht": "Geslacht",
    "status_bepaling_bekostigingsstatus": "Status bepaling bekostigingsstatus",
    "bekostigingstype": "Bekostiging (VLP GRONDSLAG)",
}


def _toml() -> dict:
    return tomllib.loads((SCHEMA_DIR / "waardenlijsten.toml").read_text("utf-8"))


def _sectie(kop: str) -> list[str]:
    tekst = PAGINA.read_text(encoding="utf-8")
    m = re.search(rf"^## {re.escape(kop)}\n(.*?)(?=^## |\Z)", tekst, re.M | re.S)
    assert m, f"Sectie '{kop}' ontbreekt in {PAGINA}"
    return [r for r in m.group(1).splitlines() if r.startswith("| `")]


def _waarde(rij: str) -> str:
    m = re.match(r"\| `([^`]+)`", rij)
    assert m, rij
    return m.group(1)


def _datum(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def test_elke_waarde_uit_de_toml_staat_op_de_pagina_en_omgekeerd():
    domeinen = _toml()["domein"]
    for domein, kop in SECTIES.items():
        rijen = _sectie(kop)
        op_pagina = {_waarde(r) for r in rijen}
        assert op_pagina == set(domeinen[domein]["waarden"]), f"{kop}: {domein}"


def test_geldigheidsdata_op_de_pagina_zijn_die_uit_de_toml():
    domeinen = _toml()["domein"]
    for domein in ("leertraject", "leerroutefase"):
        rijen = {_waarde(r): r for r in _sectie(SECTIES[domein])}
        for waarde, gelding in domeinen[domein]["geldigheid"].items():
            assert _datum(gelding["vanaf"]) in rijen[waarde], f"{domein} {waarde}"
            if "tot" in gelding:
                assert _datum(gelding["tot"]) in rijen[waarde], f"{domein} {waarde}"
            elif domein == "leertraject":
                assert rijen[waarde].rstrip(" |").endswith("—"), f"{waarde} loopt door"
