"""Wegschrijven van schone data naar de output-map."""

from pathlib import Path
from typing import Literal

import polars as pl

OutputFormat = Literal["parquet", "csv"]


def export_ro(
    frames: dict[str, pl.DataFrame],
    output_dir: str | Path,
    fmt: OutputFormat = "parquet",
) -> list[Path]:
    """Schrijf elk RO-recordtype als apart bestand naar output_dir.

    Args:
        frames:     Dict van recordtype-code naar getypeerde DataFrame.
        output_dir: Doelmap (wordt aangemaakt als die niet bestaat).
        fmt:        Uitvoerformaat: ``"parquet"`` (standaard) of ``"csv"``.

    Returns:
        Lijst van geschreven paden.

    Raises:
        ValueError: Als ``fmt`` geen ondersteund formaat is.
    """
    if fmt not in ("parquet", "csv"):
        raise ValueError(f"Onbekend formaat {fmt!r}. Kies 'parquet' of 'csv'.")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for rt, df in frames.items():
        path = output_dir / f"{rt}.{fmt}"
        if fmt == "parquet":
            df.write_parquet(path)
        else:
            df.write_csv(path)
        written.append(path)

    return written
