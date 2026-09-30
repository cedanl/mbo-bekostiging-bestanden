"""Dashboard — visueel overzicht van de verwerkte bekostigingsdata.

Alleen orkestratie (#301): laden en jaarselectie in ``_dashboard.data``,
rendering per tab in ``_dashboard.tab_*``.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from _dashboard import (
    data,
    kerncijfers,
    kwaliteit,
    sidebar,
    tab_bekostiging,
    tab_examens,
    tab_opleidingen,
    tab_opleidingsstructuur,
    tab_rendementen,
    tab_studenten,
)
from _utils import star_dir, vind_star_dir

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from mbo_bekostiging_bestanden.filters import beschikbare_schooljaren

st.markdown(
    '<span style="font-size:.75rem;font-weight:700;color:#4d5d8a;'
    'text-transform:uppercase;letter-spacing:.08em">Dashboard</span>',
    unsafe_allow_html=True,
)
st.title("Dashboard")

data_dir = vind_star_dir(st.session_state)
if data_dir is None:
    st.warning(
        "Geen data gevonden — verwerk eerst bestanden via Home of zet "
        f"demo-data in `{star_dir() / 'datamodel'}`."
    )
    if st.button("← Home"):
        st.switch_page("pages/home.py")
    st.stop()

ster = data.lees_star_schema(data_dir, data.parquet_max_mtime(data_dir))
rapport = data.lees_kwaliteitsrapport(data_dir)
kwaliteit.toon(rapport, ster.meta_leveringen)
selectie = data.selecteer(
    ster,
    sidebar.schooljaar_selectie(beschikbare_schooljaren(ster.jaren, ster.bekostiging)),
)

kerncijfers.toon(selectie)
st.divider()

_TABS = {
    "Rendementen": lambda: tab_rendementen.toon(selectie, rapport),
    "Bekostiging": lambda: tab_bekostiging.toon(selectie),
    "Opleidingen": lambda: tab_opleidingen.toon(selectie),
    "Studenten": lambda: tab_studenten.toon(selectie),
    "Examens": lambda: tab_examens.toon(selectie),
    "Opleidingsstructuur": lambda: tab_opleidingsstructuur.toon(selectie),
}
for tab, toon in zip(st.tabs(list(_TABS)), _TABS.values(), strict=True):
    with tab:
        toon()

st.caption(
    "© CEDA · Npuls — [GitHub](https://github.com/cedanl/mbo-bekostiging-bestanden)"
)
