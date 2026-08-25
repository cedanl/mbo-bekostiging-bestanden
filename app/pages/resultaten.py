"""Resultaten — blader door de verwerkte tabellen en download.

Toont bij voorkeur het star-schema-datamodel. Kon dat niet gebouwd worden
(bijv. een bestand zonder inschrijvingen), dan valt de pagina terug op de
losse prepared tabellen per bestand, zodat de data alsnog te bekijken is.
"""

import sys
from pathlib import Path

import polars as pl
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from _tabel_docs import PAGINA_INTRO, tabel_help


@st.cache_resource(show_spinner=False)
def _lees_tabel(pad: str, mtime: float) -> pl.DataFrame:
    """Houdt een gelezen Parquet-tabel in het geheugen tussen reruns."""
    return pl.read_parquet(pad)


@st.cache_data(show_spinner=False)
def _tabel_csv(pad: str, mtime: float) -> str:
    """Genereert de CSV-tekst één keer per bestand i.p.v. bij elke rerun."""
    return _lees_tabel(pad, mtime).write_csv()


def _verzamel_tabellen() -> tuple[dict[str, Path], str]:
    """Bepaal de te tonen tabellen en de bron ('star' of 'prepared').

    Voorkeur: het star-datamodel. Ontbreekt dat, dan de losse prepared
    tabellen per bestand als fallback.
    """
    tabellen: dict[str, Path] = {}

    resultaten_dir = st.session_state.get("resultaten_dir")
    if resultaten_dir:
        datamodel = Path(resultaten_dir) / "datamodel"
        if datamodel.exists():
            for parquet in sorted(datamodel.glob("*.parquet")):
                tabellen[parquet.stem] = parquet
    if tabellen:
        return tabellen, "star"

    for prep in st.session_state.get("prepared_dirs", []):
        prep_pad = Path(prep)
        for parquet in sorted(prep_pad.glob("*.parquet")):
            tabellen[f"{prep_pad.name} / {parquet.stem}"] = parquet
    return tabellen, "prepared"


st.markdown(
    '<span style="font-size:.75rem;font-weight:700;color:#7b8ab8;'
    'text-transform:uppercase;letter-spacing:.08em">Resultaten</span>',
    unsafe_allow_html=True,
)
st.title("Resultaten")

st.info(PAGINA_INTRO)

tabellen, bron = _verzamel_tabellen()

if not tabellen:
    st.warning(
        "Geen resultaten — verwerk eerst een of meer bestanden op de Home-pagina."
    )
    if st.button("← Home"):
        st.switch_page("pages/home.py")
    st.stop()

if bron == "prepared":
    st.warning(
        "Nog geen star schema gebouwd. Hieronder de losse verwerkte tabellen per "
        "bestand (recordtypes), zodat je de data alsnog kunt bekijken en downloaden."
    )

gekozen = st.selectbox("Kies tabel", list(tabellen), key="resultaten_tabel")

if gekozen:
    parquet_pad = tabellen[gekozen]

    if bron == "star":
        tabel_help(gekozen)

    mtime = parquet_pad.stat().st_mtime
    df = _lees_tabel(str(parquet_pad), mtime)

    col_info1, col_info2 = st.columns(2)
    col_info1.metric("Rijen", f"{df.height:,}")
    col_info2.metric("Kolommen", f"{df.width:,}")

    st.dataframe(df.head(1_000), use_container_width=True, hide_index=True)

    if df.height > 1_000:
        st.caption(f"Eerste 1 000 van {df.height:,} rijen getoond.")

    st.download_button(
        label=f"Download `{parquet_pad.stem}.csv`",
        data=_tabel_csv(str(parquet_pad), mtime),
        file_name=f"{parquet_pad.stem}.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.write("")
col_terug, _ = st.columns([1, 3])
with col_terug:
    if st.button("← Home", use_container_width=True):
        st.switch_page("pages/home.py")
