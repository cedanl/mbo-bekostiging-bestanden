"""Dimensionaal model (star schema) afgeleid van de analysetabellen.

Splitst ``inschrijvingen`` in drie dimensietabellen en één feitstabel,
en promoveert de detail-tabellen (BPV, KZD, AMO, GEO, bekostiging) naar
expliciete feittabellen met een stabiel schema.

Publieke API:
    build_star(stacked) -> dict[str, pl.DataFrame]
"""

from __future__ import annotations

import re

import polars as pl

from mbo_bekostiging_bestanden.enrich import verrijk_instelling
from mbo_bekostiging_bestanden.transform import _PERSOON_COLS, _bouw_analysetabellen

# ---------------------------------------------------------------------------
# Kolomdefinities per dimensie
# ---------------------------------------------------------------------------

_DIM_DEELNEMER_COLS = [
    "_persoon_id",
    "Geboortedatum",
    "Geslacht",
    "Postcodecijfers",
    "Gemeente",
    "Gemeentecode",
    "Nationaliteit1",
    "Nationaliteit1_naam",
    "Nationaliteit1_migratieachtergrond",
    "Nationaliteit2",
    "Nationaliteit2_naam",
    "Nationaliteit2_migratieachtergrond",
    "CodeGeboorteland",
    "CodeGeboorteland_naam",
    "CodeGeboorteland_migratieachtergrond",
    "CodeGeboortelandOuder1",
    "CodeGeboortelandOuder2",
    "Verblijfstitel",
    "DatumVestigingNederland",
    "DatumVertrekNederland",
    "CodeLandWaarnaarVertrokken",
]

_DIM_OPLEIDING_COLS = [
    "Opleidingcode",
    "Niveau",
    "Opleiding_naam",
    "Opleiding_leerweg",
    "Opleiding_domein",
    "Opleiding_subgroep",
    "Opleiding_dossiercode",
    "Opleiding_dossier",
    "Opleiding_sectorkamer",
    # S-BB koppeltabel (Groep 19)
    "Opleiding_beroep",
    "Opleiding_niveau",
    "Opleiding_opvolger",
    "Opleiding_eerste_schooljaar",
    "Opleiding_laatste_schooljaar",
    # S-BB crebolijst (Groep 14)
    "Opleiding_geldig_van",
    "Opleiding_geldig_tot",
    "Opleiding_prijsfactor",
    "Opleiding_soort_opleiding",
]

_DIM_INSTELLING_COLS = [
    "BRIN",
    "Instelling_naam",
    "Instelling_plaats",
]

# Foreign keys: blijven zowel in de fact als in de dim.
_FK_COLS = {"_persoon_id", "Opleidingcode", "BRIN"}

# GEO-pivotkolommen in inschrijvingen (GEO_{code}_{veld}).
# Deze zijn schema-instabiel en worden vervangen door fact_geo.
_GEO_COL_RE = re.compile(r"^GEO_\d+_")

# Kolommen die PII bevatten en uit de output verwijderd worden.
# _persoon_id is gepseudonimiseerd (HMAC-SHA256), maar de bron-identifiers
# (PGN, BSN, ONr) staan nog rechtstreeks in de brondata en moeten weg.
_PERSON_IDENTIFIER_COLS = set(_PERSOON_COLS)
_PII_DROP = _PERSON_IDENTIFIER_COLS | {"_bron"}
_BEKOSTIGING_DROP = _PII_DROP

# Interne implementatie-details die niet in het exporteerbare star schema horen.
# Deze kolommen zijn tussenstappen in transformatie en niet bedoeld voor analyse.
_INTERNAL_COLS = {"_schooljaren_actief"}  # List aggregaat uit _bepaal_actief_per_sj


# ---------------------------------------------------------------------------
# Publieke API
# ---------------------------------------------------------------------------


