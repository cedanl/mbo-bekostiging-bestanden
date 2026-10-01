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


def voldoet_aan_domein(waarde: pl.Expr, naam: str) -> pl.Expr:
    """Strikt: gevuld en binnen het domein, of leeg bij een ``leeg``-domein.

    Voor de layoutherkenning (#236, #321): anders dan bij
    :func:`controleer_waardedomeinen` telt een lege waarde hier als niet passend,
    zodat een verschoven regel niet via een leeg veld toch past.
    """
    domein = waardedomein(naam)
    gevuld = waarde.is_not_null() & (waarde.str.strip_chars() != "")
    if domein.get("leeg"):
        return ~gevuld
    return gevuld & _binnen_domein(waarde, domein)


# Getypeerde velden: een verschoven waarde valt op als parseverlies.
_GETYPEERD = {
    "date_fields": "datum",
    "partial_date_fields": "datum",
    "int_fields": "getal",
    "float_fields": "getal",
}
_RECORDSOORT = "Recordsoort"


def velden_zonder_domein() -> dict[str, str]:
    """Veldnaam → reden waarom het veld bewust geen domein heeft (#288)."""
    return _laad()["geen_domein"]


def _dekking(veld: str, recordschema: dict, redenen: dict[str, str]) -> str | None:
    if veld in recordschema.get("domeinen", {}):
        return f"domein:{recordschema['domeinen'][veld]}"
    for sleutel, soort in _GETYPEERD.items():
        if veld in recordschema.get(sleutel, []):
            return f"type:{soort}"
    if veld == _RECORDSOORT:
        return "recordsoort"
    if veld in redenen:
        return f"reden:{redenen[veld]}"
    return None


def domeindekking(schema_name: str) -> dict[str, dict[str, str | None]]:
    """Per recordtype en veld hoe een verschoven waarde opvalt (#288).

    ``domein:<naam>``, ``type:datum``/``type:getal`` (parseverlies),
    ``recordsoort`` (de ingest splitst erop) of ``reden:<tekst>`` uit
    ``[geen_domein]``; ``None`` als niets het veld dekt.
    """
    redenen = velden_zonder_domein()
    return {
        rt: {
            veld: _dekking(veld, recordschema, redenen)
            for veld in recordschema["fields"]
        }
        for rt, recordschema in load_schema(schema_name).items()
    }


def dekkingsoverzicht(schema_name: str) -> dict[str, int]:
    """Aantal schemavelden per soort dekking, voor ``quality.json`` (#288).

    ``geen`` telt de velden waar een verschoven waarde niet opvalt; voor RO en
    GRONDSLAG is dat 0 (tests/test_domeindekking.py).
    """
    aantallen = dict.fromkeys(("domein", "type", "recordsoort", "reden", "geen"), 0)
    for velden in domeindekking(schema_name).values():
        for dekking in velden.values():
            aantallen[dekking.split(":")[0] if dekking else "geen"] += 1
    return aantallen


def _buiten_geldigheid(
    waarde: pl.Expr, peildatum: pl.Expr, geldigheid: dict
) -> tuple[pl.Expr, pl.Expr]:
    """``(buiten, zonder_peildatum)`` voor waarden met een periode (#325).

    ``vanaf`` en ``tot`` zijn inclusief (PvE §16.6: "tot en met"). Zonder
    peildatum is een tijdgebonden waarde niet te toetsen; die telt apart.
    """
    genormaliseerd = _normaliseer(waarde)
    buiten = pl.lit(False)
    tijdgebonden = pl.lit(False)
    for code, periode in geldigheid.items():
        is_code = genormaliseerd == code
        tijdgebonden = tijdgebonden | is_code
        if "vanaf" in periode:
            buiten = buiten | (is_code & (peildatum < periode["vanaf"]))
        if "tot" in periode:
            buiten = buiten | (is_code & (peildatum > periode["tot"]))
    return buiten.fill_null(False), tijdgebonden & peildatum.is_null()


