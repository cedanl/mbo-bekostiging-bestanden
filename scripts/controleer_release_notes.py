"""Release-gate: controleer de verwijzingen in gegenereerde release-notes (#190).

Gebruik (in ``.github/workflows/release.yml``)::

    python3 scripts/controleer_release_notes.py <notes-bestand> <owner/repo>

Faalt (exit 1) als een ``#NNN`` in de notes niet bestaat, of als een issue dat
een PR in de notes met ``Closes #NNN`` sluit, nog openstaat. Vraagt GitHub op
via ``gh api``; de controlelogica is los daarvan te testen.
"""

import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

_VERWIJZING = re.compile(r"(?<![\w/])#(\d+)\b")
_PR_LINK = re.compile(r"/pull/(\d+)\b")
_SLUIT = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.I)


def pr_nummers(notes: str) -> set[int]:
    """PR-nummers uit de links die ``--generate-notes`` per regel zet."""
    return {int(n) for n in _PR_LINK.findall(notes)}


def verwijzingen(notes: str) -> set[int]:
    """Alle ``#NNN``-verwijzingen plus de PR's uit de links."""
    return {int(n) for n in _VERWIJZING.findall(notes)} | pr_nummers(notes)


def fouten(
    notes: str,
    bestaat: Callable[[int], bool],
    pr_body: Callable[[int], str],
    is_gesloten: Callable[[int], bool],
) -> list[str]:
    """Beschrijving van elke onjuiste verwijzing; leeg als alles klopt."""
    uit = [f"#{n} bestaat niet" for n in sorted(verwijzingen(notes)) if not bestaat(n)]
    for pr in sorted(pr_nummers(notes)):
        for issue in sorted({int(n) for n in _SLUIT.findall(pr_body(pr))}):
            if not is_gesloten(issue):
                uit.append(f"#{issue} staat nog open, maar PR #{pr} sluit het")
    return uit


def _gh(repo: str, pad: str) -> dict | None:
    resultaat = subprocess.run(
        ["gh", "api", f"repos/{repo}/{pad}"], capture_output=True, text=True
    )
    return json.loads(resultaat.stdout) if resultaat.returncode == 0 else None


def main(notes_pad: str, repo: str) -> int:
    notes = Path(notes_pad).read_text(encoding="utf-8")
    gevonden = fouten(
        notes,
        bestaat=lambda n: _gh(repo, f"issues/{n}") is not None,
        pr_body=lambda n: (_gh(repo, f"pulls/{n}") or {}).get("body") or "",
        is_gesloten=lambda n: (_gh(repo, f"issues/{n}") or {}).get("state") == "closed",
    )
    for fout in gevonden:
        print(f"::error::Release-notes: {fout}")
    return 1 if gevonden else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
