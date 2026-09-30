"""Tab Opleidingsstructuur: dossiers, S-BB-beroepen, looptijd en hercodering."""

import polars as pl
import streamlit as st
from _chart_docs import chart_help

from _dashboard.data import Selectie
from _dashboard.grafieken import hbar, sorteer_aantal, telling

_SBB_BEROEP_TOP_N = 20  # maximaal aantal beroepen in de S-BB-grafiek


def _toon_dossiers(df: pl.DataFrame) -> None:
    if not {"Opleiding_dossiercode", "Opleiding_dossier"} <= set(df.columns):
        st.info(
            "Kolommen `Opleiding_dossiercode` of `Opleiding_dossier` niet beschikbaar."
        )
        return
    dossier = (
        df.filter(pl.col("Opleiding_dossiercode").is_not_null())
        .with_columns(
            pl.format("{} — {}", "Opleiding_dossiercode", "Opleiding_dossier").alias(
                "Dossier"
            )
        )
        .group_by("Dossier")
        .agg(pl.len().alias("Inschrijvingen"))
    )
    if dossier.is_empty():
        st.info("Geen dossierdata beschikbaar.")
        return
    hbar(dossier, "Dossier", "Inschrijvingen")


def _toon_beroepen(df: pl.DataFrame) -> None:
    if "Opleiding_beroep" not in df.columns:
        st.info("Kolom `Opleiding_beroep` niet beschikbaar.")
        return
    beroep = sorteer_aantal(
        telling(df, "Opleiding_beroep", "Beroep"), "Inschrijvingen", "Beroep"
    ).head(_SBB_BEROEP_TOP_N)
    if beroep.is_empty():
        st.info("Geen beroepsdata beschikbaar (S-BB koppeltabel).")
        return
    hbar(beroep, "Beroep", "Inschrijvingen")


def _toon_looptijd(df: pl.DataFrame) -> None:
    eerste, laatste = "Opleiding_eerste_schooljaar", "Opleiding_laatste_schooljaar"
    if not {eerste, laatste} <= set(df.columns):
        st.info(f"Kolommen `{eerste}` of `{laatste}` niet beschikbaar.")
        return
    met_looptijd = df.filter(pl.col(laatste).is_not_null())
    kolommen = [
        c
        for c in ("Opleidingcode", "Opleiding_naam", eerste, laatste)
        if c in df.columns
    ]
    looptijd = (
        met_looptijd.select(kolommen)
        .unique(subset=["Opleidingcode"])
        .sort([laatste, "Opleidingcode"])
    )
    if looptijd.is_empty():
        st.info("Geen looptijddata beschikbaar.")
        return
    per_jaar = (
        met_looptijd.group_by(laatste)
        .agg(pl.len().alias("Inschrijvingen"))
        .sort(laatste)
        .rename({laatste: "Laatste schooljaar"})
    )
    st.bar_chart(per_jaar, x="Laatste schooljaar", y="Inschrijvingen")
    with st.expander("Detailtabel opleidingen met looptijd"):
        st.dataframe(looptijd, width="stretch", hide_index=True)


def _toon_hercodering(df: pl.DataFrame) -> None:
    if not {"Opleiding_opvolger", "Opleidingcode"} <= set(df.columns):
        st.info("Kolom `Opleiding_opvolger` niet beschikbaar.")
        return
    oud = df.filter(pl.col("Opleiding_opvolger").is_not_null())
    kolommen = [
        c
        for c in (
            "Opleidingcode",
            "Opleiding_naam",
            "Opleiding_opvolger",
            "Opleiding_dossier",
        )
        if c in df.columns
    ]
    codes = oud.select(kolommen).unique(subset=["Opleidingcode"]).sort("Opleidingcode")
    hc1, hc2 = st.columns(2)
    hc1.metric(
        "Unieke codes mét opvolger",
        codes.height,
        help="Aantal unieke CREBO-codes (25xxx) waarvoor de S-BB koppeltabel "
        "een opvolger (27xxx) vermeldt.",
    )
    hc2.metric(
        "Inschrijvingen op 'oude' code",
        f"{oud.height:,}",
        help="Inschrijvingen waarbij de Opleidingcode een opvolger heeft; "
        "voor longitudinale analyses samenvoegen met de 27xxx-opvolger.",
    )
    if codes.is_empty():
        st.info("Geen opleidingen met opvolger in de geselecteerde data.")
        return
    st.dataframe(codes, width="stretch", hide_index=True)


def toon(selectie: Selectie) -> None:
    df = selectie.inschrijvingen
    st.markdown(
        "Overzicht van de CREBO-structuur: **kwalificatiedossiers (23xxx)**, "
        "**kwalificaties/beroepen (25xxx/27xxx)** via de S-BB koppeltabel, "
        "en **hercodering** bij dossierherziening. "
        "Klik op ℹ️ bij elke grafiek voor de exacte definitie."
    )

    st.subheader("Inschrijvingen per kwalificatiedossier (23xxx)")
    chart_help("dossier_inschrijvingen")
    _toon_dossiers(df)

    st.subheader("Inschrijvingen per beroep (S-BB koppeltabel)")
    chart_help("sbb_beroep_inschrijvingen")
    _toon_beroepen(df)

    st.subheader("Looptijd van opleidingen (S-BB)")
    chart_help("sbb_looptijd")
    _toon_looptijd(df)

    st.subheader("Hercodering: 25xxx → 27xxx (via S-BB opvolger)")
    chart_help("hercodering_25_27")
    _toon_hercodering(df)
