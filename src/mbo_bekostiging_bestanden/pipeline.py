"""Orkestratie van de ingestion-pipeline: ingest > decode > validate > export."""

from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.decode import decode_fields
from mbo_bekostiging_bestanden.export import export_data
from mbo_bekostiging_bestanden.ingest import read_raw_file
from mbo_bekostiging_bestanden.validate import validate_data


def run_pipeline(source: str | Path, target: str | Path) -> pl.DataFrame:
    """Draai de volledige ingestion-pipeline van bron naar schone output.

    Args:
        source: Pad naar het ruwe bronbestand.
        target: Pad waar de schone data wordt weggeschreven.

    Returns:
        De schone, gevalideerde DataFrame.
    """
    data = read_raw_file(source)
    data = decode_fields(data)
    data = validate_data(data)
    export_data(data, target)
    return data
