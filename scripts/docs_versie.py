"""Houdt de versieregel en de lijst release-notes in de docs gelijk aan de repo.

Gebruik::

    python3 scripts/docs_versie.py                  # herschrijf de blokken
    python3 scripts/docs_versie.py --controleer     # exit 1 als een blok afwijkt
    python3 scripts/docs_versie.py --commit <sha>   # CI: voeg commit en datum toe

Twee blokken in ``docs/*.md`` worden hergeschreven, tussen deze markeringen:

- ``<!-- versie -->`` ... ``<!-- /versie -->``: de versie uit ``pyproject.toml``;
- ``<!-- release-notes -->`` ... ``<!-- /release-notes -->``: een regel per
  ``release-notes/v*.md``. Een versie boven die in ``pyproject.toml`` is nog niet
  uitgebracht.

In CI draait het script vóór de build met ``--commit``; het resultaat wordt niet
gecommit. De commit en de datum staan dus alleen op de gepubliceerde site.
"""

import argparse
import re
import sys
import tomllib
from datetime import date
from pathlib import Path

REPO = Path(__file__).parent.parent
REPO_URL = "https://github.com/cedanl/mbo-bekostiging-bestanden"
_BLOK = r"(<!-- {naam} -->)\n.*?\n(<!-- /{naam} -->)"


def versie(repo: Path = REPO) -> str:
    """Pakketversie uit ``pyproject.toml``."""
    data = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def _sleutel(v: str) -> tuple[int, ...]:
    return tuple(int(d) for d in v.lstrip("v").split("."))


def versieregel(
    huidig: str, commit: str | None = None, vandaag: date | None = None
) -> str:
    """De regel "Documentatie bij versie ..."; met commit en datum in CI."""
    regel = f"Documentatie bij versie **{huidig}**"
    if commit:
        dag = (vandaag or date.today()).strftime("%d-%m-%Y")
        regel += (
            f" · [commit `{commit}`]({REPO_URL}/commit/{commit}) · gebouwd op {dag}"
        )
    return regel + "."


def notes_lijst(huidig: str, repo: Path = REPO) -> str:
    """Eén lijstregel per release-notes-bestand, nieuwste eerst."""
    regels = []
    bestanden = sorted(
        (repo / "release-notes").glob("v*.md"),
        key=lambda p: _sleutel(p.stem),
        reverse=True,
    )
    for pad in bestanden:
        titel = pad.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        regel = f"- [{titel}]({REPO_URL}/blob/main/release-notes/{pad.name})"
        if _sleutel(pad.stem) > _sleutel(huidig):
            regel += " (nog niet uitgebracht)"
        regels.append(regel)
    return "\n".join(regels)


def vervang_blok(tekst: str, naam: str, inhoud: str) -> str:
    """Zet ``inhoud`` tussen de markeringen van blok ``naam`` (alle voorkomens)."""
    patroon = re.compile(_BLOK.format(naam=re.escape(naam)), re.S)
    return patroon.sub(lambda m: f"{m.group(1)}\n{inhoud}\n{m.group(2)}", tekst)


def bijgewerkt(tekst: str, huidig: str, notes: str, commit: str | None = None) -> str:
    """``tekst`` met beide blokken bijgewerkt."""
    tekst = vervang_blok(tekst, "versie", versieregel(huidig, commit))
    return vervang_blok(tekst, "release-notes", notes)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Versie en release-notes in de docs bijwerken"
    )
    ap.add_argument("--controleer", action="store_true")
    ap.add_argument("--commit", help="commit-sha voor de gepubliceerde site (CI)")
    args = ap.parse_args(argv)
    huidig, notes = versie(), notes_lijst(versie())
    afwijkend = []
    for pad in sorted((REPO / "docs").rglob("*.md")):
        oud = pad.read_text(encoding="utf-8")
        nieuw = bijgewerkt(oud, huidig, notes, args.commit)
        if nieuw != oud:
            afwijkend.append(pad.relative_to(REPO).as_posix())
            if not args.controleer:
                pad.write_text(nieuw, encoding="utf-8")
    if args.controleer and afwijkend:
        print(f"Verouderd: {afwijkend}; draai scripts/docs_versie.py", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