def build_star(
    stacked: dict[str, pl.DataFrame],
) -> dict[str, pl.DataFrame]:
    """Bouw het star schema vanuit gestapelde genormaliseerde records.

    Args:
        stacked: Output van :func:`~mbo_bekostiging_bestanden.stack.stack_prepared`,
                 dict van tabelnaam → DataFrame.

    Returns:
        Dict met elf sleutels:

        Dimensies:
          ``dim_deelnemer``              — uniek per ``_persoon_id``
          ``dim_opleiding``              — uniek per ``Opleidingcode``
          ``dim_instelling``             — uniek per ``BRIN``, uit alle feiten

        Feiten:
          ``fact_inschrijving``          — ISP-periode-grain, uniek per sleutel
          ``fact_bpv``                   — BPV-periodes per inschrijving
          ``fact_kzd``                   — Keuzedelen per inschrijving
          ``fact_amo``                   — AMO-onderdelen per inschrijving
          ``fact_geo``                   — GEO-examenresultaten in long format
          ``fact_bekostiging``           — TBGI Teldatum-grondslagen per inschrijving
          ``fact_bekostiging_diploma``   — TBGI diplomawaarde-bijdragen per inschrijving

        Metadata:
          ``meta_leveringen``            — VLP + SLR per bronbestand (per levering)
    """
    tables = _bouw_analysetabellen(stacked)
    inschrijvingen = tables["inschrijvingen"]

    dim_deelnemer = _build_dim(inschrijvingen, _DIM_DEELNEMER_COLS, "_persoon_id")
    dim_opleiding = _build_dim(inschrijvingen, _DIM_OPLEIDING_COLS, "Opleidingcode")
    dim_instelling = _build_dim_instelling(tables)

    dim_col_set = (
        set(_DIM_DEELNEMER_COLS) | set(_DIM_OPLEIDING_COLS) | set(_DIM_INSTELLING_COLS)
    ) - _FK_COLS

    # GEO-pivotkolommen verwijderen: schema-instabiel en nu in fact_geo.
    geo_cols = {c for c in inschrijvingen.columns if _GEO_COL_RE.match(c)}

    fact_cols = [
        c for c in inschrijvingen.columns if c not in dim_col_set and c not in geo_cols
    ]
    fact_inschrijving = inschrijvingen.select(fact_cols)

    # Verwijder persoonsidentificerende gegevens en interne kolommen
    to_drop = []
    pii_to_drop = [c for c in _PII_DROP if c in fact_inschrijving.columns]
    internal_to_drop = [c for c in _INTERNAL_COLS if c in fact_inschrijving.columns]
    to_drop.extend(pii_to_drop)
    to_drop.extend(internal_to_drop)

    if to_drop:
        fact_inschrijving = fact_inschrijving.drop(to_drop)

    return {
        "dim_deelnemer": dim_deelnemer,
        "dim_opleiding": dim_opleiding,
        "dim_instelling": dim_instelling,
        "fact_inschrijving": fact_inschrijving,
        "fact_bpv": _build_fact_bpv(tables),
        "fact_kzd": _build_fact_kzd(tables),
        "fact_amo": _build_fact_amo(tables),
        "fact_geo": _build_fact_geo(tables),
        "fact_bekostiging": _build_fact_bekostiging(tables),
        "fact_bekostiging_diploma": _build_fact_bekostiging_diploma(tables),
        "meta_leveringen": tables.get("meta_leveringen", pl.DataFrame()),
    }


# ---------------------------------------------------------------------------
# Feittabel-builders
# ---------------------------------------------------------------------------


