"""Persoonsidentiteit: ``_persoon_id`` als pseudoniem van een persoons-identifier.

HMAC-SHA256 met een geheime salt (fail-closed: zonder salt geen pseudoniem).
Het identifierdomein gaat mee in het pseudoniem, zodat een PGN, BSN of ONr met
dezelfde cijfers nooit als dezelfde persoon koppelt.

De privacygrens ligt bij decode (#173): :func:`pseudonimiseer` vervangt de
identifiers, zodat ze de brondata (``02-prepared``) niet bereiken.
"""

import functools
import hashlib
import hmac
import os
import tomllib
from pathlib import Path

import polars as pl

_SALT_ENV = "MBO_PSEUDONIMISERING_SALT"
_DEMO_CONFIG = Path(__file__).parents[2] / "app" / "config.toml"

# Persoonsidentificerende kolommen (prioriteitsvolgorde) → identifierdomein.
# GRONDSLAG levert een omgenummerd PGN, geen BSN (PvE 4.8.2 §17.1), dus gelijke
# cijfers zijn niet dezelfde persoon.
PERSOON_DOMEIN = {
    "PseudoNummer": "PGN",
    "Burgerservicenummer": "BSN",
    "Onderwijsnummer": "ONR",
}
PERSOON_COLS = list(PERSOON_DOMEIN)
PERSOON_ID = "_persoon_id"


@functools.cache
def laad_pseudonimisering_salt() -> str:
    """Salt uit de env-var (productie), anders uit ``app/config.toml`` (demo).

    Raises:
        ValueError: als geen salt beschikbaar is.
    """
    env_salt = os.environ.get(_SALT_ENV)
    if env_salt:
        return env_salt

    if _DEMO_CONFIG.exists():
        with open(_DEMO_CONFIG, "rb") as f:
            config = tomllib.load(f)
        salt = config.get("security", {}).get("pseudonimisering_salt")
        if salt:
            return salt

    raise ValueError(
        "Geen pseudonimisering_salt beschikbaar. "
        f"Zet {_SALT_ENV} env-var of voeg toe aan app/config.toml"
    )


def pseudoniem(domein: str, identifier: str) -> str:
    """Pseudoniem van een identifier binnen zijn domein (PGN/BSN/ONR)."""
    salt = laad_pseudonimisering_salt()
    msg = f"{salt}:{domein}:{identifier}".encode()
    return hmac.new(salt.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def pseudonimiseer(df: pl.DataFrame) -> pl.DataFrame:
    """Vervang de identifierkolommen door ``_persoon_id`` op de plek van de eerste.

    ``_persoon_id`` is :func:`pseudoniem` van de eerste gevulde identifier (in
    de volgorde van :data:`PERSOON_DOMEIN`); een lege string telt als leeg.
    Een frame zonder identifierkolommen blijft ongewijzigd.

    Raises:
        ValueError: zonder salt (:func:`laad_pseudonimisering_salt`).
    """
    beschikbaar = [c for c in PERSOON_COLS if c in df.columns]
    if not beschikbaar:
        return df
    kolommen = verwachte_kolommen(df.columns)
    return _voeg_persoon_id_toe(df, beschikbaar).select(kolommen)


def verwachte_kolommen(kolommen: list[str]) -> list[str]:
    """``kolommen`` na :func:`pseudonimiseer`."""
    eerste = next((k for k in kolommen if k in PERSOON_DOMEIN), None)
    return [
        PERSOON_ID if k == eerste else k
        for k in kolommen
        if k == eerste or k not in PERSOON_DOMEIN
    ]


def _voeg_persoon_id_toe(df: pl.DataFrame, beschikbaar: list[str]) -> pl.DataFrame:
    gevuld = {c: pl.col(c) != "" for c in beschikbaar}
    domein = pl.coalesce(
        pl.when(gevuld[c]).then(pl.lit(PERSOON_DOMEIN[c])) for c in beschikbaar
    )
    identifier = pl.coalesce(pl.when(gevuld[c]).then(pl.col(c)) for c in beschikbaar)
    return df.with_columns(
        pl.struct(domein.alias("domein"), identifier.alias("identifier"))
        .map_elements(
            lambda r: (
                None
                if r["identifier"] is None
                else pseudoniem(r["domein"], r["identifier"])
            ),
            return_dtype=pl.Utf8,
        )
        .alias(PERSOON_ID)
    )
