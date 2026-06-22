"""Decoderen van RO-velden: strings omzetten naar juiste types via schema-metadata."""

import re
import tomllib
from pathlib import Path

import polars as pl


def _load_schema(schema_path: Path) -> dict[str, dict]:
    with open(schema_path, "rb") as f:
        data = tomllib.load(f)
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _detect_date_format(sample: str) -> str:
    """Detecteer datumformaat uit een niet-lege voorbeeldwaarde.

    Returns:
        "iso"   voor ccyy-mm-dd (bijv. 2026-03-25)
        "dutch" voor d-m-yyyy   (bijv. 1-8-2025)
    """
    if re.match(r"^\d{4}-\d{2}-\d{2}$", sample):
        return "iso"
    return "dutch"


def _to_iso_expr(col: pl.Expr) -> pl.Expr:
    """Converteer een datumkolom in ISO-formaat naar pl.Date."""
    return col.str.to_date("%Y-%m-%d", strict=False)


def _to_dutch_expr(col: pl.Expr) -> pl.Expr:
    """Converteer een datumkolom in d-m-yyyy (zonder leading zeros) naar pl.Date.

    Strategie: vervang lege strings door null, split op '-', zero-pad dag en
    maand, recombineer als ISO yyyy-mm-dd, parse naar pl.Date.
    """
    non_empty = pl.when(col == "").then(pl.lit(None, dtype=pl.Utf8)).otherwise(col)
    parts = non_empty.str.split("-")
    day   = parts.list.get(0, null_on_oob=True).str.zfill(2)
    month = parts.list.get(1, null_on_oob=True).str.zfill(2)
    year  = parts.list.get(2, null_on_oob=True)
    iso   = pl.concat_str([year, month, day], separator="-", ignore_nulls=False)
    return iso.str.to_date("%Y-%m-%d", strict=False)


def _find_date_sample(frames: dict[str, pl.DataFrame]) -> str:
    """Zoek de eerste niet-lege datumwaarde uit VLP.DatumAanmaak."""
    vlp = frames.get("VLP")
    if vlp is not None and vlp.height > 0:
        val = vlp["DatumAanmaak"][0]
        if val:
            return val
    return ""


def decode_ro(frames: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Cast RO-velden naar het juiste type op basis van ro_schema.toml.

    - Datumvelden worden pl.Date (null bij lege waarde).
    - Telwaarden (SLR) worden pl.Int64.
    - Examenscores (GEO) worden nullable pl.Int64.
    - Overige velden blijven pl.Utf8.
    """
    schema_path = Path(__file__).parent / "metadata" / "ro_schema.toml"
    schema = _load_schema(schema_path)

    sample = _find_date_sample(frames)
    date_fmt = _detect_date_format(sample) if sample else "iso"
    to_date = _to_dutch_expr if date_fmt == "dutch" else _to_iso_expr

    result: dict[str, pl.DataFrame] = {}
    for rt, df in frames.items():
        if rt not in schema:
            result[rt] = df
            continue

        rt_schema = schema[rt]
        date_fields = set(rt_schema.get("date_fields", []))
        int_fields  = set(rt_schema.get("int_fields", []))

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
            else:
                exprs.append(pl.col(col))

        result[rt] = df.with_columns(exprs)

    return result
