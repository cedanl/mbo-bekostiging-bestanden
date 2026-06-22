"""Wegschrijven van schone data naar de output-map."""

from pathlib import Path

import polars as pl


def export_data(data: pl.DataFrame, path: str | Path) -> Path:
    """Schrijf schone data weg als Parquet.

    Args:
        data: Gevalideerde data uit :func:`validate.validate_data`.
        path: Doelpad in ``data/02-prepared/`` of ``data/03-output/``.

    Returns:
        Het pad waar de data is weggeschreven.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data.write_parquet(path)
    return path
