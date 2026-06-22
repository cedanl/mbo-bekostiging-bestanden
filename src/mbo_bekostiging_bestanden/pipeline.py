"""Orkestratie van de ingestion-pipeline: ingest > decode > validate > export."""

from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.decode import decode_ro
from mbo_bekostiging_bestanden.export import OutputFormat, export_ro
from mbo_bekostiging_bestanden.ingest import read_ro
from mbo_bekostiging_bestanden.validate import validate_data


def run_pipeline(
    source: str | Path,
    target: str | Path,
    fmt: OutputFormat = "parquet",
) -> dict[str, pl.DataFrame]:
    """Draai de volledige RO-pipeline van ruw bestand naar schone output.

    Args:
        source: Pad naar een ruw RO-bestand in ``data/01-raw/``.
        target: Doelmap voor de uitvoerbestanden in ``data/02-prepared/``.
        fmt:    Uitvoerformaat: ``"parquet"`` (standaard) of ``"csv"``.

    Returns:
        Dict van recordtype-code naar getypeerde DataFrame.
    """
    frames = read_ro(Path(source))
    frames = decode_ro(frames)

    for _rt, df in frames.items():
        validate_data(df)

    export_ro(frames, Path(target), fmt=fmt)
    return frames
