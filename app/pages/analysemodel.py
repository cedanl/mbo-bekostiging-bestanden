"""Analysemodel — blader door het star schema en download.

Tweede product (#213): de leveringen samengevoegd, met inhoudelijke
ontwerpkeuzes zoals canonicalisatie en hoofdinschrijving. Persoonsgegevens zijn
in preview én download standaard verborgen.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from _tabel_docs import ANALYSEMODEL_INTRO, tabel_help
from _tabellen import (
    stop_met_terug_naar_home,
    toon_download_alles,
    toon_paginakop,
    toon_tabel_sectie,
    toon_terugknop,
)
from _utils import analysemodel_bijschrift, vind_star_dir

_SECTIE_ANALYSEMODEL = "Analysemodel (star schema)"
_BESTANDSNAAM_DOWNLOAD = "analysemodel"

toon_paginakop("Brondata → ster", "Analysemodel")
st.info(ANALYSEMODEL_INTRO)

star_dir = vind_star_dir(st.session_state)
if not star_dir:
    stop_met_terug_naar_home(
        "Nog geen analysemodel (star schema) gebouwd — bouw het op de Home-pagina "
        "uit de werkbare data."
    )

star_tabellen = {p.stem: p for p in sorted((star_dir / "datamodel").glob("*.parquet"))}
toon_tabel_sectie(
    _SECTIE_ANALYSEMODEL,
    star_tabellen,
    help_fn=tabel_help,
    bijschrift=analysemodel_bijschrift(star_dir),
)
toon_download_alles(star_tabellen, f"{_BESTANDSNAAM_DOWNLOAD}.zip")

toon_terugknop()
