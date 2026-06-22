"""Inlezen van ruwe bekostigingsbestanden (fixed-width / CSV)."""

from pathlib import Path

import polars as pl


def read_raw_file(path: str | Path) -> pl.DataFrame:
    """Lees een ruw bekostigingsbestand in als DataFrame.

    Args:
        path: Pad naar het ruwe bron-bestand in ``data/01-raw/``.

    Returns:
        DataFrame met de onbewerkte kolommen.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Bronbestand niet gevonden: {path}")

    # TODO: vervang door de werkelijke veldindeling (fixed-width of CSV).
    return pl.read_csv(path)
