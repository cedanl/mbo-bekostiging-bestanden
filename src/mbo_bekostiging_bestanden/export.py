"""Wegschrijven van schone data naar de output-map."""

from pathlib import Path

import polars as pl


def export_data(data: pl.DataFrame, path: str | Path) -> Path:
    """Schrijf één DataFrame weg als Parquet."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data.write_parquet(path)
    return path


def export_ro(frames: dict[str, pl.DataFrame], output_dir: str | Path) -> list[Path]:
    """Schrijf elk RO-recordtype als apart Parquet-bestand naar output_dir.

    Args:
        frames:     Dict van recordtype-code naar getypeerde DataFrame.
        output_dir: Doelmap (wordt aangemaakt als die niet bestaat).

    Returns:
        Lijst van geschreven paden.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for rt, df in frames.items():
        path = output_dir / f"{rt}.parquet"
        df.write_parquet(path)
        written.append(path)

    return written
