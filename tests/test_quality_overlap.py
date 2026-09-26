"""Overlap tussen leveringen in de ster is na canonicalisatie een fout (#175).

Canonicalisatie (#174) houdt per inschrijving (BRIN × persoon × volgnummer)
één levering over. Staat een inschrijving daarna nog in meerdere leveringen in
``fact_inschrijving``, dan telt de output dubbel: dat is een error, geen
waarschuwing. Dezelfde persoon en volgnummer bij een andere instelling is een
andere inschrijving en geen overlap.
"""

import polars as pl

from mbo_bekostiging_bestanden.quality import compile_quality_report


def _star(*rijen: tuple[str, str, str, str]) -> dict[str, pl.DataFrame]:
    feit = pl.DataFrame(
        rijen,
        schema=["levering", "BRIN", "_persoon_id", "Inschrijvingvolgnummer"],
        orient="row",
    )
    return {"fact_inschrijving": feit}


def test_resterende_overlap_is_fout():
    rapport = compile_quality_report(
        _star(("L_a", "27DV", "P", "1"), ("L_b", "27DV", "P", "1"))
    )

    assert len(rapport["star"]["overlapping_deliveries"]) == 1
    assert rapport["summary"]["status"] == "fail"


def test_andere_instelling_is_geen_overlap():
    rapport = compile_quality_report(
        _star(("L_a", "21CY", "P", "1"), ("L_b", "27DV", "P", "1"))
    )

    assert rapport["star"]["overlapping_deliveries"] == []
