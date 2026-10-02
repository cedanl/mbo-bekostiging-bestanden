"""Decoderen van velden: strings omzetten naar juiste types via schema-metadata."""

from collections.abc import Callable

import polars as pl

from mbo_bekostiging_bestanden.contracts import PRECISIE_ONBEKEND, PRECISIE_SUFFIX
from mbo_bekostiging_bestanden.identiteit import pseudonimiseer
from mbo_bekostiging_bestanden.metadata import load_schema
from mbo_bekostiging_bestanden.waardenlijsten import indicatie_bekostigbaar

_DECIMAALKOMMA = ","


def _iso_uit_compact(col: pl.Expr) -> pl.Expr:
    """``ccyymmdd`` → ``ccyy-mm-dd``."""
    return col.str.replace(r"^(\d{4})(\d{2})(\d{2})$", "${1}-${2}-${3}")


def _iso_uit_dutch(col: pl.Expr) -> pl.Expr:
    """``d-m-ccyy`` (zonder voorloopnullen) → ``ccyy-mm-dd``."""
    parts = col.str.split("-")
    day = parts.list.get(0, null_on_oob=True).str.zfill(2)
    month = parts.list.get(1, null_on_oob=True).str.zfill(2)
    year = parts.list.get(2, null_on_oob=True)
    return pl.concat_str([year, month, day], separator="-", ignore_nulls=False)


# Datumnotaties in de leveringen, met het patroon dat ze herkent en de omzetting
# naar ISO-tekst. De patronen sluiten elkaar uit, dus de notatie wordt per cel
# bepaald: één afwijkende cel kost alleen zichzelf (#417).
_NOTATIES: tuple[tuple[str, Callable[[pl.Expr], pl.Expr]], ...] = (
    (r"^\d{4}-\d{2}-\d{2}$", lambda col: col),  # ccyy-mm-dd
    (r"^\d{8}$", _iso_uit_compact),  # ccyymmdd
    (r"^\d{1,2}-\d{1,2}-\d{4}$", _iso_uit_dutch),  # d-m-ccyy
)


def _naar_iso(col: pl.Expr) -> pl.Expr:
    """Datumtekst in een van de :data:`_NOTATIES` → ``ccyy-mm-dd``; anders null.

    Een onbekende notatie wordt null en telt zo als parseverlies.
    """
    (patroon, omzetting), *overige = _NOTATIES
    expr = pl.when(col.str.contains(patroon)).then(omzetting(col))
    for patroon, omzetting in overige:
        expr = expr.when(col.str.contains(patroon)).then(omzetting(col))
    return expr.otherwise(None)


# Onbekende dag/maand ("00", PvE §15.5.2) → eerste van de maand/het jaar.
_ONBEKENDE_MAAND = r"-00-00$"
_ONBEKENDE_DAG = r"-00$"
_PRECISIE_DAG, _PRECISIE_MAAND, _PRECISIE_JAAR = "dag", "maand", "jaar"
# Jaar 0 bestaat niet (geen PvE-notatie, Python ``datetime`` kan het niet aan);
# Polars parst het wel, dus het moet expliciet null worden (#391).
_JAAR_NUL = r"^0000-"


def _naar_datum(iso: pl.Expr) -> pl.Expr:
    return (
        pl.when(iso.str.contains(_JAAR_NUL))
        .then(None)
        .otherwise(iso.str.to_date("%Y-%m-%d", strict=False))
    )


def _deels_bekende_datum(iso: pl.Expr) -> tuple[pl.Expr, pl.Expr]:
    """``(datum, precisie)`` voor een ISO-string waarin dag of maand ``00`` mag zijn.

    Jaar ``0000`` geeft een null-datum met precisie ``onbekend``: geen
    parsefout, maar een bewust onbekende waarde die ``quality`` als warning
    telt (:func:`quality.tel_onbekende_datums`).
    """
    aangevuld = iso.str.replace(_ONBEKENDE_MAAND, "-01-01").str.replace(
        _ONBEKENDE_DAG, "-01"
    )
    datum = _naar_datum(aangevuld)
    precisie = (
        pl.when(iso.str.contains(_JAAR_NUL))
        .then(pl.lit(PRECISIE_ONBEKEND))
        .when(datum.is_null())
        .then(None)
        .when(iso.str.contains(_ONBEKENDE_MAAND))
        .then(pl.lit(_PRECISIE_JAAR))
        .when(iso.str.contains(_ONBEKENDE_DAG))
        .then(pl.lit(_PRECISIE_MAAND))
        .otherwise(pl.lit(_PRECISIE_DAG))
    )
    return datum, precisie


def leeg_naar_null(col: pl.Expr) -> pl.Expr:
    """Trim omringende witruimte (#392) en maak een lege waarde null.

    Hier en niet bij ingest, zodat de ruwe levering getrouw blijft tot decode.
    """
    getrimd = col.str.strip_chars()
    return pl.when(getrimd == "").then(None).otherwise(getrimd)


