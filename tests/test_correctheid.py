"""Hand-berekende correctheidsfixture naast de demo-snapshot (#181).

De demo-snapshot legt vast wat de pipeline doet; deze test legt vast wat juist
is. Twee synthetische RO-leveringen (``tests/fixtures/correctheid/``, BRIN
99XX, niet de demodata) met vijf deelnemers; elke verwachting hieronder is met
de hand afgeleid uit de regel die erbij staat, niet uit pipeline-output.

Schooljaar t loopt van 1-8-t t/m 31-7-(t+1), peildatum 1-10-t
(``docs/datamodel.md``). De nieuwe levering kan peildata tot en met 1-10-2025
waarnemen (``DatumEindePeriode`` 2026-03-24, #211).

Deelnemers, situatie → regel:

- P1: MBO-3 vanaf 1-8-2023, werkelijk uitgeschreven 15-7-2024, diploma
  30-6-2024 → JR-teller (diploma in het schooljaar zelf, #194); DR-noemer en
  -teller (geen inschrijving in 2024, en 1-10-2024 is waarneembaar).
- P2: begint 1-8-2024, werkelijk uitgeschreven 30-9-2024 →
  ``DatumUitschrijvingWerkelijk`` is een harde grens (#163): niet actief op
  1-10-2024, dus geen schooljaarrij.
- P3: twee gelijktijdige inschrijvingen, 1 (MBO-2) en 2 (MBO-4) → de
  hoofdinschrijving is het hoogste niveau (#130).
- P4: open periode MBO-4 vanaf 1-8-2023 → telt in elk schooljaar waarvan de
  peildatum gedekt is (#193); nooit uitstromer, 2026 is niet waarneembaar.
- P5: in de oude levering (opleiding 25010) én de nieuwe (25020) → de levering
  met de recentste ``DatumAanmaak`` wint (canonicalisatie, #175).
"""

from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline, run_star
from mbo_bekostiging_bestanden.transform import pseudoniem

FIXTURES = Path(__file__).parent / "fixtures" / "correctheid"
NIEUW = "RO_99XX_20230801_20260324"
OUD = "RO_99XX_20240801_20250731"
BSN = {f"P{i}": f"10000000{i}" for i in range(1, 6)}


@pytest.fixture(scope="module")
def star(tmp_path_factory) -> dict[str, pl.DataFrame]:
    prepared = tmp_path_factory.mktemp("prepared")
    for bron in sorted(FIXTURES.glob("*.csv")):
        run_auto_pipeline(bron, prepared / bron.stem)
    doel = tmp_path_factory.mktemp("star")
    return run_star(sorted(prepared.iterdir()), doel, relative_to=prepared)


def _jaren(star: dict[str, pl.DataFrame], deelnemer: str) -> pl.DataFrame:
    persoon = pseudoniem("BSN", BSN[deelnemer])
    return (
        star["fact_inschrijving_schooljaar"]
        .filter(pl.col("_persoon_id") == persoon)
        .sort("Schooljaar", "Inschrijvingvolgnummer")
    )


def test_p1_gediplomeerde_uitstromer_telt_in_jr_en_dr(star):
    rij = _jaren(star, "P1").row(0, named=True)
    assert rij["Schooljaar"] == 2023
    assert (rij["_jr_noemer"], rij["_jr_teller"]) == (True, True)
    assert (rij["_dr_noemer"], rij["_dr_teller"]) == (True, True)
    assert _jaren(star, "P1").height == 1


def test_p2_uitgeschreven_voor_1_oktober_telt_niet(star):
    assert _jaren(star, "P2").is_empty()


def test_p3_hoofdinschrijving_is_het_hoogste_niveau(star):
    hoofd = _jaren(star, "P3").filter(pl.col("_hoofdinschrijving"))
    assert hoofd.select("Schooljaar", "Inschrijvingvolgnummer").rows() == [
        (2024, "2"),
        (2025, "2"),
    ]


def test_p4_open_periode_telt_elk_waarneembaar_schooljaar(star):
    jaren = _jaren(star, "P4")
    assert jaren["Schooljaar"].to_list() == [2023, 2024, 2025]
    assert jaren["_dr_noemer"].to_list() == [False, False, False]


def test_p5_nieuwste_levering_wint(star):
    jaren = _jaren(star, "P5")
    assert jaren.select("Schooljaar", "Opleidingcode").rows() == [
        (2024, "25020"),
        (2025, "25020"),
    ]
    assert jaren["levering"].unique().to_list() == [NIEUW]
    vervangen = star["meta_canonicalisatie"]
    assert vervangen.select("levering", "vervangen_door", "inschrijvingen").rows() == [
        (OUD, NIEUW, 1)
    ]


def test_jr_en_dr_hebben_positieve_tellers(star):
    jaren = star["fact_inschrijving_schooljaar"]
    assert jaren["_jr_teller"].sum() == 1
    assert jaren["_dr_teller"].sum() == 1
