"""Interpretatie van gecodeerde veldwaarden via ``metadata/waardenlijsten.toml``.

Waarden worden exact gematcht na normalisatie (trim, hoofdletters, enkele
spaties). Een substring-match is onbruikbaar: ``NIET BEHAALD`` bevat
``BEHAALD`` (#204). Een waarde buiten de lijst wordt ``null``, nooit stil
``True`` of ``False``.
"""

import functools
import tomllib
from pathlib import Path

import polars as pl

_WAARDENLIJSTEN = Path(__file__).parent / "metadata" / "waardenlijsten.toml"


@functools.cache
def _laad() -> dict[str, dict[str, list[str]]]:
    with _WAARDENLIJSTEN.open("rb") as f:
        return tomllib.load(f)


def _normaliseer(expr: pl.Expr) -> pl.Expr:
    return expr.str.strip_chars().str.to_uppercase().str.replace_all(r"\s+", " ")


def kzd_behaald(resultaat: pl.Expr) -> pl.Expr:
    """``True``/``False`` voor een bekend KZD-resultaat, anders ``null``."""
    lijst = _laad()["kzd_resultaat"]
    waarde = _normaliseer(resultaat)
    return (
        pl.when(waarde.is_in(lijst["behaald"]))
        .then(True)
        .when(waarde.is_in(lijst["niet_behaald"]))
        .then(False)
        .otherwise(None)
    )
