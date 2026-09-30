"""Tab Opleidingen: top-10, domein, sectorkamer, leertraject, BPV en keuzedelen."""

import polars as pl
import streamlit as st
from _chart_docs import chart_help

from _dashboard.data import Selectie
from _dashboard.grafieken import (
    gevuld,
    hbar,
    sorteer_aantal,
    telling,
    toon_telling,
)

_BPV_DUUR_GRENZEN = (30, 90, 180)  # dagen — grenzen voor de duurklasse-buckets
_KZD_TOP_N = 15  # maximaal aantal keuzedelen in de detailtabel
_KZD_LAGE_GRENS = 50  # drempel waaronder slagingskans als laag wordt beschouwd (%)
_TOP_N_OPLEIDINGEN = 10


def _toon_top_opleidingen(df: pl.DataFrame) -> None:
    if "Opleidingcode" not in df.columns:
        st.info("Kolom `Opleidingcode` niet beschikbaar.")
        return
    top = sorteer_aantal(
        telling(df, "Opleidingcode", "Opleidingcode"), "Inschrijvingen", "Opleidingcode"
    ).head(_TOP_N_OPLEIDINGEN)
    if top.is_empty():
        st.info("Geen data beschikbaar voor deze grafiek.")
        return
    if "Opleiding_naam" in df.columns:
        naam_lookup = (
            df.select("Opleidingcode", "Opleiding_naam")
            .filter(pl.col("Opleiding_naam").is_not_null())
            .unique(subset=["Opleidingcode"], keep="first")
        )
        top = top.join(naam_lookup, on="Opleidingcode", how="left").with_columns(
            pl.coalesce("Opleiding_naam", "Opleidingcode").alias("Opleiding")
        )
    else:
        top = top.with_columns(("CREBO " + pl.col("Opleidingcode")).alias("Opleiding"))
    hbar(top, "Opleiding", "Inschrijvingen")


def _toon_bol_bbl(df: pl.DataFrame) -> None:
    if "Leertraject" not in df.columns or "levering" not in df.columns:
        st.info("Kolommen `levering` of `Leertraject` niet beschikbaar.")
        return
    bol_bbl = (
        df.filter(gevuld("Leertraject"))
        .group_by(["levering", "Leertraject"])
        .agg(pl.len().alias("Inschrijvingen"))
        .sort(["levering", "Leertraject"])
    )
    if bol_bbl.is_empty():
        st.info("Geen data beschikbaar voor deze grafiek.")
        return
    st.bar_chart(bol_bbl, x="levering", y="Inschrijvingen", color="Leertraject")


def _toon_bpv_coverage(df: pl.DataFrame) -> None:
    if "BPV_Aantal" not in df.columns or "Leertraject" not in df.columns:
        st.info("Kolommen `BPV_Aantal` of `Leertraject` niet beschikbaar.")
        return
    bpv = (
        df.filter(gevuld("Leertraject"))
        .with_columns(
            pl.when(pl.col("BPV_Aantal").is_not_null() & (pl.col("BPV_Aantal") > 0))
            .then(pl.lit("Met BPV"))
            .otherwise(pl.lit("Zonder BPV"))
            .alias("BPV_status")
        )
        .group_by(["Leertraject", "BPV_status"])
        .agg(pl.len().alias("Inschrijvingen"))
        .sort(["Leertraject", "BPV_status"])
    )
    if bpv.is_empty():
        st.info("Geen BPV-data beschikbaar.")
        return
    st.bar_chart(bpv, x="Leertraject", y="Inschrijvingen", color="BPV_status")


def _toon_kzd_per_levering(df: pl.DataFrame) -> None:
    if not {"KZD_Aantal", "KZD_AantalBehaald", "levering"} <= set(df.columns):
        st.info("Kolommen `KZD_Aantal` of `KZD_AantalBehaald` niet beschikbaar.")
        return
    kzd = (
        df.filter(
            pl.col("KZD_Aantal").is_not_null()
            & (pl.col("KZD_Aantal") > 0)
            & pl.col("KZD_AantalBehaald").is_not_null()
        )
        .with_columns(
            (pl.col("KZD_AantalBehaald") / pl.col("KZD_Aantal") * 100).alias("_ratio")
        )
        .group_by("levering")
        .agg(pl.col("_ratio").mean().round(1).alias("Gem. KZD behaald (%)"))
        .sort("levering")
        .rename({"levering": "Levering"})
    )
    if kzd.is_empty():
        st.info("Geen KZD-data beschikbaar.")
        return
    st.dataframe(kzd, width="stretch", hide_index=True)


def _duurklassen() -> tuple[pl.Expr, list[str]]:
    """Duurklasse van een BPV-periode en de klassen in volgorde."""
    d1, d2, d3 = _BPV_DUUR_GRENZEN
    klassen = [f"< {d1} dgn", f"{d1}–{d2} dgn", f"{d2}–{d3} dgn", f"> {d3} dgn"]
    duur = pl.col("Duur (dagen)")
    expr = (
        pl.when(duur < d1)
        .then(pl.lit(klassen[0]))
        .when(duur < d2)
        .then(pl.lit(klassen[1]))
        .when(duur < d3)
        .then(pl.lit(klassen[2]))
        .otherwise(pl.lit(klassen[3]))
    )
    return expr, klassen


