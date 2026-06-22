"""Stap 1–2 van stapelflow — Kies leveringen en stapel ze."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from _utils import output_dir, prepared_dir

from mbo_bekostiging_bestanden.export import export_frames
from mbo_bekostiging_bestanden.stack import stack_prepared

st.markdown(
    '<span style="font-size:.75rem;font-weight:700;color:#7b8ab8;'
    'text-transform:uppercase;letter-spacing:.08em">Leveringen stapelen</span>',
    unsafe_allow_html=True,
)
st.title("Leveringen stapelen")
st.write("Combineer genormaliseerde tabellen van meerdere leveringen.")

prepared = prepared_dir()
beschikbaar = sorted(
    d for d in prepared.rglob("*") if d.is_dir() and any(d.glob("*.parquet"))
)

if not beschikbaar:
    st.info(
        f"Geen prepared-mappen gevonden in `{prepared}`. "
        "Verwerk eerst één of meerdere bestanden via **Verwerk één bestand**."
    )
    if st.button("← Home"):
        st.switch_page("pages/home.py")
    st.stop()

# key= behoudt selectie bij rerun
geselecteerd = st.multiselect(
    "Kies mappen om te stapelen",
    beschikbaar,
    key="stapel_geselecteerd",
    format_func=lambda p: str(p.relative_to(prepared)),
)

done = st.session_state.get("stapel_done", False)

st.write("")
col_terug, col_stapel = st.columns(2)
with col_terug:
    if st.button("← Home", use_container_width=True):
        st.session_state.pop("stapel_done", None)
        st.switch_page("pages/home.py")
with col_stapel:
    if st.button(
        "Stapel",
        type="primary",
        disabled=len(geselecteerd) < 2,
        use_container_width=True,
    ):
        target = output_dir() / "gestapeld"
        target.mkdir(parents=True, exist_ok=True)
        with st.spinner("Bezig met stapelen…"):
            try:
                frames = stack_prepared(geselecteerd, relative_to=prepared)
                export_frames(frames, target)
                st.session_state["stapel_done"] = True
                st.session_state["stapel_output_dir"] = str(target)
                st.session_state["stapel_summary"] = {
                    "tabellen": len(frames),
                    "rijen": sum(df.height for df in frames.values()),
                    "tabel_namen": sorted(frames.keys()),
                }
                st.rerun()
            except Exception as exc:
                st.error(f"Fout tijdens stapelen: {exc}")

if done:
    summary = st.session_state.get("stapel_summary", {})
    st.success(
        f"Klaar — {summary.get('tabellen', '?')} tabellen, "
        f"{summary.get('rijen', '?')} rijen gecombineerd"
    )
    with st.expander("Tabellen"):
        for naam in summary.get("tabel_namen", []):
            st.write(f"• `{naam}`")

    if st.button("Bekijk resultaten →", type="primary", use_container_width=True):
        st.session_state["resultaten_dir"] = st.session_state["stapel_output_dir"]
        st.switch_page("pages/resultaten.py")
