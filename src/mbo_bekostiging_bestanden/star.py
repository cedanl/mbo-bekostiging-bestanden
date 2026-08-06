"""Dimensionaal model (star schema) afgeleid van de OBT-tabellen.

Splitst ``obt_inschrijvingen`` in drie dimensietabellen en één feitstabel,
en promoveert de detail-tabellen (BPV, KZD, AMO, GEO, bekostiging) naar
expliciete feittabellen met een stabiel schema.

Publieke API:
    build_star(obt_tables) -> dict[str, pl.DataFrame]
"""

from __future__ import annotations

import re

import polars as pl

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

# GEO-pivotkolommen in obt_inschrijvingen (GEO_{code}_{veld}).
# Deze zijn schema-instabiel en worden vervangen door fact_geo.
_GEO_COL_RE = re.compile(r"^GEO_\d+_")

# Kolommen die persoonsidentificerende gegevens bevatten en niet in het
# star schema horen (BSN is al gehasht naar _persoon_id; Onderwijsnummer
# is directe identifier).
_BEKOSTIGING_DROP = {"Burgerservicenummer", "Onderwijsnummer", "_bron"}


# ---------------------------------------------------------------------------
# Publieke API
# ---------------------------------------------------------------------------


def build_star(
    obt_tables: dict[str, pl.DataFrame],
) -> dict[str, pl.DataFrame]:
    """Bouw het star schema vanuit de OBT-tabellen.

    Args:
        obt_tables: Dict zoals geretourneerd door ``build_obt``.  Verwacht
            minimaal de sleutel ``obt_inschrijvingen``; optioneel ook
            ``detail_bpv``, ``detail_kzd_amo``, ``detail_geo``,
            ``detail_bekostiging``.

    Returns:
        Dict met negen sleutels:

        Dimensies:
          ``dim_deelnemer``     — uniek per ``_persoon_id``
          ``dim_opleiding``     — uniek per ``Opleidingcode``
          ``dim_instelling``    — uniek per ``BRIN``

        Feiten:
          ``fact_inschrijving`` — ISP-grain, FK's + vlaggen, zonder GEO-pivot
          ``fact_bpv``          — BPV-periodes per inschrijving
          ``fact_kzd``          — Keuzedelen per inschrijving
          ``fact_amo``          — AMO-onderdelen per inschrijving
          ``fact_geo``          — GEO-examenresultaten in long format
          ``fact_bekostiging``  — TBGI bekostigingsgrondslagen per inschrijving
    """
    obt = obt_tables["obt_inschrijvingen"]

    dim_deelnemer = _build_dim(obt, _DIM_DEELNEMER_COLS, "_persoon_id")
    dim_opleiding = _build_dim(obt, _DIM_OPLEIDING_COLS, "Opleidingcode")
    dim_instelling = _build_dim(obt, _DIM_INSTELLING_COLS, "BRIN")

    dim_col_set = (
        set(_DIM_DEELNEMER_COLS) | set(_DIM_OPLEIDING_COLS) | set(_DIM_INSTELLING_COLS)
    ) - _FK_COLS

    # GEO-pivotkolommen verwijderen: schema-instabiel en nu in fact_geo.
    geo_cols = {c for c in obt.columns if _GEO_COL_RE.match(c)}

    fact_cols = [c for c in obt.columns if c not in dim_col_set and c not in geo_cols]
    fact_inschrijving = obt.select(fact_cols)

    return {
        "dim_deelnemer": dim_deelnemer,
        "dim_opleiding": dim_opleiding,
        "dim_instelling": dim_instelling,
        "fact_inschrijving": fact_inschrijving,
        "fact_bpv": _build_fact_bpv(obt_tables),
        "fact_kzd": _build_fact_kzd(obt_tables),
        "fact_amo": _build_fact_amo(obt_tables),
        "fact_geo": _build_fact_geo(obt_tables),
        "fact_bekostiging": _build_fact_bekostiging(obt_tables),
    }


# ---------------------------------------------------------------------------
# Feittabel-builders
# ---------------------------------------------------------------------------


def _build_fact_bpv(obt_tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """fact_bpv: BPV-periodes per inschrijving.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, Volgnummer).
    Joinbaar met fact_inschrijving via de eerste drie sleutelkolommen.
    """
    return obt_tables.get("detail_bpv", pl.DataFrame())


def _build_fact_kzd(obt_tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """fact_kzd: Keuzedelen per inschrijving.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, Resultaatvolgnummer).
    """
    detail = obt_tables.get("detail_kzd_amo", pl.DataFrame())
    if detail.is_empty() or "_bron" not in detail.columns:
        return pl.DataFrame()
    return detail.filter(pl.col("_bron") == "KZD").drop("_bron")


def _build_fact_amo(obt_tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """fact_amo: AMO-onderdelen per inschrijving.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, Resultaatvolgnummer).
    """
    detail = obt_tables.get("detail_kzd_amo", pl.DataFrame())
    if detail.is_empty() or "_bron" not in detail.columns:
        return pl.DataFrame()
    return detail.filter(pl.col("_bron") == "AMO").drop("_bron")


def _build_fact_bekostiging(obt_tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """fact_bekostiging: TBGI bekostigingsgrondslagen per inschrijving.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, Teldatum).
    Joinbaar met fact_inschrijving via de eerste drie sleutelkolommen en met
    dim_instelling via BRIN.  BSN en Onderwijsnummer worden verwijderd.
    """
    detail = obt_tables.get("detail_bekostiging", pl.DataFrame())
    if detail.is_empty():
        return pl.DataFrame()
    drop = [c for c in _BEKOSTIGING_DROP if c in detail.columns]
    return detail.drop(drop)


def _build_fact_geo(obt_tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """fact_geo: GEO-examenresultaten in long format.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, CodeGeneriekExamenonderdeel).
    Stabiel schema ongeacht welke codes aanwezig zijn in de data.
    Behoudt DatumResultaat, VrijstellingIE/CE die in de OBT-pivot verloren gaan.
    """
    return obt_tables.get("detail_geo", pl.DataFrame())


# ---------------------------------------------------------------------------
# Interne helpers
# ---------------------------------------------------------------------------


def _build_dim(
    obt: pl.DataFrame,
    cols: list[str],
    key: str,
) -> pl.DataFrame:
    """Bouw een dimensietabel: selecteer kolommen, houd de meest complete rij."""
    beschikbaar = [c for c in cols if c in obt.columns]
    if key not in beschikbaar:
        return pl.DataFrame()
    subset = obt.select(beschikbaar)
    non_key = [c for c in beschikbaar if c != key]
    if non_key:
        subset = subset.with_columns(
            pl.sum_horizontal([pl.col(c).is_not_null() for c in non_key]).alias(
                "_vulling"
            ),
        )
        subset = subset.sort("_vulling", descending=True)
        subset = subset.unique(subset=[key], keep="first", maintain_order=False)
        subset = subset.drop("_vulling").sort(key)
    else:
        subset = subset.unique(subset=[key], keep="first", maintain_order=True)
    return subset
