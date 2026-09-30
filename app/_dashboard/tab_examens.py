"""Tab Examens: GEO-cijfers en -slaging, IE vs CE, AMO-onderdelen."""

import tomllib
from pathlib import Path

import polars as pl
import streamlit as st
from _chart_docs import chart_help

from _dashboard.data import Selectie
from _dashboard.grafieken import hbar, sorteer_aantal

_GEO_META = (
    Path(__file__).parents[2] / "src/mbo_bekostiging_bestanden/metadata/geo_codes.toml"
)
_GEO_SLAAGGRENS = 5.5  # minimaal eindcijfer om als geslaagd te tellen


def _geo_labels() -> dict[str, str]:
    if not _GEO_META.exists():
        return {}
    with _GEO_META.open("rb") as f:
        codes = tomllib.load(f).get("codes", {})
    return {code: meta.get("label", code) for code, meta in codes.items()}


def _geo_statistieken(geo: pl.DataFrame, labels: dict[str, str]) -> list[dict]:
    """Per onderdeel gemiddeld eindcijfer, slagingspercentage en N.

    Eenmalig berekend: de eindcijfer- en de slagingsgrafiek delen de uitkomst.
    """
    stats = []
    for (code,), groep in geo.group_by("CodeGeneriekExamenonderdeel"):
        cijfers = groep["Eindcijfer"].drop_nulls().cast(pl.Float64)
        if cijfers.is_empty():
            continue
        gemiddeld = cijfers.mean()
        stats.append(
            {
                "Onderdeel": labels.get(str(code), f"GEO {code}"),
                "Gemiddeld eindcijfer": round(
                    gemiddeld if isinstance(gemiddeld, float) else 0.0, 1
                ),
                "Geslaagd (%)": round(
                    int((cijfers >= _GEO_SLAAGGRENS).sum()) / len(cijfers) * 100, 1
                ),
                "N": len(cijfers),
            }
        )
    return stats


def _toon_ie_ce(geo: pl.DataFrame, labels: dict[str, str]) -> None:
    if geo.is_empty() or not {
        "CodeGeneriekExamenonderdeel",
        "CijferIE",
        "CijferCE",
    } <= set(geo.columns):
        st.info("fact_geo niet beschikbaar of IE/CE-kolommen ontbreken.")
        return
    code = pl.col("CodeGeneriekExamenonderdeel").cast(pl.Utf8)
    codes = (
        geo.filter(pl.col("CijferIE").is_not_null() | pl.col("CijferCE").is_not_null())
        .select(code)
        .to_series()
        .unique()
        .sort()
        .to_list()
    )
    getoond = False
    for geo_code in codes:
        groep = geo.filter(code == geo_code)
        ie = groep["CijferIE"].drop_nulls()
        ce = groep["CijferCE"].drop_nulls()
        if ie.is_empty() and ce.is_empty():
            continue
        getoond = True
        st.markdown(f"**{labels.get(geo_code, f'GEO {geo_code}')} (code {geo_code})**")
        gc1, gc2 = st.columns(2)
        if not ie.is_empty():
            gc1.metric(
                "Gem. IE", f"{ie.cast(pl.Float64).mean():.1f}", help="Instituutsexamen"
            )
        if not ce.is_empty():
            gc2.metric(
                "Gem. CE", f"{ce.cast(pl.Float64).mean():.1f}", help="Centraal examen"
            )
    if not getoond:
        st.info("Geen IE/CE-cijfers beschikbaar in de data.")


def _toon_amo(df: pl.DataFrame) -> None:
    if "AMO_Aantal" not in df.columns:
        st.info("Kolom `AMO_Aantal` niet beschikbaar.")
        return
    amo = df["AMO_Aantal"].drop_nulls()
    if amo.is_empty():
        st.info("Kolom `AMO_Aantal` is volledig leeg.")
        return
    ac1, ac2 = st.columns(2)
    ac1.metric("Totaal AMO-onderdelen", f"{int(amo.sum()):,}")
    ac2.metric("Gemiddeld per periode met AMO", f"{amo.mean():.1f}")


def toon(selectie: Selectie) -> None:
    geo = selectie.geo
    labels = _geo_labels()
    heeft_data = not geo.is_empty() and {
        "CodeGeneriekExamenonderdeel",
        "Eindcijfer",
    } <= set(geo.columns)
    stats = _geo_statistieken(geo, labels) if heeft_data else []

    st.subheader("GEO-examencijfers")
    chart_help("geo_eindcijfers")
    if stats:
        tabel = sorteer_aantal(pl.DataFrame(stats), "N", "Onderdeel")
        st.dataframe(
            tabel.select(["Onderdeel", "Gemiddeld eindcijfer", "N"]),
            width="stretch",
            hide_index=True,
        )
    elif heeft_data:
        st.info("Geen GEO-eindcijfers gevuld in de data.")
    else:
        st.info("fact_geo niet beschikbaar of kolommen ontbreken.")

    st.subheader("GEO slagingspercentage (eindcijfer ≥ 5,5)")
    chart_help("geo_slagingspercentage")
    if stats:
        hbar(pl.DataFrame(stats), "Onderdeel", "Geslaagd (%)")
    elif heeft_data:
        st.info("Geen GEO-eindcijfers beschikbaar voor slagingspercentage.")
    else:
        st.info("fact_geo niet beschikbaar of kolom `Eindcijfer` ontbreekt.")

    st.subheader("GEO IE vs CE — vergelijking")
    chart_help("geo_ie_ce")
    _toon_ie_ce(geo, labels)

    st.subheader("AMO-onderdelen")
    chart_help("amo")
    _toon_amo(selectie.inschrijvingen)