def _to_float_expr(col: pl.Expr) -> pl.Expr:
    """Een komma als decimaalteken (``6,5``) is geldig volgens het PvE en wordt
    eerst genormaliseerd naar een punt (#207).
    """
    return (
        leeg_naar_null(col)
        .str.replace(_DECIMAALKOMMA, ".", literal=True)
        .cast(pl.Float64, strict=False)
    )


def _normaliseer_indicatie_bekostigbaar(df: pl.DataFrame) -> pl.DataFrame:
    """Normaliseer ``IndicatieBekostigbaar`` naar ``"J"``/``"N"``.

    RO gebruikt ``"J"``/``"N"``, GRONDSLAG ``"1"``/``"0"``, TBGI ``"true"``/``"false"``;
    de notaties staan in ``metadata/waardenlijsten.toml``.
    """
    if "IndicatieBekostigbaar" not in df.columns:
        return df
    return df.with_columns(
        indicatie_bekostigbaar(pl.col("IndicatieBekostigbaar")).alias(
            "IndicatieBekostigbaar"
        )
    )


def decode_frames(
    frames: dict[str, pl.DataFrame],
    schema_name: str,
) -> dict[str, pl.DataFrame]:
    """Cast velden naar het juiste type op basis van het opgegeven schema-TOML.

    - Datumvelden worden ``pl.Date`` (null bij lege waarde); de notatie
      (``ccyy-mm-dd``, ``ccyymmdd`` of ``d-m-ccyy``) geldt per cel. Velden in
      ``partial_date_fields`` mogen een onbekende dag/maand (``00``) hebben:
      die wordt de eerste van de maand/het jaar, met ``<veld>_precisie``
      (``dag``/``maand``/``jaar``). Jaar ``0000`` wordt null met precisie
      ``onbekend`` (#391); in een gewoon datumveld is het parseverlies.
    - Integer-velden worden ``pl.Int64``.
    - Float-velden worden ``pl.Float64``; een decimaalkomma wordt geaccepteerd.
    - Alle casts zijn niet-strikt: een ongeldige waarde wordt null en telt als
      parseverlies in ``quality.json`` (zie :func:`quality.tel_parseverlies`),
      een error voor de kwaliteitspoort (#390).
    - ``IndicatieBekostigbaar`` wordt genormaliseerd naar ``"J"``/``"N"``.
    - Persoonsidentifiers (BSN, onderwijsnummer, PGN) worden vervangen door
      het pseudoniem ``_persoon_id`` (:func:`identiteit.pseudonimiseer`, #173);
      zonder salt faalt decode.
    - Overige velden blijven ``pl.Utf8``.

    Args:
        frames:      Dict van tabelnaam naar ruwe DataFrame.
        schema_name: Naam van het schema (bijv. ``"ro"``, ``"grondslag"``, ``"tbgi"``).

    Returns:
        Dict van tabelnaam naar getypeerde DataFrame.
    """
    schema = load_schema(schema_name)

    result: dict[str, pl.DataFrame] = {}
    for rt, df in frames.items():
        if rt not in schema:
            result[rt] = df
            continue

        rt_schema = schema[rt]
        date_fields = set(rt_schema.get("date_fields", []))
        partial_date_fields = set(rt_schema.get("partial_date_fields", []))
        int_fields = set(rt_schema.get("int_fields", []))
        float_fields = set(rt_schema.get("float_fields", []))

        exprs = []
        for col in df.columns:
            if col in partial_date_fields:
                datum, precisie = _deels_bekende_datum(
                    _naar_iso(leeg_naar_null(pl.col(col)))
                )
                exprs.append(datum.alias(col))
                exprs.append(precisie.alias(col + PRECISIE_SUFFIX))
            elif col in date_fields:
                exprs.append(
                    _naar_datum(_naar_iso(leeg_naar_null(pl.col(col)))).alias(col)
                )
            elif col in int_fields:
                exprs.append(
                    leeg_naar_null(pl.col(col)).cast(pl.Int64, strict=False).alias(col)
                )
            elif col in float_fields:
                exprs.append(_to_float_expr(pl.col(col)).alias(col))
            else:
                exprs.append(leeg_naar_null(pl.col(col)).alias(col))

        result[rt] = pseudonimiseer(
            _normaliseer_indicatie_bekostigbaar(df.with_columns(exprs))
        )

    return result


def decode_ro(frames: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Decodeer een RO-pakket. Dunne wrapper om :func:`decode_frames`
    met schema ``"ro"``."""
    return decode_frames(frames, "ro")


def decode_grondslag(frames: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Decodeer een GRONDSLAG IP MBO-pakket. Dunne wrapper om
    :func:`decode_frames` met schema ``"grondslag"``."""
    return decode_frames(frames, "grondslag")


def decode_tbgi(frames: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Decodeer een TBGI-pakket. Dunne wrapper om :func:`decode_frames`
    met schema ``"tbgi"``."""
    return decode_frames(frames, "tbgi")
