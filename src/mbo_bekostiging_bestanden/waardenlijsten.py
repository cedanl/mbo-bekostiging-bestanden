"""Gecodeerde veldwaarden en waardedomeinen uit ``metadata/waardenlijsten.toml``.

Waarden worden exact gematcht na normalisatie (trim, hoofdletters, enkele
spaties). Een substring-match is onbruikbaar: ``NIET BEHAALD`` bevat
``BEHAALD`` (#204). Een waarde buiten de lijst wordt ``null``, nooit stil
``True`` of ``False``.

Waardedomeinen (#205) koppelen een veld aan een patroon of lijst; waarden
daarbuiten wijzen vaak op een verschoven veldindeling en worden geteld.
"""

import functools
import tomllib
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden import ernst
from mbo_bekostiging_bestanden.metadata import load_schema

_WAARDENLIJSTEN = Path(__file__).parent / "metadata" / "waardenlijsten.toml"


@functools.cache
def _laad() -> dict[str, dict]:
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


def indicatie_bekostigbaar(waarde: pl.Expr) -> pl.Expr:
    """``"J"``/``"N"`` voor elke bronnotatie; een onbekende waarde blijft staan."""
    lijst = _laad()["indicatie_bekostigbaar"]
    genormaliseerd = _normaliseer(waarde)
    return (
        pl.when(genormaliseerd.is_in(lijst["ja"]))
        .then(pl.lit("J"))
        .when(genormaliseerd.is_in(lijst["nee"]))
        .then(pl.lit("N"))
        .otherwise(waarde)
    )


def waardedomein(naam: str) -> dict:
    """Definitie van ``[domein.<naam>]`` uit ``waardenlijsten.toml``."""
    return _laad()["domein"][naam]


def leertrajecten_buiten_indicatorpopulatie() -> list[str]:
    """Bijlage 3 van de toelichting onderwijsresultaten (#286)."""
    return waardedomein("leertraject")["buiten_indicatorpopulatie"]


def _binnen_domein(waarde: pl.Expr, domein: dict) -> pl.Expr:
    if domein.get("leeg"):
        return pl.lit(False)
    if "patroon" in domein:
        return waarde.str.strip_chars().str.contains(domein["patroon"])
    waarden = domein.get("waarden") or [
        w for lijst in _laad()[domein["waardenlijst"]].values() for w in lijst
    ]
    return _normaliseer(waarde).is_in(waarden)


def controleer_waardedomeinen(
    frames: dict[str, pl.DataFrame], schema_name: str
) -> dict[str, dict[str, dict[str, int | str]]]:
    """Tel per recordtype en veld de waarden buiten het domein.

    Args:
        frames:      Ruwe (tekst)frames per recordtype.
        schema_name: Schema met per recordtype ``domeinen = {veld = "domein"}``.

    Returns:
        Recordtype → veld → ``{"aantal": .., "ernst": ..}``; alleen niet-nul.
        ``ernst`` komt uit ``domein.<naam>.ernst`` in ``waardenlijsten.toml``
        (``"error"`` voor structurele velden zoals BRIN en Studiejaar,
        anders ``"warning"``, #238). Bij een domein met ``verplicht = true``
        telt een lege waarde ook mee in ``aantal`` en staat het aantal lege
        waarden apart in ``leeg`` (#320); anders tellen lege waarden niet.
    """
    schema = load_schema(schema_name)
    domeinen = _laad()["domein"]
    afwijkingen: dict[str, dict[str, dict[str, int | str]]] = {}
    for rt, df in frames.items():
        for veld, naam in schema.get(rt, {}).get("domeinen", {}).items():
            if veld not in df.columns:
                continue
            domein = domeinen[naam]
            waarde = pl.col(veld).cast(pl.Utf8)
            gevuld = waarde.is_not_null() & (waarde.str.strip_chars() != "")
            buiten, leeg = df.select(
                (gevuld & ~_binnen_domein(waarde, domein)).sum().alias("buiten"),
                (~gevuld).sum().alias("leeg")
                if domein.get("verplicht")
                else pl.lit(0).alias("leeg"),
            ).row(0)
            if buiten or leeg:
                afwijking: dict[str, int | str] = {
                    "aantal": buiten + leeg,
                    "ernst": domein.get("ernst", ernst.WARNING),
                }
                if leeg:
                    afwijking["leeg"] = leeg
                afwijkingen.setdefault(rt, {})[veld] = afwijking
    return afwijkingen
