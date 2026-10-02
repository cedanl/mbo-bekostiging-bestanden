"""Gedeelde bouwstenen van de tabelpagina's (Werkbare data en Analysemodel).

Tabelkeuze, preview, kolomfilter, PII-verberging en CSV-download staan hier één
keer; de pagina's bepalen alleen welke tabellen ze tonen.
"""

from pathlib import Path
from typing import NoReturn

import polars as pl
import streamlit as st

from mbo_bekostiging_bestanden.contracts import (
    KOPPELSTATUS,
    KOPPELSTATUS_BINNEN,
    KOPPELSTATUSSEN,
)
from mbo_bekostiging_bestanden.pii import detect_pii_columns, zichtbare_kolommen

_MAX_WEERGAVE_RIJEN = 1_000  # rijen in de tabelweergave; de download is volledig


@st.cache_resource(show_spinner=False)
def _lees_tabel(pad: str, mtime: float) -> pl.DataFrame:
    """Houdt een gelezen Parquet-tabel in het geheugen tussen reruns."""
    return pl.read_parquet(pad)


@st.cache_data(show_spinner=False)
def _tabel_csv(pad: str, mtime: float, drop_pii: bool = False) -> str:
    """Genereert de CSV-tekst; optioneel met PII-kolommen verwijderd."""
    df = _lees_tabel(pad, mtime)
    return df.select(zichtbare_kolommen(df.columns, verberg_pii=drop_pii)).write_csv()


def _heeft_pii(df: pl.DataFrame) -> bool:
    """Detecteer of tabel PII-gevoelige kolommen bevat."""
    return bool(detect_pii_columns(df.columns))


def _filter_koppelstatus(df: pl.DataFrame, tabel: str) -> pl.DataFrame:
    """Filter een detail-feit op waarom een rij aan haar periode hangt (#121).

    Alleen de preview: de download blijft de volledige tabel.
    """
    if KOPPELSTATUS not in df.columns:
        return df
    gekozen = st.multiselect(
        "Koppelstatus",
        [s for s in KOPPELSTATUSSEN if s in set(df[KOPPELSTATUS])],
        placeholder="Alle statussen",
        help=(
            f"`{KOPPELSTATUS_BINNEN}`: de referentiedatum valt in de periode. "
            "De andere statussen hangen aan de eerste periode van hun "
            "inschrijving, of aan geen (`geen_inschrijving`)."
        ),
        key=f"koppelstatus_{tabel}",
    )
    return df.filter(pl.col(KOPPELSTATUS).is_in(gekozen)) if gekozen else df


def toon_tabel_sectie(
    titel: str, tabellen: dict[str, Path], help_fn=None, bijschrift: str = ""
):
    """Render tabel-selectie, preview en download; ``bijschrift`` noemt map en
    status van het product (#285)."""
    if not tabellen:
        return False

    st.subheader(titel)
    if bijschrift:
        st.caption(bijschrift)
    gekozen = st.selectbox(
        "Kies tabel", list(tabellen), key=f"tabel_{titel}", label_visibility="collapsed"
    )

    if gekozen:
        parquet_pad = tabellen[gekozen]

        if help_fn:
            help_fn(gekozen)

        mtime = parquet_pad.stat().st_mtime
        df = _lees_tabel(str(parquet_pad), mtime)

        col_info1, col_info2 = st.columns(2)
        col_info1.metric("Rijen", f"{df.height:,}")
        col_info2.metric("Kolommen", f"{df.width:,}")

        # Persoonsgegevens: standaard verborgen in preview én download.
        if _heeft_pii(df):
            st.warning(
                "⚠️ **Persoonsgegevens aanwezig**  \n"
                "Deze tabel bevat privacygevoelige kolommen (bijv. pseudoniem, "
                "geboortedatum, postcode). Ze zijn standaard verborgen; behandel "
                "de data verantwoord als je ze toont.",
                icon="⚠️",
            )
            drop_pii = st.checkbox(
                "Verberg persoonsgegevens (preview en download)",
                value=True,
                help="Aanbevolen. Uitvinken toont en downloadt de volledige tabel.",
                key=f"pii_{gekozen}",
            )
        else:
            drop_pii = False
        zichtbaar = zichtbare_kolommen(df.columns, verberg_pii=drop_pii)

        df = _filter_koppelstatus(df, gekozen)
        kolommen = st.multiselect(
            "Toon kolommen",
            zichtbaar,
            placeholder="Alle kolommen",
            key=f"kolommen_{gekozen}",
        )
        if df.height > _MAX_WEERGAVE_RIJEN:
            st.caption(
                f"Eerste {_MAX_WEERGAVE_RIJEN:,} van {df.height:,} rijen getoond; "
                "de download bevat alle rijen."
            )
        st.dataframe(
            df.select(kolommen or zichtbaar).head(_MAX_WEERGAVE_RIJEN),
            width="stretch",
            hide_index=True,
        )

        st.download_button(
            label=f"Download `{parquet_pad.stem}.csv`",
            data=_tabel_csv(str(parquet_pad), mtime, drop_pii=drop_pii),
            file_name=f"{parquet_pad.stem}.csv",
            mime="text/csv",
            width="stretch",
        )
        return True
    return False


def toon_paginakop(label: str, titel: str) -> None:
    """Klein label boven de paginatitel, in de huisstijl van de app."""
    st.markdown(
        '<span style="font-size:.75rem;font-weight:700;color:#4d5d8a;'
        f'text-transform:uppercase;letter-spacing:.08em">{label}</span>',
        unsafe_allow_html=True,
    )
    st.title(titel)


def stop_met_terug_naar_home(melding: str) -> NoReturn:
    """Toon ``melding`` met een knop naar Home en stop de pagina."""
    st.warning(melding)
    if st.button("← Home"):
        st.switch_page("pages/home.py")
    st.stop()


def toon_terugknop() -> None:
    st.write("")
    col_terug, _ = st.columns([1, 3])
    with col_terug:
        if st.button("← Home", width="stretch"):
            st.switch_page("pages/home.py")
