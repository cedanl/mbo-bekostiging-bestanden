"""Tab Rendementen: JR/DR-proxy, proxy-oordeel, Entree en diploma's."""

import polars as pl
import streamlit as st
from _chart_docs import chart_help

from _dashboard.data import Selectie
from _dashboard.grafieken import gevuld, heeft_kolommen
from _dashboard.kwaliteit import uitstroom_scope
from mbo_bekostiging_bestanden.indicatoren import (
    bereken_oordeel,
    entree_indicatoren,
    entree_totaal,
    norm_voor,
    rendement,
)

_JR_KOLOMMEN = {"Schooljaar", "Niveau", "_jr_noemer", "_jr_teller"}
_DR_KOLOMMEN = {"Schooljaar", "Niveau", "_dr_noemer", "_dr_teller"}


def _toon_rendement(tabel: pl.DataFrame | None, naam: str, leeg: str) -> None:
    """Tabel en staafdiagram van :func:`indicatoren.rendement`."""
    if tabel is None:
        st.info("fact_inschrijving_schooljaar niet beschikbaar.")
        return
    if tabel.is_empty():
        st.info(leeg)
        return
    proxykolom = f"{naam}-proxy (%)"
    weergave = tabel.with_columns(pl.col("Schooljaar").cast(pl.Utf8)).rename(
        {"Percentage": proxykolom}
    )
    st.dataframe(weergave, width="stretch", hide_index=True)
    st.bar_chart(weergave, x="Niveau", y=proxykolom, color="Schooljaar")
    st.caption(
        f"{naam}-normen komen uit `metadata/normen.toml`; `Voldoet` is een "
        "indicatieve vergelijking van de proxy met de voldoende-norm, geen formele "
        "beoordeling. Zie de toelichting voor de definitie."
    )


def _rendement_per_niveau(
    *tabellen: pl.DataFrame | None,
) -> dict[str, dict[str, dict[str, float | int | None]]]:
    """Niveau → indicator → {waarde, noemer}, opgeteld over de schooljaren."""
    uit: dict[str, dict[str, dict[str, float | int | None]]] = {}
    for sleutel, tabel in zip(("jr", "dr"), tabellen, strict=True):
        if tabel is None or tabel.is_empty():
            continue
        totaal = tabel.group_by("Niveau").agg(
            pl.col("Noemer").sum(), pl.col("Teller").sum()
        )
        for r in totaal.iter_rows(named=True):
            uit.setdefault(r["Niveau"], {})[sleutel] = {
                "waarde": r["Teller"] / r["Noemer"] * 100,
                "noemer": r["Noemer"],
            }
    return uit


def _toon_oordeel(jr: pl.DataFrame | None, dr: pl.DataFrame | None) -> None:
    per_niveau = _rendement_per_niveau(jr, dr)
    if not per_niveau:
        st.info("Geen beoordeelbare rijen (niveau 2–4).")
        return
    rows = []
    for niv_str, ind in sorted(per_niveau.items()):
        niv = int(niv_str.split("-")[-1])
        oordeel, _, _ = bereken_oordeel(ind.get("jr"), ind.get("dr"), None, niveau=niv)
        row: dict = {"Niveau": niv_str, "Proxy-oordeel": oordeel}
        for naam, sleutel in (("JR", "jr"), ("DR", "dr")):
            waarde = ind.get(sleutel, {}).get("waarde")
            if waarde is not None:
                row[f"{naam}-proxy (%)"] = round(waarde, 1)
                row[f"Voldoende-norm {naam} (%)"] = norm_voor(sleutel, niv, "voldoende")
        rows.append(row)
    st.dataframe(pl.DataFrame(rows), width="stretch", hide_index=True)
    st.warning(
        "SR (startersresultaat) is niet beschikbaar — dit vereist zes "
        "jaar inschrijvingshistorie die buiten de eigen leveringen valt. "
        "Het oordeel is op JR-proxy + DR-proxy gebaseerd en daarmee indicatief. "
        "Het telt de geselecteerde schooljaren op en is niet het formele "
        "driejaarsvenster. "
        "Bij één ontbrekende "
        "indicator is een oordeel alleen mogelijk als de twee aanwezige "
        "indicatoren dezelfde richting uitwijzen (§3.5)."
    )


def _toon_entree(jaren: pl.DataFrame) -> None:
    entree_df = entree_indicatoren(jaren)
    if entree_df.is_empty():
        st.info(
            "Geen entree-studenten die Entree verlaten in de geselecteerde "
            "schooljaren (vraagt een waarneembaar volgend schooljaar)."
        )
        return
    st.metric(
        "Entree-populatie (noemer)",
        f"{entree_totaal(jaren):,}",
        help="Hoofdinschrijvingen op niveau 1 die na het schooljaar doorstromen "
        "naar niveau ≥ 2 of uitstromen, uit fact_inschrijving_schooljaar.",
    )
    st.dataframe(entree_df, width="stretch", hide_index=True)
    if "Categorie" in entree_df.columns:
        st.bar_chart(entree_df, x="Categorie", y="Aandeel (%)")


def _toon_diplomas_per_leertraject(df: pl.DataFrame) -> None:
    if "Leertraject" not in df.columns or "DIP_DatumResultaat" not in df.columns:
        st.info("Kolommen `Leertraject` of `DIP_DatumResultaat` niet beschikbaar.")
        return
    dip_lt = (
        df.with_columns(
            pl.when(pl.col("DIP_DatumResultaat").is_not_null())
            .then(pl.lit("Diploma behaald"))
            .otherwise(pl.lit("Geen diploma"))
            .alias("Diplomastatus")
        )
        .filter(gevuld("Leertraject"))
        .group_by(["Leertraject", "Diplomastatus"])
        .agg(pl.len().alias("Inschrijvingen"))
        .sort(["Leertraject", "Diplomastatus"])
    )
    if dip_lt.is_empty():
        st.info("Geen data beschikbaar voor deze grafiek.")
        return
    st.bar_chart(dip_lt, x="Leertraject", y="Inschrijvingen", color="Diplomastatus")


def toon(selectie: Selectie, rapport: dict | None) -> None:
    jaren = selectie.jaren
    st.subheader("Jaarresultaat (JR-proxy) — per schooljaar en niveau")
    chart_help("jr_indicatief")
    jr = rendement(jaren, "jr") if heeft_kolommen(jaren, _JR_KOLOMMEN) else None
    _toon_rendement(jr, "JR", "Geen JR-noemer in de geselecteerde schooljaren.")

    st.subheader("Diplomaresultaat (DR-proxy) — per schooljaar en niveau")
    chart_help("dr_indicatief")
    dr = rendement(jaren, "dr") if heeft_kolommen(jaren, _DR_KOLOMMEN) else None
    _toon_rendement(
        dr,
        "DR",
        "Geen uitstromers in de geselecteerde schooljaren (DR vraagt een "
        "waarneembaar volgend schooljaar).",
    )
    st.caption(
        f"DR-proxy: diploma's van vóór de eerste levering ontbreken. "
        f"{uitstroom_scope(rapport)}"
    )

    st.subheader("Proxy-oordeel Studiesucces (indicatief)")
    chart_help("berekend_oordeel")
    _toon_oordeel(jr, dr)

    st.subheader("Entree-indicatoren (niveau 1)")
    chart_help("entree")
    _toon_entree(jaren)

    st.subheader("Diploma's per Leertraject")
    chart_help("diplomas_leertraject")
    _toon_diplomas_per_leertraject(selectie.inschrijvingen)
