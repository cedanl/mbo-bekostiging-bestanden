"""Bestanden selecteren als alternatief voor de vaste invoermap (#436).

De selectie wordt in een werkmap buiten de repo gezet (ruwe DUO-bestanden zijn
persoonsgegevens) en wordt daarna net als een invoermap gescand en verwerkt.
"""

import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path

# Eerste submap onder de werkmap: ``Home`` groepeert de brondata op deze naam.
SELECTIEMAP = "selectie"
_WERKMAP_PREFIX = "mbo-selectie-"
_ONGELDIGE_NAMEN = {"", ".", ".."}


def maak_werkmap() -> Path:
    """Nieuwe, lege werkmap in de tijdelijke map van het systeem."""
    return Path(tempfile.mkdtemp(prefix=_WERKMAP_PREFIX))


def synchroniseer_selectie(
    bestanden: Iterable[tuple[str, bytes]], werkmap: Path
) -> Path:
    """Maak ``werkmap/selectie`` gelijk aan de gekozen bestanden.

    Alleen de bestandsnaam telt (padgedeelten worden weggehaald, zodat een
    naam de map niet kan verlaten). Een bestand met gelijke grootte blijft
    staan: Streamlit draait het script bij elke interactie opnieuw en de
    bestanden zijn groot.

    Returns:
        De map met de gekozen bestanden.
    """
    doel = werkmap / SELECTIEMAP
    doel.mkdir(parents=True, exist_ok=True)
    gekozen = {
        Path(naam).name: inhoud
        for naam, inhoud in bestanden
        if Path(naam).name not in _ONGELDIGE_NAMEN
    }

    for bestaand in doel.iterdir():
        if bestaand.name not in gekozen:
            shutil.rmtree(bestaand) if bestaand.is_dir() else bestaand.unlink()
    for naam, inhoud in gekozen.items():
        pad = doel / naam
        if not pad.exists() or pad.stat().st_size != len(inhoud):
            pad.write_bytes(inhoud)
    return doel
