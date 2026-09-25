"""Resultaten — blader door de verwerkte tabellen en download.

Toont bij voorkeur het star-schema-datamodel. Aanvullend: TBGI prepared data
(detail_bekostiging, detail_bekostiging_diploma) voor BPV/signaalinformatie.
Kon het star schema niet gebouwd worden, dan valt de pagina terug op de losse
prepared tabellen per bestand.
"""

import sys
from pathlib import Path

import polars as pl
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from _tabel_docs import PAGINA_INTRO, tabel_help
from _utils import vind_star_dir

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from mbo_bekostiging_bestanden.pii import detect_pii_columns

_MAX_WEERGAVE_RIJEN = 1_000  # rijen in de tabelweergave; de download is volledig


@st.cache_resource(show_spinner=False)
def _lees_tabel(pad: str, mtime: float) -> pl.DataFrame:
    """Houdt een gelezen Parquet-tabel in het geheugen tussen reruns."""
    return pl.read_parquet(pad)


@st.cache_data(show_spinner=False)
def _tabel_csv(pad: str, mtime: float, drop_pii: bool = False) -> str:
    """Genereert de CSV-tekst; optioneel met PII-kolommen verwijderd."""
    df = _lees_tabel(pad, mtime)
    if drop_pii:
        pii_kolommen = detect_pii_columns(df.columns)
        if pii_kolommen:
            df = df.drop(pii_kolommen)
    return df.write_csv()


def _heeft_pii(df: pl.DataFrame) -> bool:
    """Detecteer of tabel PII-gevoelige kolommen bevat."""
    return bool(detect_pii_columns(df.columns))


def _toon_tabel_sectie(titel: str, tabellen: dict[str, Path], help_fn=None):
    """Render tabel-selectie, preview en download."""
    if not tabellen:
        return False

    st.subheader(titel)
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

        kolommen = st.multiselect(
            "Toon kolommen",
            df.columns,
            placeholder="Alle kolommen",
            key=f"kolommen_{gekozen}",
        )
        if df.height > _MAX_WEERGAVE_RIJEN:
            st.caption(
                f"Eerste {_MAX_WEERGAVE_RIJEN:,} van {df.height:,} rijen getoond; "
                "de download bevat alle rijen."
            )
        st.dataframe(
            df.select(kolommen or df.columns).head(_MAX_WEERGAVE_RIJEN),
            width="stretch",
            hide_index=True,
        )

        # Waarschuwing en opties voor PII-gevoelige tabellen
        if _heeft_pii(df):
            st.warning(
                "⚠️ **Persoonsgegevens aanwezig**  \n"
                "Deze tabel bevat privacygevoelige kolommen (bijv. geboortedatum, "
                "postcode). Zorg ervoor dat je deze data verantwoord behandelt.",
                icon="⚠️",
            )
            drop_pii = st.checkbox(
                "Verwijder persoonsgegevens voor download",
                value=True,
                help="Privacygegevens worden standaard verwijderd (aanbevolen). "
                "Uncheck om volledige tabel te downloaden (met PII).",
                key=f"pii_{gekozen}",
            )
        else:
            drop_pii = False

        st.download_button(
            label=f"Download `{parquet_pad.stem}.csv`",
            data=_tabel_csv(str(parquet_pad), mtime, drop_pii=drop_pii),
            file_name=f"{parquet_pad.stem}.csv",
            mime="text/csv",
            width="stretch",
        )
        return True
    return False


st.markdown(
    '<span style="font-size:.75rem;font-weight:700;color:#4d5d8a;'
    'text-transform:uppercase;letter-spacing:.08em">Resultaten</span>',
    unsafe_allow_html=True,
)
st.title("Resultaten")

st.info(PAGINA_INTRO)

# Verzamel star- en prepared-tabellen
star_dir = vind_star_dir(st.session_state)
star_tabellen = (
    {p.stem: p for p in sorted((star_dir / "datamodel").glob("*.parquet"))}
    if star_dir
    else {}
)

# Verzamel prepared-tabellen, gescheiden naar type
tbgi_prepared = {}
other_prepared = {}
for prep_dir in st.session_state.get("prepared_dirs", []):
    prep_pad = Path(prep_dir)
    for parquet in sorted(prep_pad.glob("*.parquet")):
        name = parquet.stem
        if "detail_bekostiging" in name:
            tbgi_prepared[name] = parquet
        else:
            other_prepared[f"{prep_pad.name} / {name}"] = parquet

if not star_tabellen and not tbgi_prepared and not other_prepared:
    st.warning(
        "Geen resultaten — verwerk eerst een of meer bestanden op de Home-pagina."
    )
    if st.button("← Home"):
        st.switch_page("pages/home.py")
    st.stop()

if not star_tabellen:
    st.warning(
        "Nog geen star schema gebouwd. Hieronder de losse verwerkte tabellen per "
        "bestand (recordtypes), zodat je de data alsnog kunt bekijken en downloaden."
    )

# Toon secties
if star_tabellen:
    _toon_tabel_sectie("📊 Star Schema", star_tabellen, help_fn=tabel_help)

if tbgi_prepared:
    st.divider()
    _toon_tabel_sectie("🔁 TBGI Prepared Data (BPV, Signalen)", tbgi_prepared)

if other_prepared:
    st.divider()
    _toon_tabel_sectie("📑 Overige Prepared Data", other_prepared)

st.write("")
col_terug, _ = st.columns([1, 3])
with col_terug:
    if st.button("← Home", width="stretch"):
        st.switch_page("pages/home.py")
