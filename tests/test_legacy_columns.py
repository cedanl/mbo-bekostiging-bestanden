"""``fact_inschrijving`` heeft geen jaargebonden vlaggen meer (#201).

Ze stonden er sinds #164 dubbel naast ``fact_inschrijving_schooljaar``, met
dezelfde namen maar andere getallen (demo: ``_dr_noemer`` 19 tegenover 6).
Na markering in v3.2.0–v3.4.0 zijn ze in v4.0.0 verwijderd; de schooljaar-fact
is de enige bron.
"""

import pytest

from mbo_bekostiging_bestanden.contracts import SCHOOLJAAR_FEIT

# De kolommen zoals ze tot en met v3.4.0 in fact_inschrijving stonden.
VERWIJDERD = (
    "_actief_1_oktober",
    "_bekostigd_eerste_1okt",
    "_gediplomeerd_in_jaar",
    "_ingeschreven_jaar_later",
    "_deelnemer_niet_bekostigd_eerste_1okt",
    "_hoogste_niveau",
    "_laagste_CREBO",
    "_hoofdinschrijving",
    "_telling",
    "_jr_noemer",
    "_jr_teller",
    "_dr_noemer",
    "_dr_teller",
    "_entree_uitstroom",
    "_entree_doorstroom",
    "Opbrengstjaar_uitsplitsing",
    "_driejaars_teljaar",
    "Opbrengstjaar_3jaars_voortschrijdend",
    "_num_opbrengstjaar_3jr",
    "_schooljaren_actief",
)


@pytest.mark.parametrize("bron", ["demo_star", "demo_tabellen"])
def test_periode_grain_heeft_geen_jaarvlaggen(bron, request):
    tabellen = request.getfixturevalue(bron)
    tabel = "fact_inschrijving" if bron == "demo_star" else "inschrijvingen"
    assert set(VERWIJDERD) & set(tabellen[tabel].columns) == set()


def test_schooljaar_fact_draagt_de_indicatoren(demo_star):
    """De gedeelde namen blijven bestaan, op de schooljaar-grain."""
    kolommen = set(demo_star[SCHOOLJAAR_FEIT].columns)
    assert {"_telling", "_jr_noemer", "_jr_teller", "_dr_noemer", "_dr_teller"} <= (
        kolommen
    )
    assert {"_hoofdinschrijving", "_entree_uitstroom"} <= kolommen
