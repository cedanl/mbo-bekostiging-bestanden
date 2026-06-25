"""Resultaten — blader door de output-tabellen en download."""

import sys
from pathlib import Path

import polars as pl
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

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
if not parquets:
    st.error(f"Geen Parquet-bestanden gevonden in `{result_path}`.")
    if st.button("← Home"):
        st.switch_page("pages/home.py")
    st.stop()

tabel_namen = [p.stem for p in parquets]

# key= houdt selectie vast bij rerun
gekozen = st.selectbox(
    "Kies tabel",
    tabel_namen,
    key="resultaten_tabel",
)

if gekozen:
    parquet_pad = result_path / f"{gekozen}.parquet"
    df = pl.read_parquet(parquet_pad)

    col_info1, col_info2 = st.columns(2)
    col_info1.metric("Rijen", f"{df.height:,}")
    col_info2.metric("Kolommen", f"{df.width:,}")

    st.dataframe(df.head(1_000), use_container_width=True, hide_index=True)

    if df.height > 1_000:
        st.caption(f"Eerste 1 000 van {df.height:,} rijen getoond.")

    csv = df.write_csv()
    st.download_button(
        label=f"Download `{gekozen}.csv`",
        data=csv,
        file_name=f"{gekozen}.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.write("")
col_terug, _ = st.columns([1, 3])
with col_terug:
    if st.button("← Home", use_container_width=True):
        st.switch_page("pages/home.py")
