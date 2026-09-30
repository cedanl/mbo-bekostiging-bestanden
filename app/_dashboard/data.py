"""Star schema laden en de schooljaarselectie toepassen, los van de weergave (#301)."""

import json
from dataclasses import dataclass
from pathlib import Path

import polars as pl
import streamlit as st

from mbo_bekostiging_bestanden.filters import (
    filter_bekostiging_op_schooljaren,
    filter_detail_op_inschrijvingen,
    filter_op_schooljaren,
    filter_perioden_op_schooljaren,
)

_KWALITEITSRAPPORT = "quality.json"


@dataclass(frozen=True)
class Ster:
    """De tabellen die het dashboard leest.

    ``inschrijvingen`` is ``fact_inschrijving`` met de drie dimensies erop
    (periode-grain); ``jaren`` is ``fact_inschrijving_schooljaar``, de bron voor
    rendementen en tellingen op 1 oktober (#136).
    """

    inschrijvingen: pl.DataFrame
    geo: pl.DataFrame
    bpv: pl.DataFrame
    kzd: pl.DataFrame
    bekostiging: pl.DataFrame
    jaren: pl.DataFrame
    meta_leveringen: pl.DataFrame


@dataclass(frozen=True)
class Selectie:
    """Elk feit gefilterd op de gekozen schooljaren, op zijn eigen grain (#240)."""

    schooljaren: list[int]
    inschrijvingen: pl.DataFrame
    jaren: pl.DataFrame
    geo: pl.DataFrame
    bpv: pl.DataFrame
    kzd: pl.DataFrame
    bekostiging: pl.DataFrame


@st.cache_resource(show_spinner=False)
def _lees_parquet(pad: str, mtime: float) -> pl.DataFrame:
    """Lees een parquet-bestand en cache op pad + wijzigingsdatum."""
    return pl.read_parquet(pad)


def parquet_max_mtime(data_dir: Path) -> float:
    dm = data_dir / "datamodel"
    if not dm.exists():
        return 0.0
    return max((p.stat().st_mtime for p in dm.glob("*.parquet")), default=0.0)


def _met_dimensies(
    feit: pl.DataFrame, dimensies: list[tuple[pl.DataFrame, str]]
) -> pl.DataFrame:
    """Left join per (dimensie, sleutel), alleen als beide kanten er zijn."""
    for dim, sleutel in dimensies:
        if dim.is_empty() or sleutel not in feit.columns:
            continue
        feit = feit.join(dim, on=sleutel, how="left")
        feit = feit.drop([c for c in feit.columns if c.endswith("_right")])
    return feit


@st.cache_data(show_spinner=False)
def lees_star_schema(data_dir: Path, max_mtime: float) -> Ster:
    """Laad het star schema; ``max_mtime`` is alleen de cache-sleutel."""
    dm = data_dir / "datamodel"

    def laad(name: str) -> pl.DataFrame:
        p = dm / f"{name}.parquet"
        if not p.exists():
            return pl.DataFrame()
        return _lees_parquet(str(p), p.stat().st_mtime)

    deelnemer = laad("dim_deelnemer")
    opleiding = laad("dim_opleiding")
    instelling = laad("dim_instelling")
    return Ster(
        inschrijvingen=_met_dimensies(
            laad("fact_inschrijving"),
            [
                (deelnemer, "_persoon_id"),
                (opleiding, "Opleidingcode"),
                (instelling, "BRIN"),
            ],
        ),
        geo=laad("fact_geo"),
        bpv=laad("fact_bpv"),
        kzd=laad("fact_kzd"),
        bekostiging=_met_dimensies(
            laad("fact_bekostiging"),
            [(opleiding, "Opleidingcode"), (instelling, "BRIN")],
        ),
        jaren=laad("fact_inschrijving_schooljaar"),
        meta_leveringen=laad("meta_leveringen"),
    )


def selecteer(ster: Ster, schooljaren: list[int]) -> Selectie:
    """Tellingen en rendementen op schooljaar-grain; perioden die in een gekozen
    jaar beginnen of er op 1 oktober actief zijn; detailfeiten via hun periode;
    bekostiging op het schooljaar van de teldatum."""
    inschrijvingen = filter_perioden_op_schooljaren(
        ster.inschrijvingen, ster.jaren, schooljaren
    )
    return Selectie(
        schooljaren=schooljaren,
        inschrijvingen=inschrijvingen,
        jaren=filter_op_schooljaren(ster.jaren, schooljaren),
        geo=filter_detail_op_inschrijvingen(ster.geo, inschrijvingen),
        bpv=filter_detail_op_inschrijvingen(ster.bpv, inschrijvingen),
        kzd=filter_detail_op_inschrijvingen(ster.kzd, inschrijvingen),
        bekostiging=filter_bekostiging_op_schooljaren(ster.bekostiging, schooljaren),
    )


def lees_kwaliteitsrapport(data_dir: Path) -> dict | None:
    pad = data_dir / _KWALITEITSRAPPORT
    if not pad.exists():
        return None
    return json.loads(pad.read_text(encoding="utf-8"))
