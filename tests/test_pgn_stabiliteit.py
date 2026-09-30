"""Stabiliteit van het omgenummerde GRONDSLAG-PGN over studiejaren (#128).

DUO heeft niet bevestigd dat dezelfde persoon in elk studiejaar hetzelfde
omgenummerde PGN krijgt. De pipeline neemt aan dat het stabiel is (ze koppelt
op het PGN), zegt in ``quality.json`` dat dat onbekend is, en meldt het zodra
de aanname ertoe doet: GRONDSLAG-leveringen van meer dan één studiejaar per
instelling in dezelfde ster.
"""

from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.quality import (
    compile_quality_report,
    kwaliteitsmeldingen,
)


def _meta(studiejaren: list[int | None], brin: str = "27DV") -> dict:
    return {
        "meta_leveringen": pl.DataFrame(
            {
                "levering": [f"L{i}" for i in range(len(studiejaren))],
                "BRIN": [brin] * len(studiejaren),
                "Studiejaar": studiejaren,
            }
        )
    }


def _info(rapport: dict) -> list[str]:
    return [m.tekst for m in kwaliteitsmeldingen(rapport) if m.ernst == "info"]


def test_conformiteit_noemt_de_stabiliteit_onbekend():
    assert compile_quality_report({})["conformiteit"]["pgn_stabiliteit"] == "onbekend"


def test_meerdere_grondslag_studiejaren_per_instelling_geven_een_melding():
    rapport = compile_quality_report(_meta([2024, 2025, None]))
    assert rapport["star"]["grondslag_studiejaren"] == {"27DV": [2024, 2025]}
    assert any("#128" in tekst and "27DV" in tekst for tekst in _info(rapport))
    assert rapport["summary"]["status"] == "pass"


def test_een_studiejaar_geeft_geen_melding():
    rapport = compile_quality_report(_meta([2025, None]))
    assert not any("#128" in tekst for tekst in _info(rapport))


def test_documentatie_benoemt_omnummering_en_pseudonimisering():
    tekst = Path("docs/databestanden/grondslag-ip.md").read_text(encoding="utf-8")
    assert "omgenummerd" in tekst
    assert "#128" in tekst
