"""Tab Bekostiging: trechter, bekostigd per levering, na 1 oktober, TBG-i."""

import polars as pl
import streamlit as st
from _chart_docs import chart_help
from _indicatoren import ingeschreven_na_peildatum

from _dashboard.data import Selectie
from _dashboard.grafieken import hbar, heeft_kolommen

_GEEN_SCHOOLJAARFEIT = "fact_inschrijving_schooljaar niet beschikbaar."


def _toon_trechter(selectie: Selectie) -> None:
    jaren = selectie.jaren
    if not heeft_kolommen(jaren, {"_bekostigd"}):
        st.info(_GEEN_SCHOOLJAARFEIT)
        return
    actief_1okt_n = jaren.height
    bekostigd_1okt_n = int(jaren["_bekostigd"].sum())
    tc1, tc2, tc3, tc4 = st.columns(4)
    tc1.metric("Inschrijvingsperioden", f"{selectie.inschrijvingen.height:,}")
    tc2.metric(
        "Actief op 1-oktober",
        f"{actief_1okt_n:,}",
        help="Inschrijving × schooljaar met een periode die 1 oktober dekt.",
    )
    tc3.metric(
        "Bekostigbaar op 1-oktober",
        f"{bekostigd_1okt_n:,}",
        help="Waarvan `IndicatieBekostigbaar` = J in de periode op 1 oktober.",
    )
    tc4.metric("Actief maar niet bekostigbaar", f"{actief_1okt_n - bekostigd_1okt_n:,}")


def _toon_per_levering(jaren: pl.DataFrame) -> None:
    if not heeft_kolommen(jaren, {"_bekostigd", "levering"}):
        st.info(_GEEN_SCHOOLJAARFEIT)
        return
    bek_lev = (
        jaren.with_columns(
            pl.when(pl.col("_bekostigd"))
            .then(pl.lit("Bekostigd"))
            .otherwise(pl.lit("Niet bekostigd"))
            .alias("Bekostigingstatus")
        )
        .group_by(["levering", "Bekostigingstatus"])
        .agg(pl.len().alias("Inschrijvingen"))
        .sort(["levering", "Bekostigingstatus"])
    )
    if bek_lev.is_empty():
        st.info("Geen data beschikbaar voor deze grafiek.")
        return
    st.bar_chart(bek_lev, x="levering", y="Inschrijvingen", color="Bekostigingstatus")


def _toon_grondslagen(bekostiging: pl.DataFrame) -> None:
    if bekostiging.is_empty() or "Bekostigingsstatus" not in bekostiging.columns:
        st.info(
            "fact_bekostiging niet beschikbaar of kolom `Bekostigingsstatus` ontbreekt."
        )
        return
    bek_status = (
        bekostiging.filter(pl.col("Bekostigingsstatus").is_not_null())
        .group_by("Bekostigingsstatus")
        .agg(pl.len().alias("Inschrijvingen"))
    )
    if not bek_status.is_empty():
        hbar(bek_status, "Bekostigingsstatus", "Inschrijvingen")
    if "BijdrageInschrijvingAanDeelnemerswaarde" in bekostiging.columns:
        totaal_dw = bekostiging["BijdrageInschrijvingAanDeelnemerswaarde"].sum()
        st.metric(
            "Totale deelnemerswaarde (som)",
            f"{totaal_dw:,.2f}" if totaal_dw is not None else "—",
            help="Som van `BijdrageInschrijvingAanDeelnemerswaarde` over alle "
            "TBGI-rijen in de selectie.",
        )


def toon(selectie: Selectie) -> None:
    st.subheader("Bekostigingstrechter")
    chart_help("bekostigingstrechter")
    _toon_trechter(selectie)

    st.subheader("Bekostigd vs niet-bekostigd per levering")
    chart_help("bekostiging_levering")
    _toon_per_levering(selectie.jaren)

    st.subheader("Inschrijvingen na 1-oktober")
    chart_help("na_1okt")
    st.metric(
        "Ingeschreven na 1-oktober",
        f"{ingeschreven_na_peildatum(selectie.inschrijvingen, selectie.schooljaren):,}",
        help="Inschrijvingen die in een geselecteerd schooljaar ná 1 oktober "
        "begonnen; ze tellen dat schooljaar niet mee op de peildatum.",
    )

    st.subheader("Bekostigingsgrondslagen (TBGI)")
    chart_help("bekostigingsgrondslagen")
    _toon_grondslagen(selectie.bekostiging)
