"""Resultaten — blader door de output-tabellen en download."""

import sys
from pathlib import Path

import polars as pl
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))


@st.cache_resource(show_spinner=False)
def _lees_tabel(pad: str, mtime: float) -> pl.DataFrame:
    """Houdt een gelezen Parquet-tabel in het geheugen tussen reruns."""
    return pl.read_parquet(pad)


@st.cache_data(show_spinner=False)
def _tabel_csv(pad: str, mtime: float) -> str:
    """Genereert de CSV-tekst één keer per bestand i.p.v. bij elke rerun."""
    return _lees_tabel(pad, mtime).write_csv()

st.markdown(
    '<span style="font-size:.75rem;font-weight:700;color:#7b8ab8;'
    'text-transform:uppercase;letter-spacing:.08em">Resultaten</span>',
    unsafe_allow_html=True,
)
st.title("Resultaten")

resultaten_dir: str | None = st.session_state.get("resultaten_dir")
if not resultaten_dir:
    st.warning(
        "Geen resultatenmap ingesteld — verwerk eerst een bestand of stapel leveringen."
    )
    if st.button("← Home"):
        st.switch_page("pages/home.py")
    st.stop()

result_path = Path(resultaten_dir)
parquets = sorted(result_path.glob("*.parquet"))
datamodel_path = result_path / "datamodel"
dm_parquets = (
    sorted(datamodel_path.glob("*.parquet"))
    if datamodel_path.exists()
    else []
)

if not parquets and not dm_parquets:
    st.error(f"Geen Parquet-bestanden gevonden in `{result_path}`.")
    if st.button("← Home"):
        st.switch_page("pages/home.py")
    st.stop()

obt_namen = [p.stem for p in parquets]
dm_namen = [f"datamodel/{p.stem}" for p in dm_parquets]
tabel_namen = obt_namen + (["---"] + dm_namen if dm_namen else [])

gekozen = st.selectbox(
    "Kies tabel",
    tabel_namen,
    key="resultaten_tabel",
    format_func=lambda x: x if x != "---" else "── Star schema ──",
)

if gekozen and gekozen != "---":
    parquet_pad = result_path / f"{gekozen}.parquet"
    mtime = parquet_pad.stat().st_mtime
    df = _lees_tabel(str(parquet_pad), mtime)
    tabel_label = gekozen.split("/")[-1]

    col_info1, col_info2 = st.columns(2)
    col_info1.metric("Rijen", f"{df.height:,}")
    col_info2.metric("Kolommen", f"{df.width:,}")

    st.dataframe(df.head(1_000), use_container_width=True, hide_index=True)

    if df.height > 1_000:
        st.caption(f"Eerste 1 000 van {df.height:,} rijen getoond.")

    st.download_button(
        label=f"Download `{tabel_label}.csv`",
        data=_tabel_csv(str(parquet_pad), mtime),
        file_name=f"{tabel_label}.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.write("")
col_terug, _ = st.columns([1, 3])
with col_terug:
    if st.button("← Home", use_container_width=True):
        st.switch_page("pages/home.py")