def _toon_bpv_periodes(bpv: pl.DataFrame) -> None:
    if bpv.is_empty() or not {"DatumBegin", "DatumEindWerkelijk"} <= set(bpv.columns):
        st.info("fact_bpv niet beschikbaar of kolommen ontbreken.")
        return
    periodes = bpv.filter(
        pl.col("DatumBegin").is_not_null() & pl.col("DatumEindWerkelijk").is_not_null()
    ).with_columns(
        (pl.col("DatumEindWerkelijk") - pl.col("DatumBegin"))
        .dt.total_days()
        .alias("Duur (dagen)")
    )
    if periodes.is_empty():
        st.info("Geen BPV-periodes met bekende begin- én einddatum.")
        return
    bp1, bp2 = st.columns(2)
    bp1.metric("Periodes met bekende duur", f"{periodes.height:,}")
    bp2.metric("Gem. duur (dagen)", f"{periodes['Duur (dagen)'].mean():.0f}")
    if "Omvang" in periodes.columns:
        omvang = periodes["Omvang"].drop_nulls()
        if not omvang.is_empty():
            st.metric("Gem. omvang", f"{omvang.cast(pl.Float64).mean():.1f}")
    klasse, volgorde = _duurklassen()
    per_klasse = (
        periodes.with_columns(klasse.alias("Duur-klasse"))
        .group_by("Duur-klasse")
        .agg(pl.len().alias("Periodes"))
        .with_columns(pl.col("Duur-klasse").cast(pl.Enum(volgorde)))
        .sort("Duur-klasse")
    )
    st.bar_chart(per_klasse, x="Duur-klasse", y="Periodes")


def _toon_keuzedelen(kzd: pl.DataFrame) -> None:
    if kzd.is_empty() or not {"CodeKeuzedeel", "Behaald"} <= set(kzd.columns):
        st.info("fact_kzd niet beschikbaar of kolom `CodeKeuzedeel` ontbreekt.")
        return
    per_keuzedeel = (
        kzd.filter(pl.col("CodeKeuzedeel").is_not_null())
        .group_by("CodeKeuzedeel")
        .agg(pl.len().alias("Totaal"), pl.col("Behaald").sum().alias("Behaald"))
        .with_columns(
            (pl.col("Behaald") / pl.col("Totaal") * 100).round(1).alias("Behaald (%)")
        )
    )
    detail = sorteer_aantal(per_keuzedeel, "Totaal", "CodeKeuzedeel").head(_KZD_TOP_N)
    if detail.is_empty():
        st.info("Geen keuzedeel-data beschikbaar.")
        return
    st.dataframe(detail, width="stretch", hide_index=True)
    laag = detail.filter(pl.col("Behaald (%)") < _KZD_LAGE_GRENS)
    if not laag.is_empty():
        st.warning(
            f"{laag.height} keuzedeel(en) in de top-{_KZD_TOP_N} "
            f"met minder dan {_KZD_LAGE_GRENS}% behaald:"
        )
        st.dataframe(laag, width="stretch", hide_index=True)


def _toon_instelling(df: pl.DataFrame) -> None:
    if "Instelling_naam" not in df.columns:
        return
    kolommen = [c for c in ("Instelling_naam", "Instelling_plaats") if c in df.columns]
    info = (
        df.select(kolommen)
        .filter(pl.col("Instelling_naam").is_not_null())
        .unique()
        .sort(kolommen)
    )
    if not info.is_empty():
        st.subheader("Instelling")
        chart_help("instelling")
        st.dataframe(info, width="stretch", hide_index=True)


def toon(selectie: Selectie) -> None:
    df = selectie.inschrijvingen
    st.subheader("Top-10 opleidingen naar inschrijvingen")
    chart_help("top10_opleidingen")
    _toon_top_opleidingen(df)

    st.subheader("Inschrijvingen per domein")
    chart_help("inschrijvingen_domein")
    toon_telling(df, "Opleiding_domein", "Domein", "Geen domeindata beschikbaar.")

    st.subheader("Inschrijvingen per sectorkamer")
    chart_help("inschrijvingen_sectorkamer")
    toon_telling(
        df, "Opleiding_sectorkamer", "Sectorkamer", "Geen sectorkamerdata beschikbaar."
    )

    st.subheader("BOL vs BBL per levering")
    chart_help("bol_bbl_levering")
    _toon_bol_bbl(df)

    st.subheader("BPV-coverage")
    chart_help("bpv_coverage")
    _toon_bpv_coverage(df)

    st.subheader("KZD-behaaldverhouding per levering")
    chart_help("kzd")
    _toon_kzd_per_levering(df)

    st.subheader("BPV-periodes — duur en omvang")
    chart_help("bpv_periodes")
    _toon_bpv_periodes(selectie.bpv)

    st.subheader("Keuzedelen — resultaten per code")
    chart_help("kzd_detail")
    _toon_keuzedelen(selectie.kzd)

    _toon_instelling(df)
