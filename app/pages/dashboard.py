"""Dashboard — visueel overzicht van de gecombineerde OBT-data."""

import sys
from pathlib import Path

import polars as pl
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from _utils import output_dir


def _resolve_dir() -> Path | None:
    for key in ("resultaten_dir", "obt_pad"):
        val = st.session_state.get(key)
        if val:
            p = Path(val)
            if (p / "obt_inschrijvingen.parquet").exists():
                return p
    fallback = output_dir() / "obt"
    if (fallback / "obt_inschrijvingen.parquet").exists():
        return fallback
    return None


st.markdown(
    '<span style="font-size:.75rem;font-weight:700;color:#7b8ab8;'
    'text-transform:uppercase;letter-spacing:.08em">Dashboard</span>',
    unsafe_allow_html=True,
)
st.title("Dashboard")

data_dir = _resolve_dir()

if data_dir is None:
    st.warning(
        "Geen OBT-data gevonden — verwerk eerst bestanden via Home of zet "
        "demo-data in `data/03-output/demo/obt/`."
    )
    if st.button("← Home"):
        st.switch_page("pages/home.py")
    st.stop()

df = pl.read_parquet(data_dir / "obt_inschrijvingen.parquet")

# ---------------------------------------------------------------------------
# 1. Header metrics
# ---------------------------------------------------------------------------

totaal = df.height
bekostigd_n = (
    df.filter(pl.col("IndicatieBekostigbaar") == "J").height
    if "IndicatieBekostigbaar" in df.columns
    else 0
)
diplomas_n = (
    df.filter(pl.col("DIP_DatumResultaat").is_not_null()).height
    if "DIP_DatumResultaat" in df.columns
    else 0
)
n_leveringen = df["levering"].n_unique() if "levering" in df.columns else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Inschrijvingen", f"{totaal:,}")
col2.metric("Bekostigd (indicatie)", f"{bekostigd_n:,}")
col3.metric("Diploma's behaald", f"{diplomas_n:,}")
col4.metric("Leveringen", n_leveringen)

st.divider()

# ---------------------------------------------------------------------------
# 2. Inschrijvingen per levering
# ---------------------------------------------------------------------------

st.subheader("Inschrijvingen per levering")
if "levering" in df.columns:
    per_levering = (
        df.group_by("levering")
        .agg(pl.len().alias("Inschrijvingen"))
        .sort("levering")
    )
    st.bar_chart(per_levering, x="levering", y="Inschrijvingen")

st.divider()

# ---------------------------------------------------------------------------
# 3. Verdeling naar Niveau
# ---------------------------------------------------------------------------

st.subheader("Verdeling naar Niveau")
if "Niveau" in df.columns:
    per_niveau = (
        df.group_by("Niveau")
        .agg(pl.len().alias("Inschrijvingen"))
        .sort("Niveau")
    )
    st.bar_chart(per_niveau, x="Niveau", y="Inschrijvingen")
else:
    st.info("Kolom `Niveau` niet beschikbaar in de data.")

st.divider()

# ---------------------------------------------------------------------------
# 4. Leertraject per levering
# ---------------------------------------------------------------------------

st.subheader("Leertraject per levering")
if "Leertraject" in df.columns and "levering" in df.columns:
    per_lt = (
        df.group_by(["levering", "Leertraject"])
        .agg(pl.len().alias("Inschrijvingen"))
        .sort(["levering", "Leertraject"])
    )
    st.bar_chart(per_lt, x="levering", y="Inschrijvingen", color="Leertraject")
else:
    st.info("Kolommen `levering` of `Leertraject` niet beschikbaar in de data.")

st.divider()

# ---------------------------------------------------------------------------
# 5. Bekostigingsstatus
# ---------------------------------------------------------------------------

st.subheader("Bekostigingsstatus")
if "_bekostigd_eerste_1okt" in df.columns:
    n_1okt = df.filter(pl.col("_bekostigd_eerste_1okt")).height
    pct_1okt = n_1okt / totaal * 100 if totaal > 0 else 0.0
    st.metric("Bekostigd op 1 oktober", f"{n_1okt:,}", f"{pct_1okt:.1f}%")
elif "IndicatieBekostigbaar" in df.columns:
    verdeling = (
        df.group_by("IndicatieBekostigbaar")
        .agg(pl.len().alias("Inschrijvingen"))
        .sort("IndicatieBekostigbaar")
    )
    st.bar_chart(verdeling, x="IndicatieBekostigbaar", y="Inschrijvingen")

st.divider()

# ---------------------------------------------------------------------------
# 6. Jaarresultaat (JR) indicatief
# ---------------------------------------------------------------------------

if "_gediplomeerd_in_jaar" in df.columns and "_actief_1_oktober" in df.columns:
    st.subheader("Jaarresultaat (JR) — indicatief")
    jr = (
        df.group_by("levering")
        .agg(
            pl.col("_actief_1_oktober").sum().alias("Actief 1-okt"),
            pl.col("_gediplomeerd_in_jaar").sum().alias("Gediplomeerd"),
        )
        .sort("levering")
        .with_columns(
            (pl.col("Gediplomeerd") / pl.col("Actief 1-okt") * 100)
            .round(1)
            .alias("JR (%)")
        )
    )
    st.dataframe(jr, use_container_width=True, hide_index=True)
    st.divider()

st.caption(
    "© CEDA · Npuls — [GitHub](https://github.com/cedanl/mbo-bekostiging-bestanden)"
)
