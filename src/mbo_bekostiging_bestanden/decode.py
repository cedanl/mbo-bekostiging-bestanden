"""Decoderen van velden: strings omzetten naar juiste types via schema-metadata."""

import re

import polars as pl

from mbo_bekostiging_bestanden.metadata import load_schema
from mbo_bekostiging_bestanden.waardenlijsten import indicatie_bekostigbaar

_DECIMAALKOMMA = ","


def _detect_date_format(sample: str) -> str:
    """Detecteer datumformaat uit een niet-lege voorbeeldwaarde.

    Returns:
        ``"iso"``     voor ``ccyy-mm-dd``  (bijv. ``2026-03-25``)
        ``"compact"`` voor ``ccyymmdd``    (bijv. ``20251119``)
        ``"dutch"``   voor ``d-m-yyyy``    (bijv. ``1-8-2025``)
    """
    if re.match(r"^\d{4}-\d{2}-\d{2}$", sample):
        return "iso"
    if re.match(r"^\d{8}$", sample):
        return "compact"
    return "dutch"


def _iso_uit_iso(col: pl.Expr) -> pl.Expr:
    return col


def _iso_uit_compact(col: pl.Expr) -> pl.Expr:
    """``ccyymmdd`` → ``ccyy-mm-dd``."""
    return col.str.replace(r"^(\d{4})(\d{2})(\d{2})$", "${1}-${2}-${3}")


def _iso_uit_dutch(col: pl.Expr) -> pl.Expr:
    """``d-m-yyyy`` (zonder voorloopnullen) → ``ccyy-mm-dd``."""
    parts = col.str.split("-")
    day = parts.list.get(0, null_on_oob=True).str.zfill(2)
    month = parts.list.get(1, null_on_oob=True).str.zfill(2)
    year = parts.list.get(2, null_on_oob=True)
    return pl.concat_str([year, month, day], separator="-", ignore_nulls=False)


# Per bronformaat: expressie die een datumstring naar ISO-tekst omzet.
_NAAR_ISO = {
    "iso": _iso_uit_iso,
    "compact": _iso_uit_compact,
    "dutch": _iso_uit_dutch,
}

# Onbekende dag/maand ("00", PvE §15.5.2) → eerste van de maand/het jaar.
_ONBEKENDE_MAAND = r"-00-00$"
_ONBEKENDE_DAG = r"-00$"
_PRECISIE_SUFFIX = "_precisie"
_PRECISIE_DAG, _PRECISIE_MAAND, _PRECISIE_JAAR = "dag", "maand", "jaar"


def _naar_datum(iso: pl.Expr) -> pl.Expr:
    return iso.str.to_date("%Y-%m-%d", strict=False)


def _deels_bekende_datum(iso: pl.Expr) -> tuple[pl.Expr, pl.Expr]:
    """``(datum, precisie)`` voor een ISO-string waarin dag of maand ``00`` mag zijn."""
    aangevuld = iso.str.replace(_ONBEKENDE_MAAND, "-01-01").str.replace(
        _ONBEKENDE_DAG, "-01"
    )
    datum = _naar_datum(aangevuld)
    precisie = (
        pl.when(datum.is_null())
        .then(None)
        .when(iso.str.contains(_ONBEKENDE_MAAND))
        .then(pl.lit(_PRECISIE_JAAR))
        .when(iso.str.contains(_ONBEKENDE_DAG))
        .then(pl.lit(_PRECISIE_MAAND))
        .otherwise(pl.lit(_PRECISIE_DAG))
    )
    return datum, precisie


def _find_date_sample(frames: dict[str, pl.DataFrame], schema: dict[str, dict]) -> str:
    """Zoek de eerste niet-lege datumwaarde door alle schema-datumvelden te scannen."""
    for rt, df in frames.items():
        if rt not in schema or df.height == 0:
            continue
        for field in schema[rt].get("date_fields", []):
            if field in df.columns:
                val = (df[field][0] or "").strip()
                if val:
                    return val
    return ""


def _leeg_naar_null(col: pl.Expr) -> pl.Expr:
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
        _leeg_naar_null(col)
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

    - Datumvelden worden ``pl.Date`` (null bij lege waarde). Velden in
      ``partial_date_fields`` mogen een onbekende dag/maand (``00``) hebben:
      die wordt de eerste van de maand/het jaar, met ``<veld>_precisie``
      (``dag``/``maand``/``jaar``).
    - Integer-velden worden ``pl.Int64``.
    - Float-velden worden ``pl.Float64``; een decimaalkomma wordt geaccepteerd.
    - Alle casts zijn niet-strikt: een ongeldige waarde wordt null en telt als
      parseverlies in ``quality.json`` (zie :func:`quality.tel_parseverlies`),
      een error voor de kwaliteitspoort (#390).
    - ``IndicatieBekostigbaar`` wordt genormaliseerd naar ``"J"``/``"N"``.
    - Overige velden blijven ``pl.Utf8``.

    Args:
        frames:      Dict van tabelnaam naar ruwe DataFrame.
        schema_name: Naam van het schema (bijv. ``"ro"``, ``"grondslag"``, ``"tbgi"``).

    Returns:
        Dict van tabelnaam naar getypeerde DataFrame.
    """
    schema = load_schema(schema_name)

    sample = _find_date_sample(frames, schema)
    date_fmt = _detect_date_format(sample) if sample else "iso"
    naar_iso = _NAAR_ISO[date_fmt]

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
                    naar_iso(_leeg_naar_null(pl.col(col)))
                )
                exprs.append(datum.alias(col))
                exprs.append(precisie.alias(col + _PRECISIE_SUFFIX))
            elif col in date_fields:
                exprs.append(
                    _naar_datum(naar_iso(_leeg_naar_null(pl.col(col)))).alias(col)
                )
            elif col in int_fields:
                exprs.append(
                    _leeg_naar_null(pl.col(col)).cast(pl.Int64, strict=False).alias(col)
                )
            elif col in float_fields:
                exprs.append(_to_float_expr(pl.col(col)).alias(col))
            else:
                exprs.append(_leeg_naar_null(pl.col(col)).alias(col))

        result[rt] = _normaliseer_indicatie_bekostigbaar(df.with_columns(exprs))

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
