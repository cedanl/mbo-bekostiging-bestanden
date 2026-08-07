"""Verrijking van inschrijvingen met leesbare labels uit decodeertabellen.

Publieke API:
    enrich_inschrijvingen(df) -> pl.DataFrame

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


@functools.cache
def _laad_crebo() -> pl.DataFrame:
    return pl.read_csv(
        _METADATA / "crebo.csv",
        infer_schema_length=0,
    ).select([
        "code", "naam", "leerweg",
        "hoofdgroep_naam", "subgroep_naam",
        "dossier_code", "dossier_naam", "sectorkamer_naam",
    ])


@functools.cache
def _laad_sbb_koppeltabel() -> pl.DataFrame:
    return pl.read_parquet(_METADATA / "sbb_koppeltabel.parquet").select([
        "opleidingscode", "beroepsnaam", "niveau",
        "opvolger_kwalificatie", "eerste_schooljaar", "laatste_schooljaar",
    ])


@functools.cache
def _laad_sbb_crebolijst() -> pl.DataFrame:
    return pl.read_parquet(_METADATA / "sbb_crebolijst.parquet").select([
        "kwalificatiecode", "geldig_van", "geldig_tot",
        "prijsfactor", "soort_opleiding",
    ])


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


def enrich_inschrijvingen(df: pl.DataFrame) -> pl.DataFrame:
    """Verrijk inschrijvingen met leesbare labels uit decodeertabellen.

    Toegevoegde kolommen (alleen als de bronkolom aanwezig is):

    Nationaliteit:
        ``Nationaliteit1_naam``, ``Nationaliteit1_migratieachtergrond``
        ``Nationaliteit2_naam``, ``Nationaliteit2_migratieachtergrond``

    Geboorteland:
        ``CodeGeboorteland_naam``, ``CodeGeboorteland_migratieachtergrond``

    Postcode → gemeente:
        ``Gemeente``, ``Gemeentecode``

    Opleidingcode → CREBO (DUO erkende-opleidingstabel):
        ``Opleiding_naam``, ``Opleiding_leerweg``,
        ``Opleiding_domein``, ``Opleiding_subgroep``,
        ``Opleiding_dossiercode``, ``Opleiding_dossier``, ``Opleiding_sectorkamer``

    Opleidingcode → S-BB koppeltabel (Groep 19):
        ``Opleiding_beroep``, ``Opleiding_niveau``,
        ``Opleiding_opvolger``,
        ``Opleiding_eerste_schooljaar``, ``Opleiding_laatste_schooljaar``

    Opleidingcode → S-BB crebolijst (Groep 14, officiële geldigheidsperioden):
        ``Opleiding_geldig_van``, ``Opleiding_geldig_tot``,
        ``Opleiding_prijsfactor``, ``Opleiding_soort_opleiding``

    BRIN → instelling:
        ``Instelling_naam``, ``Instelling_plaats``

    Args:
        df: Resultaat van ``_bouw_obt_inschrijvingen`` of
            ``_bouw_tbgi_inschrijvingen`` uit ``transform.py``.

    Returns:
        Verrijkte DataFrame; originele kolommen blijven onaangepast.
    """

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

    # ── Opleidingcode → CREBO-verrijking ────────────────────────────────────
    if "Opleidingcode" in df.columns:
        crebo_lookup = (
            _laad_crebo()
            .rename({
                "code": "Opleidingcode",
                "naam": "Opleiding_naam",
                "leerweg": "Opleiding_leerweg",
                "hoofdgroep_naam": "Opleiding_domein",
                "subgroep_naam": "Opleiding_subgroep",
                "dossier_code": "Opleiding_dossiercode",
                "dossier_naam": "Opleiding_dossier",
                "sectorkamer_naam": "Opleiding_sectorkamer",
            })
            .unique(subset=["Opleidingcode"], keep="first", maintain_order=True)
        )
        df = df.join(crebo_lookup, on="Opleidingcode", how="left")

        koppel_lookup = (
            _laad_sbb_koppeltabel()
            .rename({
                "opleidingscode": "Opleidingcode_i64",
                "beroepsnaam": "Opleiding_beroep",
                "niveau": "Opleiding_niveau",
                "opvolger_kwalificatie": "Opleiding_opvolger",
                "eerste_schooljaar": "Opleiding_eerste_schooljaar",
                "laatste_schooljaar": "Opleiding_laatste_schooljaar",
            })
        )
        df = (
            df.with_columns(
                pl.col("Opleidingcode")
                .cast(pl.Int64, strict=False)
                .alias("Opleidingcode_i64")
            )
            .join(koppel_lookup, on="Opleidingcode_i64", how="left")
            .drop("Opleidingcode_i64")
        )

        crebolijst_lookup = (
            _laad_sbb_crebolijst()
            .rename({
                "kwalificatiecode": "Opleidingcode",
                "geldig_van": "Opleiding_geldig_van",
                "geldig_tot": "Opleiding_geldig_tot",
                "prijsfactor": "Opleiding_prijsfactor",
                "soort_opleiding": "Opleiding_soort_opleiding",
            })
            .unique(subset=["Opleidingcode"], keep="first", maintain_order=True)
        )
        df = df.join(crebolijst_lookup, on="Opleidingcode", how="left")

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
