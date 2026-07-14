"""Verrijking van obt_inschrijvingen met leesbare labels uit decodeertabellen.

Publieke API:
    enrich_obt(obt_inschrijvingen) -> pl.DataFrame

Voegt leesbare namen en migratieachtergronden toe via LEFT JOINs op de CSV-
bestanden in de ``metadata/``-map naast dit bestand.  Alle lookups worden
lazily ingeladen en per processlevensduur gecached.
"""

from __future__ import annotations

import functools
from pathlib import Path

import polars as pl

_METADATA = Path(__file__).parent / "metadata"


# ---------------------------------------------------------------------------
# Lazy-loaded lookups
# ---------------------------------------------------------------------------


@functools.cache
def _laad_nationaliteitscode() -> pl.DataFrame:
    return pl.read_csv(
        _METADATA / "nationaliteitscode.csv",
        infer_schema_length=0,
    ).select(["code", "omschrijving", "migratieachtergrond_ln"])


@functools.cache
def _laad_landcode() -> pl.DataFrame:
    return pl.read_csv(
        _METADATA / "landcode.csv",
        infer_schema_length=0,
    ).select(["code", "naam_land", "migratieachtergrond_ln"])


@functools.cache
def _laad_postcodecijfers() -> pl.DataFrame:
    return pl.read_csv(
        _METADATA / "postcodecijfers.csv",
        infer_schema_length=0,
    ).select(["postcode", "gemeentecode", "gemeentenaam"])


@functools.cache
def _laad_brinnummer() -> pl.DataFrame:
    return pl.read_csv(
        _METADATA / "brinnummer.csv",
        infer_schema_length=0,
    ).select(["brin", "naam", "plaats"])


# ---------------------------------------------------------------------------
# Interne join-helpers
# ---------------------------------------------------------------------------


def _join_nationaliteit(
    df: pl.DataFrame,
    src_col: str,
) -> pl.DataFrame:
    """Voeg naam en migratieachtergrond toe voor één nationaliteitskolom."""
    if src_col not in df.columns:
        return df
    lookup = _laad_nationaliteitscode().rename({
        "code": src_col,
        "omschrijving": f"{src_col}_naam",
        "migratieachtergrond_ln": f"{src_col}_migratieachtergrond",
    })
    right = lookup.unique(subset=[src_col], keep="first", maintain_order=True)
    return df.join(right, on=src_col, how="left")


def _join_landcode(
    df: pl.DataFrame,
    src_col: str,
) -> pl.DataFrame:
    """Voeg naam en migratieachtergrond toe voor één geboortelandkolom."""
    if src_col not in df.columns:
        return df
    lookup = _laad_landcode().rename({
        "code": src_col,
        "naam_land": f"{src_col}_naam",
        "migratieachtergrond_ln": f"{src_col}_migratieachtergrond",
    })
    right = lookup.unique(subset=[src_col], keep="first", maintain_order=True)
    return df.join(right, on=src_col, how="left")


# ---------------------------------------------------------------------------
# Publieke API
# ---------------------------------------------------------------------------


def enrich_obt(obt_inschrijvingen: pl.DataFrame) -> pl.DataFrame:
    """Verrijk ``obt_inschrijvingen`` met leesbare labels uit decodeertabellen.

    Toegevoegde kolommen (alleen als de bronkolom aanwezig is):

    Nationaliteit:
        ``Nationaliteit1_naam``, ``Nationaliteit1_migratieachtergrond``
        ``Nationaliteit2_naam``, ``Nationaliteit2_migratieachtergrond``

    Geboorteland:
        ``CodeGeboorteland_naam``, ``CodeGeboorteland_migratieachtergrond``

    Postcode → gemeente:
        ``Gemeente``, ``Gemeentecode``

    BRIN → instelling:
        ``Instelling_naam``, ``Instelling_plaats``

    Args:
        obt_inschrijvingen: Resultaat van ``_bouw_obt_inschrijvingen`` of
            ``_bouw_tbgi_inschrijvingen`` uit ``obt.py``.

    Returns:
        Verrijkte DataFrame; originele kolommen blijven onaangepast.
    """
    df = obt_inschrijvingen

    # ── Nationaliteit ────────────────────────────────────────────────────────
    df = _join_nationaliteit(df, "Nationaliteit1")
    df = _join_nationaliteit(df, "Nationaliteit2")

    # ── Geboorteland ─────────────────────────────────────────────────────────
    df = _join_landcode(df, "CodeGeboorteland")

    # ── Postcode → gemeente ──────────────────────────────────────────────────
    if "Postcodecijfers" in df.columns:
        postcode_lookup = (
            _laad_postcodecijfers()
            .rename({
                "postcode": "Postcodecijfers",
                "gemeentenaam": "Gemeente",
                "gemeentecode": "Gemeentecode",
            })
            .unique(subset=["Postcodecijfers"], keep="first", maintain_order=True)
        )
        df = df.join(postcode_lookup, on="Postcodecijfers", how="left")

    # ── BRIN → instelling ────────────────────────────────────────────────────
    if "BRIN" in df.columns:
        brin_lookup = (
            _laad_brinnummer()
            .rename({
                "brin": "BRIN",
                "naam": "Instelling_naam",
                "plaats": "Instelling_plaats",
            })
            .unique(subset=["BRIN"], keep="first", maintain_order=True)
        )
        df = df.join(brin_lookup, on="BRIN", how="left")

    return df
