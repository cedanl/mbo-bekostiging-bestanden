"""Het dashboard is opgesplitst per tab; de page orkestreert alleen (#301).

Het gedrag toetsen de AppTest-tests (``test_dashboard_jaren``,
``test_conformiteit``, ``test_kwaliteitsmeldingen``). Hier gaat het om de
opbouw: rendering per tab in ``app/_dashboard``, en elke grafiek met een
toelichting in ``app/_chart_docs.py`` (CLAUDE.md: een grafiek zonder
toelichting is niet af).
"""

import re
from pathlib import Path

import polars as pl
import pytest
from _chart_docs import CHART_DOCS
from _dashboard import data
from _dashboard.grafieken import sorteer_aantal

APP = Path(__file__).parents[1] / "app"
PAGE = APP / "pages" / "dashboard.py"
MODULES = sorted((APP / "_dashboard").glob("*.py"))
TABS = (
    "tab_rendementen",
    "tab_bekostiging",
    "tab_opleidingen",
    "tab_studenten",
    "tab_examens",
    "tab_opleidingsstructuur",
)
_CHART_HELP = re.compile(r"""chart_help\(\s*["'](\w+)["']""")


def _gebruikte_toelichtingen() -> set[str]:
    return {
        key
        for pad in (PAGE, *MODULES)
        for key in _CHART_HELP.findall(pad.read_text(encoding="utf-8"))
    }


def test_elke_tab_heeft_een_eigen_module():
    assert {p.stem for p in MODULES} >= set(TABS)


def test_page_rendert_zelf_geen_grafieken():
    tekst = PAGE.read_text(encoding="utf-8")
    for rendering in ("chart_help(", "st.subheader(", "st.bar_chart(", "alt.Chart("):
        assert rendering not in tekst, rendering


def test_elke_grafiek_heeft_een_toelichting():
    assert _gebruikte_toelichtingen() <= set(CHART_DOCS)


def test_elke_toelichting_hoort_bij_een_grafiek():
    assert set(CHART_DOCS) <= _gebruikte_toelichtingen()


def test_selectie_filtert_elk_feit_op_de_schooljaren():
    """Laden en jaarselectie zijn los van de weergave te toetsen."""
    jaren = pl.DataFrame(
        {"Schooljaar": [2023, 2024], "_inschrijving_periode_id": ["p1", "p2"]}
    )
    ster = data.Ster(
        inschrijvingen=pl.DataFrame({"_inschrijving_periode_id": ["p1", "p2"]}),
        geo=pl.DataFrame(),
        bpv=pl.DataFrame(),
        kzd=pl.DataFrame(),
        bekostiging=pl.DataFrame(),
        jaren=jaren,
        meta_leveringen=pl.DataFrame(),
    )
    selectie = data.selecteer(ster, [2024])
    assert selectie.schooljaren == [2024]
    assert selectie.jaren["Schooljaar"].to_list() == [2024]


@pytest.mark.parametrize("tab", TABS)
def test_tab_module_heeft_een_toon_functie(tab):
    module = __import__(f"_dashboard.{tab}", fromlist=["toon"])
    assert callable(module.toon)


def test_gelijke_tellingen_staan_in_labelvolgorde():
    """De getoonde volgorde mag niet per run wisselen (#301).

    ``group_by`` levert de groepen in een willekeurige volgorde; zonder
    tweede sorteersleutel schuiven gelijke tellingen (en in een top-N de
    grensgevallen) van plaats per run.
    """
    df = pl.DataFrame(
        {"Domein": ["Zorg", "Entree", "Techniek"], "Inschrijvingen": [13, 9, 9]}
    )
    gesorteerd = sorteer_aantal(df, "Inschrijvingen", "Domein")
    assert gesorteerd["Domein"].to_list() == ["Zorg", "Entree", "Techniek"]


def test_top_n_blijft_hetzelfde_ongeacht_de_telvolgorde():
    telling = pl.DataFrame(
        {"Beroep": ["A", "B", "C", "D"], "Inschrijvingen": [3, 1, 1, 1]}
    ).sample(fraction=1.0, shuffle=True, seed=7)
    top = sorteer_aantal(telling, "Inschrijvingen", "Beroep").head(2)
    assert top["Beroep"].to_list() == ["A", "B"]
