"""Orkestratie van de ingestion-pipeline: ingest > decode > validate > export."""

from pathlib import Path

from mbo_bekostiging_bestanden.decode import decode_ro
from mbo_bekostiging_bestanden.export import export_ro
from mbo_bekostiging_bestanden.ingest import read_ro
from mbo_bekostiging_bestanden.validate import validate_data


def run_pipeline(source: str | Path, target: str | Path) -> dict:
    """Draai de volledige RO-pipeline van ruw bestand naar Parquet-output.

    Args:
        source: Pad naar een ruw RO-bestand in data/01-raw/.
        target: Doelmap voor de Parquet-bestanden in data/02-prepared/.

    Returns:
        Dict van recordtype-code naar getypeerde DataFrame.
    """
    source = Path(source)
    target = Path(target)

    frames = read_ro(source)
    frames = decode_ro(frames)

    for _rt, df in frames.items():
        validate_data(df)

    export_ro(frames, target)
    return frames
