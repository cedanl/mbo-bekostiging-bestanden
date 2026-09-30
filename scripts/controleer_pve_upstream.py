"""Vergelijk de PvE-versie op duo.nl met de versie in ``metadata/pve_bron.json`` (#299).

Gebruik (in ``.github/workflows/pve-upstream.yml``, apart van de PR-poort omdat
het netwerk nodig heeft)::

    uv run --with pypdf python scripts/controleer_pve_upstream.py

Faalt (exit 1) als DUO een andere versie publiceert dan waarop de schema's zijn
gebaseerd; dat is het signaal om de schema's te herzien (#298).
"""

import io
import re
import sys
import urllib.request

from pypdf import PdfReader

from mbo_bekostiging_bestanden.metadata import pve_bron

_VERSIE = re.compile(r"Versie:\s*(\d+(?:\.\d+)+)\s+Datum:\s*(\d{2}-\d{2}-\d{4})")


def pve_versie(voorblad: str) -> tuple[str, str] | None:
    """``(versie, datum)`` van het voorblad van het PvE, of None."""
    treffer = _VERSIE.search(voorblad)
    return (treffer[1], treffer[2]) if treffer else None


def main() -> int:
    bron = pve_bron()
    with urllib.request.urlopen(bron["bron_url"], timeout=60) as antwoord:
        pdf = PdfReader(io.BytesIO(antwoord.read()))
    gevonden = pve_versie(pdf.pages[0].extract_text())
    if gevonden is None:
        print("Geen versie gevonden op het voorblad van het PvE.", file=sys.stderr)
        return 1
    versie, datum = gevonden
    if versie != bron["versie"]:
        print(
            f"DUO publiceert PvE {versie} ({datum}); de schema's zijn gebaseerd op "
            f"{bron['versie']} ({bron['datum']}). Zie #298.",
            file=sys.stderr,
        )
        return 1
    print(f"PvE {versie} ({datum}) komt overeen met pve_bron.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
