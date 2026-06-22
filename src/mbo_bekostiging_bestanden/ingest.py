"""Inlezen van ruwe bekostigingsbestanden."""

from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.metadata import load_schema


def _detect_separator(line: str) -> str:
    return "|" if line.count("|") >= line.count(";") else ";"


def _normalize_row(row: list[str], n: int) -> list[str]:
    """Clip of pad een rij tot exact n velden."""
    if len(row) >= n:
        return row[:n]
    return row + [""] * (n - len(row))


def read_multi_record_csv(
    path: str | Path,
    schema_name: str,
) -> dict[str, pl.DataFrame]:
    """Lees een multi-record CSV-bestand in en splits per recordtype.

    Geschikt voor elk DUO-bestandstype dat de multi-record CSV-structuur
    gebruikt (RO, GRONDSLAG IP MBO, …). Kolomnamen komen uit het opgegeven
    schema-TOML.

    Args:
        path:        Pad naar het bronbestand.
        schema_name: Naam van het schema (bijv. ``"ro"`` of ``"grondslag"``).

    Returns:
        Dict met recordtype-code als sleutel en een DataFrame als waarde.

    Raises:
        FileNotFoundError: Als het bronbestand of schema niet bestaat.
        ValueError:        Als het bestand leeg is.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Bronbestand niet gevonden: {path}")

    raw_schema = load_schema(schema_name)
    schema = {rt: v["fields"] for rt, v in raw_schema.items()}

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


def read_ro(path: str | Path) -> dict[str, pl.DataFrame]:
    """Lees een RO-bestand in en splits per recordtype.

    Dunne wrapper om :func:`read_multi_record_csv` met schema ``"ro"``.
    """
    return read_multi_record_csv(path, "ro")
