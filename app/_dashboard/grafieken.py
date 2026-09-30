"""Gedeelde grafiekhelpers voor de dashboardtabs."""

import altair as alt
import polars as pl
import streamlit as st


def heeft_kolommen(df: pl.DataFrame, kolommen: set[str]) -> bool:
    return kolommen <= set(df.columns)


def sorteer_aantal(df: pl.DataFrame, aantal: str, label: str) -> pl.DataFrame:
    """Aflopend op ``aantal``, met gelijke tellingen op ``label`` daarbovenop.

    ``group_by`` legt geen stabiele rijvolgorde vast, dus zonder tweede sleutel
    verschilt de volgorde van gelijke tellingen per run — en in een top-N
    wisselt dan zelfs welke regels getoond worden (#301).
    """
    return df.sort([aantal, label], descending=[True, False])


def hbar(df: pl.DataFrame, label: str, value: str) -> None:
    """Horizontaal staafdiagram, meest bovenaan.

    De sortering zit hier en niet bij de aanroeper: de grafiek moet op zichzelf
    reproduceerbaar zijn, welke volgorde de aanroeper ook meegeeft.
    """
    ordening = sorteer_aantal(df, value, label)
    chart = (
        alt.Chart(ordening.select([label, value]))
        .mark_bar()
        .encode(
            y=alt.Y(f"{label}:N", sort="-x", title=label),
            x=alt.X(f"{value}:Q", title=value),
        )
    )
    st.altair_chart(chart, width="stretch")


def gevuld(kolom: str) -> pl.Expr:
    """Niet leeg en niet de lege string."""
    return pl.col(kolom).is_not_null() & (pl.col(kolom) != "")


def telling(
    df: pl.DataFrame, kolom: str, label: str, aantal: str = "Inschrijvingen"
) -> pl.DataFrame:
    """Aantal rijen per gevulde waarde van ``kolom``, met ``label`` als kolomnaam."""
    return (
        df.filter(gevuld(kolom))
        .group_by(kolom)
        .agg(pl.len().alias(aantal))
        .rename({kolom: label})
    )


def toon_telling(
    df: pl.DataFrame, kolom: str, label: str, leeg: str, aantal: str = "Inschrijvingen"
) -> None:
    """:func:`telling` als horizontale staaf, of een melding als er niets is."""
    if kolom not in df.columns:
        st.info(f"Kolom `{kolom}` niet beschikbaar.")
        return
    tabel = telling(df, kolom, label, aantal)
    if tabel.is_empty():
        st.info(leeg)
        return
    hbar(tabel, label, aantal)
