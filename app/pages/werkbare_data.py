"""Werkbare data — de brondata per levering: ruw omgezet naar een werkbaar formaat.

Eerste product (#213): elk DUO-bestand per recordtype, getrouw aan de levering.
Persoonsgegevens zijn in preview én download standaard verborgen.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from _tabel_docs import BRONDATA_INTRO
from _tabellen import (
    stop_met_terug_naar_home,
    toon_download_alles,
    toon_paginakop,
    toon_tabel_sectie,
    toon_terugknop,
)
from _utils import brondata_bijschrift, groepeer_prepared, vind_prepared_dirs

_SECTIE_BRONDATA = "Brondata per levering"
_BESTANDSNAAM_DOWNLOAD = "werkbare_data"

toon_paginakop("Ruw → werkbaar", "Werkbare data")
st.info(BRONDATA_INTRO)

prepared_dirs = vind_prepared_dirs(st.session_state)
st.session_state["prepared_dirs"] = [str(d) for d in prepared_dirs]
tbgi_prepared, other_prepared = groepeer_prepared(prepared_dirs)

if not tbgi_prepared and not other_prepared:
    stop_met_terug_naar_home(
        "Nog geen werkbare data — verwerk eerst een of meer bestanden op de "
        "Home-pagina."
    )

# Het bijschrift geldt voor de brondata als geheel: één keer, bij de eerste sectie.
bijschrift = brondata_bijschrift(prepared_dirs)
for groep, tabellen in (("RO en GRONDSLAG", other_prepared), ("TBG-i", tbgi_prepared)):
    if tabellen:
        toon_tabel_sectie(
            f"{_SECTIE_BRONDATA} — {groep}", tabellen, bijschrift=bijschrift
        )
        bijschrift = ""

toon_download_alles(
    {**other_prepared, **tbgi_prepared}, f"{_BESTANDSNAAM_DOWNLOAD}.zip"
)
toon_terugknop()
