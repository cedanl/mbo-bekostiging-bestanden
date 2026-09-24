"""Elke documentatiepagina is vindbaar via de MkDocs-navigatie (#110)."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"


def _nav_paginas() -> set[str]:
    tekst = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    nav = tekst[tekst.index("\nnav:") :]
    return set(re.findall(r"([\w./-]+\.md)", nav))


def test_alle_docs_paginas_staan_in_nav():
    paginas = {p.relative_to(DOCS).as_posix() for p in DOCS.rglob("*.md")}
    ontbrekend = paginas - _nav_paginas()
    assert not ontbrekend, f"Niet in mkdocs-nav: {sorted(ontbrekend)}"
