"""Home — auto-ontdek en verwerk alle bestanden in één stap."""

import sys
from collections import defaultdict
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from _utils import output_dir, prepared_dir, raw_dir

from mbo_bekostiging_bestanden.export import export_frames
from mbo_bekostiging_bestanden.obt import build_obt
from mbo_bekostiging_bestanden.pipeline import detect_bestandstype, run_auto_pipeline
from mbo_bekostiging_bestanden.stack import stack_prepared


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------


def _scan_raw(raw: Path) -> dict[str, list[Path]]:
    """Alle herkenbare bestanden in raw, gegroepeerd op eerste submap."""
    groepen: dict[str, list[Path]] = defaultdict(list)
    for p in sorted(raw.rglob("*")):
        if p.is_file() and detect_bestandstype(p) is not None:
            rel = p.relative_to(raw)
            groep = rel.parts[0] if len(rel.parts) > 1 else "overig"
            groepen[groep].append(p)
    return dict(groepen)


def _prepared_subdir(raw_file: Path, raw: Path, prepared: Path) -> Path:
    """Consistente prepared-mapnaam op basis van de bestandsstam."""
    rel = raw_file.relative_to(raw)
    groep = rel.parts[0] if len(rel.parts) > 1 else "overig"
    return prepared / groep / raw_file.stem


# ---------------------------------------------------------------------------
# Pagina
# ---------------------------------------------------------------------------

st.markdown(
    """<style>
.hero { background: linear-gradient(135deg,#1a56db 0%,#0e3fa8 100%);
        padding: 2rem 1.5rem; border-radius: 10px; color: white;
        margin-bottom: 1.5rem; text-align: center; }
.hero h1 { margin: 0 0 .4rem 0; font-size: 2rem; font-weight: 700; }
.hero p  { margin: 0; opacity: .88; font-size: 1rem; }
</style>
<div class="hero">
  <h1>MBO-bekostigingsbestanden</h1>
  <p>Zet ruwe DUO-bekostigingsbestanden automatisch om naar schone OBT-data.</p>
</div>""",
    unsafe_allow_html=True,
)

# ── Ontdek bestanden ─────────────────────────────────────────────────────────
raw = raw_dir()
groepen = _scan_raw(raw)

if not groepen:
    st.info(
        f"Geen herkenbare bestanden gevonden in `{raw}`.  \n"
        "Zet RO-, GRONDSLAG- of TBGI-bestanden in de invoermap."
    )
    st.stop()

totaal_bestanden = sum(len(v) for v in groepen.values())
st.write(
    f"**{totaal_bestanden} bestand(en) gevonden** in `{raw}` "
    f"— {len(groepen)} map(pen):"
)

for periode in sorted(groepen):
    with st.expander(f"📁 {periode}  ({len(groepen[periode])} bestand(en))"):
        for f in groepen[periode]:
            bestandstype = detect_bestandstype(f) or "?"
            st.write(f"• `{f.name}` — *{bestandstype}*")

st.write("")

# ── Verwerk alles ────────────────────────────────────────────────────────────
done = st.session_state.get("alles_verwerkt", False)

if not done:
    if st.button("Verwerk alles", type="primary", use_container_width=True):
        prepared = prepared_dir()
        output = output_dir()

        # +1 voor de gecombineerde OBT-stap aan het eind
        totaal_stappen = totaal_bestanden + 1
        voortgang = st.progress(0, text="Start…")
        status = st.empty()
        stap = 0
        fouten: list[str] = []
        alle_prep_dirs: list[Path] = []

        # Stap 1: verwerk ieder ruw bestand naar prepared
        for periode in sorted(groepen):
            for raw_file in groepen[periode]:
                target = _prepared_subdir(raw_file, raw, prepared)
                target.mkdir(parents=True, exist_ok=True)
                status.info(f"Verwerk `{raw_file.name}`…")
                try:
                    run_auto_pipeline(raw_file, target)
                    alle_prep_dirs.append(target)
                except Exception as exc:
                    fouten.append(f"{raw_file.name}: {exc}")
                stap += 1
                voortgang.progress(stap / totaal_stappen, text=f"{stap}/{totaal_stappen}")

        # Stap 2: alle prepared dirs samen stapelen en één gecombineerde OBT bouwen
        status.info("Stapel alle leveringen en bouw gecombineerde OBT…")
        prep_dirs_met_data = [
            d for d in alle_prep_dirs
            if d.exists() and any(d.glob("*.parquet"))
        ]
        obt_target = output / "obt"
        obt_target.mkdir(parents=True, exist_ok=True)

        try:
            stacked = stack_prepared(prep_dirs_met_data, relative_to=prepared)
            obt = build_obt(stacked)
            export_frames(obt, obt_target)
            obt_summary = {
                "isp_rijen": obt["obt_inschrijvingen"].height,
                "bekostiging_rijen": obt["detail_bekostiging"].height,
                "bpv_rijen": obt["detail_bpv"].height,
                "kzd_amo_rijen": obt["detail_kzd_amo"].height,
                "leveringen": sorted(
                    obt["obt_inschrijvingen"]["levering"].unique().to_list()
                ),
            }
        except Exception as exc:
            fouten.append(f"OBT: {exc}")
            obt_summary = {}

        stap += 1
        voortgang.progress(1.0, text="Klaar")
        status.empty()
        st.session_state["alles_verwerkt"] = True
        st.session_state["obt_pad"] = str(obt_target)
        st.session_state["obt_summary"] = obt_summary
        if fouten:
            st.session_state["fouten"] = fouten
        st.rerun()

if done:
    obt_pad = st.session_state.get("obt_pad", "")
    obt_summary: dict = st.session_state.get("obt_summary", {})
    fouten: list[str] = st.session_state.get("fouten", [])

    if fouten:
        with st.expander(f"⚠️ {len(fouten)} fout(en)"):
            for f in fouten:
                st.write(f"• {f}")

    if obt_summary:
        st.success("Verwerkt — gecombineerde OBT klaar")
        col1, col2, col3 = st.columns(3)
        col1.metric("Inschrijvingen (ISP)", obt_summary.get("isp_rijen", "—"))
        col2.metric("Bekostiging detail", obt_summary.get("bekostiging_rijen", "—"))
        col3.metric("BPV detail", obt_summary.get("bpv_rijen", "—"))

        with st.expander("Leveringen opgenomen"):
            for lev in obt_summary.get("leveringen", []):
                st.write(f"• `{lev}`")

        st.write("")
        col_bekijk, col_opnieuw = st.columns(2)
        with col_bekijk:
            if st.button("Bekijk resultaten →", type="primary", use_container_width=True):
                st.session_state["resultaten_dir"] = obt_pad
                st.switch_page("pages/resultaten.py")
        with col_opnieuw:
            if st.button("Opnieuw verwerken", use_container_width=True):
                for sleutel in ("alles_verwerkt", "obt_pad", "obt_summary", "fouten"):
                    st.session_state.pop(sleutel, None)
                st.rerun()

st.divider()
st.caption(
    "© CEDA · Npuls — [GitHub](https://github.com/cedanl/mbo-bekostiging-bestanden)"
)
