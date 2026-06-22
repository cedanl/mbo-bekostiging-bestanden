"""Stap 1 van 3 — Kies een ruw bronbestand."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from _utils import raw_dir

from mbo_bekostiging_bestanden.pipeline import detect_bestandstype

st.markdown(
    '<span style="font-size:.75rem;font-weight:700;color:#7b8ab8;'
    'text-transform:uppercase;letter-spacing:.08em">Stap 1 van 3</span>',
    unsafe_allow_html=True,
)
st.title("Bestand kiezen")
st.write("Selecteer het ruwe bekostigingsbestand dat je wil verwerken.")

raw = raw_dir()
sources = sorted(p for p in raw.rglob("*") if p.is_file())

if not sources:
    st.error(
        f"Geen bronbestanden gevonden in `{raw}`. "
        "Controleer het pad in `app/config.toml`."
    )
    st.stop()

# key= zorgt dat de keuze behouden blijft bij elke rerun / knoppdruk
source = st.selectbox(
    "Bronbestand",
    sources,
    key="selected_source",
    format_func=lambda p: str(p.relative_to(raw)),
)

if source:
    bestandstype = detect_bestandstype(source)
    if bestandstype:
        st.success(f"Herkend als **{bestandstype.upper()}**-bestand.")
    else:
        st.warning(
            "Bestandstype niet herkend op basis van de naam. "
            "Controleer of de bestandsnaam begint met `RO_`, "
            "`GRONDSLAG_IP_MBO_` of `TBGI_`."
        )

st.write("")
col_terug, col_volgende = st.columns(2)
with col_terug:
    if st.button("← Home", use_container_width=True):
        st.switch_page("pages/home.py")
with col_volgende:
    can_proceed = source is not None and detect_bestandstype(source) is not None
    if st.button(
        "Verwerken →",
        type="primary",
        disabled=not can_proceed,
        use_container_width=True,
    ):
        # Wis vorige verwerkingsresultaten zodat verwerken.py opnieuw runt
        st.session_state.pop("verwerk_done", None)
        st.session_state.pop("verwerk_output_dir", None)
        st.switch_page("pages/verwerken.py")
