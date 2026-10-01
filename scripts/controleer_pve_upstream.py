"""Vergelijk de PvE-versie op duo.nl met de versie in ``metadata/pve_bron.json`` (#299).

Gebruik (in ``.github/workflows/pve-upstream.yml``, apart van de PR-poort omdat
het netwerk nodig heeft)::

    uv run --with pypdf python scripts/controleer_pve_upstream.py

Faalt (exit 1) als DUO een andere versie publiceert dan waarop de schema's zijn
gebaseerd, of als de bestandsbeschrijvingen inhoudelijk afwijken van de
extractie in de repo terwijl de versie gelijk is (#368); dat is het signaal om
de schema's te herzien (#298). Een andere sha256 van de volledige PDF bij gelijke
inhoud is alleen een melding: DUO kan de PDF opnieuw genereren.
"""

import hashlib
import io
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

from pypdf import PdfReader

from mbo_bekostiging_bestanden.metadata import pve_bron

REPO = Path(__file__).parent.parent
_VERSIE = re.compile(r"Versie:\s*(\d+(?:\.\d+)+)\s+Datum:\s*(\d{2}-\d{2}-\d{4})")


def pve_versie(voorblad: str) -> tuple[str, str] | None:
    """``(versie, datum)`` van het voorblad van het PvE, of None."""
    treffer = _VERSIE.search(voorblad)
    return (treffer[1], treffer[2]) if treffer else None


def beoordeel(
    gevonden: tuple[str, str] | None,
    afwijkende_paginas: list[int],
    sha256_volledig: str,
    bron: dict[str, str],
) -> tuple[list[str], list[str]]:
    """``(fouten, meldingen)`` van de upstream-PDF tegenover het manifest.

    Fouten laten de workflow falen: geen versie op het voorblad, een andere
    versie, of een gelijke versie met afwijkende bestandsbeschrijvingen (DUO
    wijzigde de PDF zonder het versienummer te verhogen, #368).
    """
    if gevonden is None:
        return ["Geen versie gevonden op het voorblad van het PvE."], []
    versie, datum = gevonden
    if versie != bron["versie"]:
        return [
            f"DUO publiceert PvE {versie} ({datum}); de schema's zijn gebaseerd op "
            f"{bron['versie']} ({bron['datum']}). Zie #298."
        ], []
    fouten = []
    if afwijkende_paginas:
        fouten.append(
            f"PvE {versie} is inhoudelijk gewijzigd zonder nieuwe versie: "
            f"pagina's {afwijkende_paginas} wijken af van {bron['bestand']}."
        )
    meldingen = []
    if sha256_volledig != bron["sha256_volledig"]:
        meldingen.append(
            "De sha256 van de volledige PDF wijkt af van het manifest "
            f"({sha256_volledig}); "
            + (
                "zie de afwijkende pagina's."
                if afwijkende_paginas
                else "de inhoud is gelijk."
            )
        )
    return fouten, meldingen


def main() -> int:
    # Staat naast dit script, dus op sys.path bij ``python scripts/...``.
    from vergelijk_pve import verschillen

    bron = pve_bron()
    with urllib.request.urlopen(bron["bron_url"], timeout=60) as antwoord:
        inhoud = antwoord.read()
    with tempfile.NamedTemporaryFile(suffix=".pdf") as upstream:
        upstream.write(inhoud)
        upstream.flush()
        afwijkend = sorted(verschillen(REPO / bron["bestand"], Path(upstream.name)))
    gevonden = pve_versie(PdfReader(io.BytesIO(inhoud)).pages[0].extract_text())
    fouten, meldingen = beoordeel(
        gevonden, afwijkend, hashlib.sha256(inhoud).hexdigest(), bron
    )
    for melding in meldingen:
        print(melding)
    for fout in fouten:
        print(fout, file=sys.stderr)
    if fouten:
        return 1
    print(f"PvE {bron['versie']} ({bron['datum']}) komt overeen met pve_bron.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