def _tel_afwijkingen(
    df: pl.DataFrame, veld: str, domein: dict, peildatum: pl.Series | None
) -> dict[str, int]:
    """Aantallen per soort afwijking van één veld; alleen niet-nul."""
    waarde = pl.col(veld).cast(pl.Utf8)
    gevuld = waarde.is_not_null() & (waarde.str.strip_chars() != "")
    tellingen = {
        "buiten": gevuld & ~_binnen_domein(waarde, domein),
        "leeg": ~gevuld if domein.get("verplicht") else pl.lit(False),
    }
    if domein.get("geldigheid") and peildatum is not None:
        df = df.with_columns(peildatum.alias("_peildatum"))
        buiten_periode, zonder = _buiten_geldigheid(
            waarde, pl.col("_peildatum"), domein["geldigheid"]
        )
        tellingen["buiten_geldigheid"] = gevuld & buiten_periode
        tellingen["zonder_peildatum"] = gevuld & zonder
    rij = df.select(expr.sum().alias(soort) for soort, expr in tellingen.items())
    return {soort: n for soort, n in rij.row(0, named=True).items() if n}


def controleer_waardedomeinen(
    frames: dict[str, pl.DataFrame],
    schema_name: str,
    getypeerd: dict[str, pl.DataFrame] | None = None,
) -> dict[str, dict[str, dict[str, int | str]]]:
    """Tel per recordtype en veld de waarden buiten het domein.

    Args:
        frames:      Ruwe (tekst)frames per recordtype.
        schema_name: Schema met per recordtype ``domeinen = {veld = "domein"}``.
        getypeerd:   Gedecodeerde frames met dezelfde rijvolgorde; nodig voor de
                     tijdstoets op de ``peildatum`` van het recordtype (#325).

    Returns:
        Recordtype → veld → ``{"aantal": .., "ernst": ..}``; alleen niet-nul.
        ``ernst`` komt uit ``domein.<naam>.ernst`` in ``waardenlijsten.toml``
        (``"error"`` voor structurele velden zoals BRIN en Studiejaar,
        anders ``"warning"``, #238). Bij een domein met ``verplicht = true``
        telt een lege waarde ook mee in ``aantal`` en staat het aantal lege
        waarden apart in ``leeg`` (#320); anders tellen lege waarden niet.
        Een waarde buiten haar ``geldigheid`` op de peildatum staat apart in
        ``buiten_geldigheid`` en ``zonder_peildatum`` telt de tijdgebonden
        waarden die niet te toetsen waren; beide tellen niet mee in ``aantal``
        en geven alleen een ``warning`` (#360).
    """
    schema = load_schema(schema_name)
    domeinen = _laad()["domein"]
    afwijkingen: dict[str, dict[str, dict[str, int | str]]] = {}
    for rt, df in frames.items():
        spec = schema.get(rt, {})
        peildatum = (
            (getypeerd or {})
            .get(rt, pl.DataFrame())
            .get_column(spec.get("peildatum", ""), default=None)
        )
        for veld, naam in spec.get("domeinen", {}).items():
            if veld not in df.columns:
                continue
            domein = domeinen[naam]
            tellingen = _tel_afwijkingen(df, veld, domein, peildatum)
            if not tellingen:
                continue
            aantal = tellingen.pop("buiten", 0) + tellingen.get("leeg", 0)
            # Zonder echte domeinschending is de waarde hooguit historisch of
            # niet toetsbaar (#360): nooit een error, ook niet bij een
            # verplicht veld.
            afwijking: dict[str, int | str] = {
                "aantal": aantal,
                "ernst": domein.get("ernst", ernst.WARNING)
                if aantal
                else ernst.WARNING,
            }
            afwijkingen.setdefault(rt, {})[veld] = afwijking | tellingen
    return afwijkingen
