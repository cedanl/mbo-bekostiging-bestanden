"""Inlezen van ruwe bekostigingsbestanden."""

import tomllib
from pathlib import Path

import polars as pl


def _load_schema(schema_path: Path) -> dict[str, list[str]]:
    with open(schema_path, "rb") as f:
        data = tomllib.load(f)
    return {
        key: value["fields"]
        for key, value in data.items()
        if isinstance(value, dict) and "fields" in value
    }


def _detect_separator(line: str) -> str:
    return "|" if line.count("|") >= line.count(";") else ";"


def _normalize_row(row: list[str], n: int) -> list[str]:
    """Clip of pad een rij tot exact n velden."""
    if len(row) >= n:
        return row[:n]
    return row + [""] * (n - len(row))


def read_ro(path: str | Path) -> dict[str, pl.DataFrame]:
    """Lees een RO-bestand in en splits per recordtype.

    Returns:
        Dict met recordtype-code als sleutel en een DataFrame als waarde.
        Kolomnamen komen uit ro_schema.toml.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Bronbestand niet gevonden: {path}")

    schema_path = Path(__file__).parent / "metadata" / "ro_schema.toml"
    schema = _load_schema(schema_path)

    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        content = path.read_text(encoding="latin-1")

    lines = [line.rstrip("\r") for line in content.splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"Leeg bestand: {path}")

    sep = _detect_separator(lines[0])

    rows_by_type: dict[str, list[list[str]]] = {rt: [] for rt in schema}
    for line in lines:
        fields = line.rstrip(sep).split(sep)
        rt = fields[0] if fields else ""
        if rt in rows_by_type:
            rows_by_type[rt].append(fields)

    result: dict[str, pl.DataFrame] = {}
    for rt, rows in rows_by_type.items():
        if not rows:
            continue
        cols = schema[rt]
        n = len(cols)
        normalized = [_normalize_row(row, n) for row in rows]
        result[rt] = pl.DataFrame(
            {col: [r[i] for r in normalized] for i, col in enumerate(cols)}
        )

    return result
