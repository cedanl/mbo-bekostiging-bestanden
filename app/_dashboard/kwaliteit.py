"""Kwaliteitsstatus uit ``quality.json`` bovenaan het dashboard (#202)."""

from typing import Any

import polars as pl
import streamlit as st
from _chart_docs import chart_help

from mbo_bekostiging_bestanden.quality import (
    ERNST_ERROR,
    ERNST_INFO,
    ERNST_WARNING,
    FORMEEL_GEBRUIK_UITGESLOTEN,
    kwaliteitsmeldingen,
    slr_status_icoon,
)

_STATUS_WEERGAVE = {"fail": st.error, "warn": st.warning, "pass": st.success}
_ERNST_ICOON = {ERNST_ERROR: "❌", ERNST_WARNING: "⚠️", ERNST_INFO: "ℹ️"}
_LEVERING_KOLOMMEN = [
    "levering",
    "DatumAanmaak",
    "Peilgrens",
    "Peilgrens_bron",
    "Laatste_peildatum",
]


def uitstroom_scope(rapport: dict | None) -> str:
    """Binnen welke instellingen uitstroom bepaald is (``dr_scope``, #118)."""
    brins = (rapport or {}).get("star", {}).get("dr_scope", {}).get("brins", [])
    if not brins:
        return "Uitstroom is bepaald binnen de instellingen in de dataset."
    return (
        f"Uitstroom is bepaald binnen {', '.join(brins)}: een overstap naar een "
        "instelling buiten de dataset telt als uitstroom."
    )


def _indicatoren_tekst(indicatoren: dict[str, Any]) -> str:
    """Status per proxy-indicator met de formele afwijkingen (#369).

    Een ``quality.json`` van vóór #369 heeft hier een kale statusstring; die
    blijft leesbaar zodat een oud rapport geen KeyError geeft.
    """
    if not isinstance(indicatoren, dict):
        return str(indicatoren)
    statussen = ", ".join(
        f"{naam} {gegevens['status']}" for naam, gegevens in indicatoren.items()
    )
    # Besluit #296: geen officiële laag; ``formeel_gebruik`` ontbreekt vóór v4.0.0.
    if any(
        g.get("formeel_gebruik") == FORMEEL_GEBRUIK_UITGESLOTEN
        for g in indicatoren.values()
    ):
        statussen += " (formeel gebruik uitgesloten)"
    afwijkingen = [
        afwijking["code"]
        for gegevens in indicatoren.values()
        for afwijking in gegevens.get("afwijkingen", [])
    ]
    if not afwijkingen:
        return statussen
    return f"{statussen}; formele afwijkingen: {', '.join(sorted(set(afwijkingen)))}"


def toon(rapport: dict | None, meta_leveringen: pl.DataFrame) -> None:
    """Status, conformiteit, meldingen en bronleveringen."""
    if rapport is None:
        st.warning(
            "Geen `quality.json` bij dit star schema: de kwaliteit van de "
            "verwerking is onbekend. Bouw het schema opnieuw via Home."
        )
        return
    samenvatting = rapport["summary"]
    status = samenvatting["status"]
    _STATUS_WEERGAVE.get(status, st.warning)(
        f"Kwaliteitsstatus: {status} — {samenvatting['total_errors']} errors, "
        f"{samenvatting['total_warnings']} warnings"
    )
    conformiteit = rapport.get("conformiteit")
    if conformiteit:
        inhoud = str(conformiteit.get("pve_inhoudelijke_conformiteit", "?")).replace(
            "_", " "
        )
        versie = conformiteit.get("pve_versie", "?")
        indicatoren = _indicatoren_tekst(conformiteit["indicatoren"])
        st.caption(
            f"Indicatoren (JR/DR): **{indicatoren}**, geen formele "
            f"Inspectie-uitkomst · PvE-versie: {versie} ({inhoud}) "
            f"· privacyprofiel: {conformiteit['privacyprofiel']}"
        )
    with st.expander("Kwaliteitsmeldingen en bronleveringen"):
        chart_help("kwaliteit")
        for m in kwaliteitsmeldingen(rapport):
            st.markdown(f"{_ERNST_ICOON[m.ernst]} **{m.bron}** — {m.tekst}")
        slr = pl.DataFrame(
            {
                "levering": [d["levering"] for d in rapport["deliveries"]],
                "SLR": [
                    slr_status_icoon(d["slr_status"]) for d in rapport["deliveries"]
                ],
            }
        )
        kolommen = [c for c in _LEVERING_KOLOMMEN if c in meta_leveringen.columns]
        if "levering" in kolommen:
            leveringen = meta_leveringen.select(kolommen).join(
                slr, on="levering", how="left"
            )
            st.dataframe(leveringen, width="stretch", hide_index=True)
