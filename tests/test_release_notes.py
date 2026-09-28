"""Release-gate: verwijzingen in de release-notes kloppen (#190).

``--generate-notes`` neemt PR-titels over; een verkeerde ``#NNN`` in een titel
belandde zo ongecontroleerd in de notes van v3.1.1. De gate faalt nu als een
verwijzing niet bestaat, of als een issue dat een PR in de notes sluit, nog
openstaat. De GitHub-opvragingen zijn geïnjecteerd, zodat dit zonder netwerk
te testen is.
"""

import importlib.util
from pathlib import Path

_PAD = Path(__file__).parent.parent / "scripts" / "controleer_release_notes.py"
_spec = importlib.util.spec_from_file_location("controleer_release_notes", _PAD)
assert _spec and _spec.loader
notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(notes)

NOTES = """## What's Changed
* fix(#204): KZD-resultaat exact by @x in https://github.com/o/r/pull/214
* fix(#999): bestaat niet by @x in https://github.com/o/r/pull/215
"""


def test_verwijzingen_uit_titels_en_pr_links():
    assert notes.verwijzingen(NOTES) == {204, 214, 215, 999}


def test_pr_nummers_uit_de_links():
    assert notes.pr_nummers(NOTES) == {214, 215}


def test_niet_bestaande_verwijzing_is_een_fout():
    bestaande = {204, 214, 215}
    fouten = notes.fouten(
        NOTES,
        bestaat=lambda n: n in bestaande,
        pr_body=lambda n: "",
        is_gesloten=lambda n: True,
    )
    assert fouten == ["#999 bestaat niet"]


def test_open_issue_dat_een_pr_sluit_is_een_fout():
    fouten = notes.fouten(
        NOTES,
        bestaat=lambda n: True,
        pr_body=lambda n: "Closes #204\n\nCloses #210" if n == 214 else "",
        is_gesloten=lambda n: n != 210,
    )
    assert fouten == ["#210 staat nog open, maar PR #214 sluit het"]


def test_correcte_notes_geven_geen_fouten():
    fouten = notes.fouten(
        NOTES,
        bestaat=lambda n: True,
        pr_body=lambda n: "Closes #204",
        is_gesloten=lambda n: True,
    )
    assert fouten == []
