"""Dimensionaal model (star schema) afgeleid van de OBT.

Splitst ``obt_inschrijvingen`` in drie dimensietabellen en één feitstabel.
Het referentiemodel is het QlikView Resultatenbox-schema (zie
``ondersteunend-materiaal/``).

Publieke API:
    build_star(obt_tables) -> dict[str, pl.DataFrame]
"""

from __future__ import annotations

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
    "Opleiding_dossier",
    "Opleiding_sectorkamer",
]

_DIM_INSTELLING_COLS = [
    "BRIN",
    "Instelling_naam",
    "Instelling_plaats",
]

# Kolommen die naar een dimensie verhuizen en dus uit de fact verdwijnen.
# Foreign keys (_persoon_id, Opleidingcode, BRIN) blijven wél in de fact.
_FK_COLS = {"_persoon_id", "Opleidingcode", "BRIN"}


# ---------------------------------------------------------------------------
# Publieke API
# ---------------------------------------------------------------------------


def build_star(
    obt_tables: dict[str, pl.DataFrame],
) -> dict[str, pl.DataFrame]:
    """Splits de OBT in een star schema.

    Args:
        obt_tables: Dict zoals geretourneerd door ``build_obt``.  Verwacht
            minimaal de sleutel ``obt_inschrijvingen``.

    Returns:
        Dict met:
          ``dim_deelnemer``    — uniek per ``_persoon_id``
          ``dim_opleiding``   — uniek per ``Opleidingcode``
          ``dim_instelling``  — uniek per ``BRIN``
          ``fact_inschrijving`` — ISP-grain feiten, vlaggen en FK's
    """
    obt = obt_tables["obt_inschrijvingen"]

    dim_deelnemer = _build_dim(obt, _DIM_DEELNEMER_COLS, "_persoon_id")
    dim_opleiding = _build_dim(obt, _DIM_OPLEIDING_COLS, "Opleidingcode")
    dim_instelling = _build_dim(obt, _DIM_INSTELLING_COLS, "BRIN")

    dim_col_set = (
        set(_DIM_DEELNEMER_COLS)
        | set(_DIM_OPLEIDING_COLS)
        | set(_DIM_INSTELLING_COLS)
    ) - _FK_COLS
    fact_cols = [c for c in obt.columns if c not in dim_col_set]
    fact_inschrijving = obt.select(fact_cols)

    return {
        "dim_deelnemer": dim_deelnemer,
        "dim_opleiding": dim_opleiding,
        "dim_instelling": dim_instelling,
        "fact_inschrijving": fact_inschrijving,
    }


# ---------------------------------------------------------------------------
# Interne helpers
# ---------------------------------------------------------------------------


def _build_dim(
    obt: pl.DataFrame,
    cols: list[str],
    key: str,
) -> pl.DataFrame:
    """Bouw een dimensietabel: selecteer kolommen, dedupliceer op key."""
    beschikbaar = [c for c in cols if c in obt.columns]
    if key not in beschikbaar:
        return pl.DataFrame()
    return obt.select(beschikbaar).unique(
        subset=[key], keep="first", maintain_order=True
    )
