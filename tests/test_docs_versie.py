"""De versieregel en release-notes-lijst in de docs worden gegenereerd, niet getypt."""

import importlib.util
from datetime import date
from pathlib import Path

_REPO = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location(
    "docs_versie", _REPO / "scripts" / "docs_versie.py"
)
assert _spec and _spec.loader
dv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dv)


def test_blokken_in_de_docs_zijn_actueel():
    """Faalt na een versie-bump of nieuwe release-notes; draai docs_versie.py."""
    assert dv.main(["--controleer"]) == 0


def test_versieregel_in_ci_noemt_commit_en_datum():
    regel = dv.versieregel("4.0.0", "abc1234", date(2026, 11, 26))
    assert "**4.0.0**" in regel
    assert "commit/abc1234" in regel
    assert "26-11-2026" in regel


def test_versieregel_zonder_commit_heeft_geen_datum():
    assert dv.versieregel("4.0.0") == "Documentatie bij versie **4.0.0**."


def test_vervang_blok_laat_de_rest_staan():
    tekst = "voor\n<!-- versie -->\noud\n<!-- /versie -->\nna"
    nieuw = dv.vervang_blok(tekst, "versie", "nieuw")
    assert nieuw == "voor\n<!-- versie -->\nnieuw\n<!-- /versie -->\nna"


def test_nieuwere_versie_dan_pyproject_is_niet_uitgebracht(tmp_path):
    (tmp_path / "release-notes").mkdir()
    (tmp_path / "release-notes" / "v1.0.0.md").write_text("# v1.0.0 — a\n")
    (tmp_path / "release-notes" / "v1.1.0.md").write_text("# v1.1.0 — b\n")
    lijst = dv.notes_lijst("1.0.0", tmp_path).splitlines()
    assert lijst[0].endswith("(nog niet uitgebracht)")
    assert "v1.1.0" in lijst[0]
    assert "uitgebracht" not in lijst[1]
