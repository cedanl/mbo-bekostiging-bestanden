"""Tab Studenten: geslacht, herkomst, woonplaats, uitstroom en duur."""

import polars as pl
import streamlit as st
from _chart_docs import chart_help

from _dashboard.data import Selectie
from _dashboard.grafieken import gevuld, hbar, sorteer_aantal, telling

REDEN_LABELS = {
    "01": "Diploma BOL",
    "02": "Diploma BBL",
    "06": "Eigen verzoek",
    "08": "Verwijdering instelling",
    "4": "Geslaagd (oud)",
    "7": "Uitstroom zonder diploma",
    "8": "Verwijderd (oud)",
}
_GESLACHT = {"M": "Man", "V": "Vrouw", "O": "Onbekend"}
_TOP_N = 10
# Geboorteland-namen die geen land zijn (onbekend of lege decodering).
_GEEN_LAND = ("Onbekend", "NULL")
# Duurklassen in maanden: bovengrens → label; de laatste klasse is open.
_DUUR_KLASSEN = {6: "< 6 mnd", 12: "6–12 mnd", 24: "12–24 mnd", 36: "24–36 mnd"}
_DUUR_OPEN = "> 36 mnd"
_DAGEN_PER_MAAND = 30


def _toon_geslacht(df: pl.DataFrame) -> None:
    if "Geslacht" not in df.columns or "Leertraject" not in df.columns:
        st.info("Kolommen `Geslacht` of `Leertraject` niet beschikbaar.")
        return
    geslacht = (
        df.filter(gevuld("Geslacht") & gevuld("Leertraject"))
        .with_columns(pl.col("Geslacht").replace(_GESLACHT))
        .group_by(["Geslacht", "Leertraject"])
        .agg(pl.len().alias("Inschrijvingen"))
        .sort(["Geslacht", "Leertraject"])
    )
    if geslacht.is_empty():
        st.info("Geen data beschikbaar voor deze grafiek.")
        return
    st.bar_chart(geslacht, x="Leertraject", y="Inschrijvingen", color="Geslacht")


def _toon_herkomst(df: pl.DataFrame) -> None:
    kolom = "Nationaliteit1_migratieachtergrond"
    if kolom not in df.columns:
        return
    st.subheader("Herkomst (migratieachtergrond)")
    chart_help("herkomst")
    herkomst = (
        df.filter(pl.col(kolom).is_not_null())
        .group_by(kolom)
        .agg(pl.len().alias("Inschrijvingen"))
        .rename({kolom: "Migratieachtergrond"})
    )
    if herkomst.is_empty():
        st.info("Geen herkomstdata beschikbaar.")
        return
    hbar(herkomst, "Migratieachtergrond", "Inschrijvingen")


def _toon_top(df: pl.DataFrame, kolom: str, label: str, leeg: str) -> None:
    """Top-``_TOP_N`` van een kolom als tabel."""
    top = sorteer_aantal(
        telling(df, kolom, label, aantal="Studenten"), "Studenten", label
    ).head(_TOP_N)
    if top.is_empty():
        st.info(leeg)
        return
    st.dataframe(top, width="stretch", hide_index=True)


def _toon_uitstroom(df: pl.DataFrame) -> None:
    if "RedenUitschrijving" not in df.columns:
        st.info("Kolom `RedenUitschrijving` niet beschikbaar.")
        return
    reden_code = pl.col("RedenUitschrijving")
    uitstroom = (
        df.with_columns(
            pl.when(reden_code.is_null() | (reden_code == ""))
            .then(pl.lit("Nog ingeschreven"))
            .when(reden_code.is_in(REDEN_LABELS))
            .then(reden_code.replace(REDEN_LABELS))
            .otherwise(pl.format("Overig (code: {})", reden_code))
            .alias("Reden")
        )
        .group_by("Reden")
        .agg(pl.len().alias("Aantal"))
    )
    if uitstroom.is_empty():
        st.info("Geen uitstroomdata beschikbaar.")
        return
    hbar(uitstroom, "Reden", "Aantal")


def _duurklasse(maanden: pl.Expr) -> pl.Expr:
    (eerste, label), *rest = _DUUR_KLASSEN.items()
    expr = pl.when(maanden < eerste).then(pl.lit(label))
    for grens, label in rest:
        expr = expr.when(maanden < grens).then(pl.lit(label))
    return expr.otherwise(pl.lit(_DUUR_OPEN))


def _toon_duur(df: pl.DataFrame) -> None:
    if not {"DatumInschrijving", "DatumUitschrijvingWerkelijk"} <= set(df.columns):
        st.info(
            "Kolommen `DatumInschrijving` of `DatumUitschrijvingWerkelijk` "
            "niet beschikbaar."
        )
        return
    duur = (
        df.filter(
            pl.col("DatumInschrijving").is_not_null()
            & pl.col("DatumUitschrijvingWerkelijk").is_not_null()
        )
        .with_columns(
            (
                (
                    pl.col("DatumUitschrijvingWerkelijk") - pl.col("DatumInschrijving")
                ).dt.total_days()
                / _DAGEN_PER_MAAND
            ).alias("Duur_maanden")
        )
        .filter(pl.col("Duur_maanden") > 0)
    )
    if duur.is_empty():
        st.info("Geen inschrijvingen met bekende in- en uitschrijfdatum.")
        return
    volgorde = [*_DUUR_KLASSEN.values(), _DUUR_OPEN]
    per_klasse = (
        duur.with_columns(_duurklasse(pl.col("Duur_maanden")).alias("Bucket"))
        .group_by("Bucket")
        .agg(pl.len().alias("Inschrijvingen"))
        .with_columns(pl.col("Bucket").cast(pl.Enum(volgorde)))
        .sort("Bucket")
    )
    st.bar_chart(per_klasse, x="Bucket", y="Inschrijvingen")


def toon(selectie: Selectie) -> None:
    df = selectie.inschrijvingen
    st.subheader("Geslachtsverdeling per Leertraject")
    chart_help("geslacht_leertraject")
    _toon_geslacht(df)

    _toon_herkomst(df)
    if "Gemeente" in df.columns:
        st.subheader("Top 10 gemeenten")
        chart_help("top10_gemeenten")
        _toon_top(df, "Gemeente", "Gemeente", "Geen gemeentedata beschikbaar.")

    if "CodeGeboorteland_naam" in df.columns:
        st.subheader("Top 10 geboorteland")
        chart_help("top10_geboorteland")
        _toon_top(
            df.filter(~pl.col("CodeGeboorteland_naam").is_in(_GEEN_LAND)),
            "CodeGeboorteland_naam",
            "Geboorteland",
            "Geen geboortelanddata beschikbaar.",
        )

    st.subheader("Uitstroomredenen")
    chart_help("uitstroomredenen")
    _toon_uitstroom(df)

    st.subheader("Duur inschrijving (maanden)")
    chart_help("duur_inschrijving")
    _toon_duur(df)
