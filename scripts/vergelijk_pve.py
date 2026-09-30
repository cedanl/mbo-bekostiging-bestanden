"""Vergelijk de bestandsbeschrijvingen van twee PvE-versies per pagina (#298).

Gebruik bij een nieuwe PvE-versie (zie ``scripts/controleer_pve_upstream.py``)::

    uv run --with pypdf python scripts/vergelijk_pve.py \\
        bestandsbeschrijving_beknopt.pdf pve-mbo-instellingen.pdf \\
        --extractie bestandsbeschrijving_beknopt.pdf

Pagina's worden gekoppeld op het nummer in de footer ("Pagina N van M"), dus
``oud`` mag de beknopte extractie zijn en ``nieuw`` het volledige PvE. Versie-
strings en witruimte tellen niet mee. Met ``--extractie`` worden dezelfde
pagina's uit ``nieuw`` weggeschreven als nieuwe beknopte extractie. Exit 1 als
een pagina inhoudelijk verschilt of ontbreekt: dan moeten de schema's herzien.
"""

import argparse
import difflib
import re
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

_PAGINA = re.compile(r"Pagina (\d+) van \d+")
_VERSIE = re.compile(r"(?i)\bversie:?\s*\d+\.\d+\.\d+")


def normaliseer(tekst: str) -> str:
    """Tekst zonder versiestring en met enkele spaties."""
    return " ".join(_VERSIE.sub("versie", tekst).split())


def paginanummer(tekst: str) -> int | None:
    treffer = _PAGINA.search(tekst)
    return int(treffer[1]) if treffer else None


def _paginas(pdf: Path) -> dict[int, tuple[int, str]]:
    """Footer-paginanummer → (index in het bestand, tekst)."""
    uit = {}
    for index, pagina in enumerate(PdfReader(pdf).pages):
        tekst = pagina.extract_text() or ""
        nummer = paginanummer(tekst)
        if nummer is not None:
            uit[nummer] = (index, tekst)
    return uit


def verschillen(oud: Path, nieuw: Path) -> dict[int, list[str]]:
    """Per pagina van ``oud``: de afwijkende regels in ``nieuw`` (leeg = gelijk)."""
    nieuwe = _paginas(nieuw)
    uit: dict[int, list[str]] = {}
    for nummer, (_, tekst) in sorted(_paginas(oud).items()):
        if nummer not in nieuwe:
            uit[nummer] = ["pagina ontbreekt in de nieuwe versie"]
            continue
        nieuwe_tekst = nieuwe[nummer][1]
        if normaliseer(tekst) == normaliseer(nieuwe_tekst):
            continue
        uit[nummer] = [
            regel
            for regel in difflib.unified_diff(
                [normaliseer(r) for r in tekst.splitlines()],
                [normaliseer(r) for r in nieuwe_tekst.splitlines()],
                lineterm="",
                n=0,
            )
            if not regel.startswith(("---", "+++", "@@"))
        ]
    return uit


def schrijf_extractie(oud: Path, nieuw: Path, doel: Path) -> int:
    """Schrijf de pagina's van ``oud`` (op footernummer) uit ``nieuw`` naar ``doel``."""
    nieuwe = _paginas(nieuw)
    lezer = PdfReader(nieuw)
    schrijver = PdfWriter()
    for nummer in sorted(_paginas(oud)):
        schrijver.add_page(lezer.pages[nieuwe[nummer][0]])
    with doel.open("wb") as f:
        schrijver.write(f)
    return len(schrijver.pages)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vergelijk de bestandsbeschrijvingen van twee PvE-versies."
    )
    parser.add_argument("oud", type=Path)
    parser.add_argument("nieuw", type=Path)
    parser.add_argument("--extractie", type=Path)
    args = parser.parse_args(argv)

    gevonden = verschillen(args.oud, args.nieuw)
    for nummer, regels in gevonden.items():
        print(f"Pagina {nummer}:")
        for regel in regels:
            print(f"  {regel}")
    if args.extractie:
        n = schrijf_extractie(args.oud, args.nieuw, args.extractie)
        print(f"{n} pagina's geschreven naar {args.extractie}")
    if gevonden:
        print(f"{len(gevonden)} pagina('s) verschillen inhoudelijk.", file=sys.stderr)
        return 1
    print("Geen inhoudelijke verschillen in de bestandsbeschrijvingen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
