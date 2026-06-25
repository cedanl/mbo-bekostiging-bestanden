"""Decoderen van velden: strings omzetten naar juiste types via schema-metadata."""

import re

import polars as pl

from mbo_bekostiging_bestanden.metadata import load_schema


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


def _to_iso_expr(col: pl.Expr) -> pl.Expr:
    return col.str.to_date("%Y-%m-%d", strict=False)


def _to_compact_expr(col: pl.Expr) -> pl.Expr:
    """Converteer ``YYYYMMDD`` (geen scheidingstekens) naar ``pl.Date``."""
    non_empty = pl.when(col == "").then(pl.lit(None, dtype=pl.Utf8)).otherwise(col)
    return non_empty.str.to_date("%Y%m%d", strict=False)


def _to_dutch_expr(col: pl.Expr) -> pl.Expr:
    """Converteer ``d-m-yyyy`` (zonder leading zeros) naar ``pl.Date``.

    Strategie: vervang lege strings door null, split op ``-``, zero-pad dag en
    maand, recombineer als ISO ``yyyy-mm-dd``, parse naar ``pl.Date``.
    """
    non_empty = pl.when(col == "").then(pl.lit(None, dtype=pl.Utf8)).otherwise(col)
    parts = non_empty.str.split("-")
    day = parts.list.get(0, null_on_oob=True).str.zfill(2)
    month = parts.list.get(1, null_on_oob=True).str.zfill(2)
    year = parts.list.get(2, null_on_oob=True)
    iso = pl.concat_str([year, month, day], separator="-", ignore_nulls=False)
    return iso.str.to_date("%Y-%m-%d", strict=False)


_DATE_EXPR = {
    "iso": _to_iso_expr,
    "compact": _to_compact_expr,
    "dutch": _to_dutch_expr,
}


def _find_date_sample(frames: dict[str, pl.DataFrame], schema: dict[str, dict]) -> str:
    """Zoek de eerste niet-lege datumwaarde door alle schema-datumvelden te scannen."""
    for rt, df in frames.items():
        if rt not in schema or df.height == 0:
            continue
        for field in schema[rt].get("date_fields", []):
            if field in df.columns:
                val = df[field][0]
                if val:
                    return val
    return ""


def _to_float_expr(col: pl.Expr) -> pl.Expr:
    """Converteer een string-kolom naar ``pl.Float64`` (null bij lege waarde)."""
    return pl.when(col == "").then(None).otherwise(col).cast(pl.Float64)


def decode_frames(
    frames: dict[str, pl.DataFrame],
    schema_name: str,
) -> dict[str, pl.DataFrame]:
    """Cast velden naar het juiste type op basis van het opgegeven schema-TOML.

    - Datumvelden worden ``pl.Date`` (null bij lege waarde).
    - Integer-velden worden ``pl.Int64``.
    - Float-velden worden ``pl.Float64``.
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
    to_date = _DATE_EXPR[date_fmt]

    result: dict[str, pl.DataFrame] = {}
    for rt, df in frames.items():
        if rt not in schema:
            result[rt] = df
            continue

        rt_schema = schema[rt]
        date_fields = set(rt_schema.get("date_fields", []))
        int_fields = set(rt_schema.get("int_fields", []))
        float_fields = set(rt_schema.get("float_fields", []))

        exprs = []
        for col in df.columns:
            if col in date_fields:
                exprs.append(to_date(pl.col(col)).alias(col))
            elif col in int_fields:
                exprs.append(
                    pl.when(pl.col(col) == "")
                    .then(None)
                    .otherwise(pl.col(col))
                    .cast(pl.Int64)
                    .alias(col)
                )
            elif col in float_fields:
                exprs.append(_to_float_expr(pl.col(col)).alias(col))
            else:
                exprs.append(
                    pl.when(pl.col(col) == "").then(None).otherwise(pl.col(col)).alias(col)
                )

        result[rt] = df.with_columns(exprs)

    return result


def decode_ro(frames: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Decodeer een RO-pakket naar getypeerde DataFrames.

    Dunne wrapper om :func:`decode_frames` met schema ``"ro"``.
    """
    return decode_frames(frames, "ro")


def decode_grondslag(frames: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Decodeer een GRONDSLAG IP MBO-pakket naar getypeerde DataFrames.

    Dunne wrapper om :func:`decode_frames` met schema ``"grondslag"``.
    """
    return decode_frames(frames, "grondslag")


def decode_tbgi(frames: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Decodeer een TBGI-pakket naar getypeerde DataFrames.

    Dunne wrapper om :func:`decode_frames` met schema ``"tbgi"``.
    """
    return decode_frames(frames, "tbgi")
