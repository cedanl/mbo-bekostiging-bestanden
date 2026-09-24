"""Tests voor de sidebar-jaarselectie die consistent op data-feiten wordt toegepast.

De helpers leven in het package (``mbo_bekostiging_bestanden.filters``) zodat de
app-jaarselectie en de TBGI-bekostigingsfilter los van de UI getest kunnen worden.
"""

import polars as pl

from mbo_bekostiging_bestanden.filters import (
    filter_fact_bekostiging_op_jaar,
    periode_jaar_kolom,
)


def test_periode_jaar_kolom_kiest_periode_variant():
    """Studiejaar_periode heeft voorrang (correct voor periode-analyses)."""
    df = pl.DataFrame({"Studiejaar": [2025], "Studiejaar_periode": [2024]})
    assert periode_jaar_kolom(df) == "Studiejaar_periode"


def test_periode_jaar_kolom_fallbacks_naar_studiejaar():
    """Zonder periode-variant valt het terug op Studiejaar, anders None."""
    assert periode_jaar_kolom(pl.DataFrame({"Studiejaar": [2024]})) == "Studiejaar"
    assert periode_jaar_kolom(pl.DataFrame({"levering": ["h16"]})) is None


def test_bekostiging_filter_hanteert_periodejaar_niet_leveringjaar():
    """De sidebar selecteert op periodejaar; bekostiging moet datzelfde jaar aanhouden.

    Regressie: eerder werd op ``df["Studiejaar"]`` (leveringjaar) gefilterd, waardoor
    bij RO/GRONDSLAG/TBGI-combinaties andere jaren verschenen dan de selectie.
    """
    geselecteerd = pl.DataFrame(
        {
            "levering": ["h17/GRONDSLAG_IP_MBO_27DV_2025"],
            "Studiejaar": [2025],  # leveringjaar — misleidend
            "Studiejaar_periode": [2024],  # werkelijke periode (aug'24–jul'25)
        }
    )
    bek = pl.DataFrame(
        {
            "levering": ["h16/TBGI_25LX_2027", "h16/TBGI_25LX_2027"],
            "Studiejaar": [2024, 2025],  # afgeleid uit Teldatum
            "Bekostigingsstatus": ["Bekostigd", "Niet bekostigd"],
        }
    )

    resultaat = filter_fact_bekostiging_op_jaar(bek, geselecteerd)

    assert resultaat["Studiejaar"].to_list() == [2024]


def test_bekostiging_filter_behoudt_alle_rijen_bij_alle_jaren():
    """Wanneer alle periodejaren geselecteerd zijn, blijft alles behouden."""
    geselecteerd = pl.DataFrame({"Studiejaar_periode": [2024, 2025]})
    bek = pl.DataFrame(
        {
            "levering": ["h16/TBGI", "h16/TBGI", "h16/TBGI"],
            "Studiejaar": [2024, 2025, 2025],
        }
    )

    resultaat = filter_fact_bekostiging_op_jaar(bek, geselecteerd)

    assert resultaat.height == 3


def test_bekostiging_filter_leeg_zonder_selectie():
    """Geen geselecteerde jaren (of leeg df) levert een lege feitentabel."""
    leeg_df = pl.DataFrame(
        schema={
            "Studiejaar": pl.Int64,
            "Studiejaar_periode": pl.Int64,
        }
    )
    bek = pl.DataFrame({"levering": ["h16"], "Studiejaar": [2024]})

    assert filter_fact_bekostiging_op_jaar(bek, leeg_df).is_empty()


def test_bekostiging_filter_ongewijzigd_zonder_jaarkolom_in_feit():
    """Als fact_bekostiging geen Studiejaar kent is er niets te filteren."""
    bek = pl.DataFrame({"levering": ["h16"], "Teldatum": ["2024-10-01"]})
    geselecteerd = pl.DataFrame({"Studiejaar_periode": [2024]})

    resultaat = filter_fact_bekostiging_op_jaar(bek, geselecteerd)

    assert resultaat.height == 1


def test_bekostiging_filter_leeg_zonder_jaarkolom_in_selectie():
    """Als de inschrijvingen geen jaarkolom hebben kan er niet gefilterd worden."""
    bek = pl.DataFrame({"levering": ["h16"], "Studiejaar": [2024]})
    geselecteerd = pl.DataFrame({"levering": ["h17/..."]})

    assert filter_fact_bekostiging_op_jaar(bek, geselecteerd).is_empty()
