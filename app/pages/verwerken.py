"""Stap 2 van 3 — Verwerk het geselecteerde bestand."""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from _utils import prepared_dir, raw_dir

from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline

st.markdown(
    '<span style="font-size:.75rem;font-weight:700;color:#7b8ab8;'
    'text-transform:uppercase;letter-spacing:.08em">Stap 2 van 3</span>',
    unsafe_allow_html=True,
)
st.title("Verwerken")

source: Path | None = st.session_state.get("verwerk_source")
if source is None:
    st.warning("Geen bestand geselecteerd — ga terug naar stap 1.")
    if st.button("← Bestand kiezen"):
        st.switch_page("pages/kiezen.py")
    st.stop()

st.write(f"**Bestand:** `{source.name}`")

done = st.session_state.get("verwerk_done", False)

if not done:
    if st.button("Start verwerking", type="primary", use_container_width=True):
        raw = raw_dir()
        sub = source.parent.relative_to(raw)
        target = prepared_dir() / sub / source.stem[:4]
        target.mkdir(parents=True, exist_ok=True)

        with st.spinner("Bezig met verwerken…"):
            try:
                frames = run_auto_pipeline(source, target)
                st.session_state["verwerk_done"] = True
                st.session_state["verwerk_output_dir"] = str(target)
                st.session_state["verwerk_summary"] = {
                    "tabellen": len(frames),
                    "rijen": sum(df.height for df in frames.values()),
                    "tabel_namen": sorted(frames.keys()),
                }
                st.rerun()
            except Exception as exc:
                st.error(f"Fout tijdens verwerking: {exc}")

if done:
    summary = st.session_state.get("verwerk_summary", {})
    st.success(
        f"Klaar — {summary.get('tabellen', '?')} tabellen, "
        f"{summary.get('rijen', '?')} rijen"
    )
    with st.expander("Tabellen"):
        for naam in summary.get("tabel_namen", []):
            st.write(f"• `{naam}`")

    st.write("")
    col_terug, col_volgende = st.columns(2)
    with col_terug:
        if st.button("← Ander bestand", use_container_width=True):
            st.session_state.pop("verwerk_done", None)
            st.session_state.pop("verwerk_output_dir", None)
            st.switch_page("pages/kiezen.py")
    with col_volgende:
        if st.button("Bekijk resultaten →", type="primary", use_container_width=True):
            st.session_state["resultaten_dir"] = st.session_state["verwerk_output_dir"]
            st.switch_page("pages/resultaten.py")