def _build_fact_bpv(tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """fact_bpv: BPV-periodes per inschrijving.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, Volgnummer).
    Joinbaar met fact_inschrijving via _inschrijving_periode_id.
    Persoonsidentificerende gegevens (BSN, ONr) worden verwijderd.
    """
    detail = tables.get("detail_bpv", pl.DataFrame())
    if detail.is_empty():
        return pl.DataFrame()
    drop = [c for c in _PII_DROP if c in detail.columns]
    return detail.drop(drop)


def _uit_kzd_amo_detail(tables: dict[str, pl.DataFrame], bron: str) -> pl.DataFrame:
    detail = tables.get("detail_kzd_amo", pl.DataFrame())
    if detail.is_empty() or "_bron" not in detail.columns:
        return pl.DataFrame()
    filtered = detail.filter(pl.col("_bron") == bron)
    if filtered.is_empty():
        return pl.DataFrame()
    drop = [c for c in _PII_DROP if c in filtered.columns]
    return filtered.drop(drop)


def _build_fact_kzd(tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """fact_kzd: Keuzedelen per inschrijving.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, Resultaatvolgnummer).
    """
    return _uit_kzd_amo_detail(tables, "KZD")


def _build_fact_amo(tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """fact_amo: AMO-onderdelen per inschrijving.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, Resultaatvolgnummer).
    """
    return _uit_kzd_amo_detail(tables, "AMO")


def _build_fact_bekostiging(tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """fact_bekostiging: TBGI bekostigingsgrondslagen per inschrijving.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, Teldatum).
    Joinbaar met fact_inschrijving via _inschrijving_periode_id en met
    dim_instelling via BRIN.  BSN en Onderwijsnummer worden verwijderd.
    """
    detail = tables.get("detail_bekostiging", pl.DataFrame())
    if detail.is_empty():
        return pl.DataFrame()
    drop = [c for c in _BEKOSTIGING_DROP if c in detail.columns]
    return detail.drop(drop)


def _build_fact_bekostiging_diploma(
    tables: dict[str, pl.DataFrame],
) -> pl.DataFrame:
    """fact_bekostiging_diploma: TBGI diplomawaarde-bijdragen per inschrijving.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, Resultaatvolgnummer).
    Joinbaar met fact_inschrijving via _inschrijving_periode_id.
    BSN en Onderwijsnummer worden verwijderd.
    """
    detail = tables.get("detail_bekostiging_diploma", pl.DataFrame())
    if detail.is_empty():
        return pl.DataFrame()
    drop = [c for c in _BEKOSTIGING_DROP if c in detail.columns]
    return detail.drop(drop)


def _build_fact_geo(tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """fact_geo: GEO-examenresultaten in long format.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, CodeGeneriekExamenonderdeel).
    Stabiel schema ongeacht welke codes aanwezig zijn in de data.
    Behoudt DatumResultaat, VrijstellingIE/CE die in de pivot verloren gaan.
    Persoonsidentificerende gegevens (BSN, ONr) worden verwijderd.
    """
    detail = tables.get("detail_geo", pl.DataFrame())
    if detail.is_empty():
        return pl.DataFrame()
    drop = [c for c in _PII_DROP if c in detail.columns]
    return detail.drop(drop)


# ---------------------------------------------------------------------------
# Interne helpers
# ---------------------------------------------------------------------------


def _build_dim_instelling(tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Eén rij per BRIN uit álle analysetabellen, verrijkt via ``brinnummer.csv``.

    Niet alleen uit ``inschrijvingen``: in de ISP-route tellen TBGI-inschrijvingen
    daar niet mee, dus een BRIN die alleen in de bekostiging staat zou ontbreken.
    """
    brins = [t.select("BRIN") for t in tables.values() if "BRIN" in t.columns]
    if not brins:
        return pl.DataFrame()
    unieke = (
        pl.concat(brins, how="vertical_relaxed")
        .filter(pl.col("BRIN").is_not_null() & (pl.col("BRIN") != ""))
        .unique()
        .sort("BRIN")
    )
    verrijkt = verrijk_instelling(unieke)
    return verrijkt.select([c for c in _DIM_INSTELLING_COLS if c in verrijkt.columns])


def _build_dim(
    df: pl.DataFrame,
    cols: list[str],
    key: str,
) -> pl.DataFrame:
    """Bouw een dimensietabel: één rij per key, per veld de eerste niet-lege waarde.

    Coalesceert per kolom over de leveringen van dezelfde key, zodat een veld dat
    alleen in de ene levering staat (bijv. ``Geboortedatum`` uit RO) niet verloren
    gaat wanneer een andere levering (bijv. GRONDSLAG) meer velden vult. De rijen
    worden op vulling gesorteerd zodat de meest complete levering vooropstaat en
    ontbrekende velden uit de overige leveringen worden aangevuld.
    """
    beschikbaar = [c for c in cols if c in df.columns]
    if key not in beschikbaar:
        return pl.DataFrame()
    subset = df.select(beschikbaar)
    non_key = [c for c in beschikbaar if c != key]
    if not non_key:
        return subset.unique(subset=[key], keep="first", maintain_order=True)

    subset = subset.with_columns(
        pl.sum_horizontal([pl.col(c).is_not_null() for c in non_key]).alias("_vulling")
    ).sort("_vulling", descending=True)
    return (
        subset.group_by(key, maintain_order=True)
        .agg([pl.col(c).drop_nulls().first().alias(c) for c in non_key])
        .select(beschikbaar)
        .sort(key)
    )
