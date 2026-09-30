"""Kerncijfers boven de tabs."""

import polars as pl
import streamlit as st

from _dashboard.data import Selectie


def toon(selectie: Selectie) -> None:
    df, jaren = selectie.inschrijvingen, selectie.jaren
    studenten_1okt = (
        jaren.filter(pl.col("_telling"))["_persoon_id"].n_unique()
        if {"_telling", "_persoon_id"} <= set(jaren.columns)
        else 0
    )
    bekostigd_n = int(jaren["_bekostigd"].sum()) if "_bekostigd" in jaren.columns else 0
    diplomas_n = (
        df.filter(pl.col("DIP_DatumResultaat").is_not_null()).height
        if "DIP_DatumResultaat" in df.columns
        else 0
    )
    n_leveringen = df["levering"].n_unique() if "levering" in df.columns else 0

    col1, col_studenten, col2, col3, col4 = st.columns(5)
    col1.metric(
        "Inschrijvingsperioden",
        f"{df.height:,}",
        help="Aantal ISP-perioden (rijen in fact_inschrijving) die in een "
        "geselecteerd schooljaar beginnen of er op 1 oktober actief zijn; één "
        "inschrijving kan meerdere perioden hebben.",
    )
    col_studenten.metric(
        "Studenten op 1 oktober",
        f"{studenten_1okt:,}",
        help="Unieke deelnemers met een telling (hoofdinschrijving op 1 oktober) "
        "in de geselecteerde schooljaren, uit fact_inschrijving_schooljaar.",
    )
    col2.metric(
        "Bekostigbaar op 1 oktober",
        f"{bekostigd_n:,}",
        help="Inschrijving × schooljaar met `IndicatieBekostigbaar` = J in de "
        "periode op 1 oktober, uit fact_inschrijving_schooljaar.",
    )
    col3.metric(
        "Diploma's behaald",
        f"{diplomas_n:,}",
        help="Inschrijvingsperioden met een ingevulde `DIP_DatumResultaat` "
        "(periode-grain, fact_inschrijving).",
    )
    col4.metric(
        "Leveringen",
        n_leveringen,
        help="Aantal unieke leveringen (bronbestanden) in de data.",
    )
