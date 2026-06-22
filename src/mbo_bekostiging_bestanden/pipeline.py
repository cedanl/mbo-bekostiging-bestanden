"""Orkestratie van de ingestion-pipeline: ingest > decode > validate > export."""

from collections.abc import Callable
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.decode import decode_grondslag, decode_ro, decode_tbgi
from mbo_bekostiging_bestanden.export import OutputFormat, export_frames
from mbo_bekostiging_bestanden.ingest import read_grondslag, read_ro, read_tbgi
from mbo_bekostiging_bestanden.validate import (
    validate_grondslag,
    validate_ro,
    validate_tbgi,
)

# Bestandsnaam-prefix (hoofdletters) → bestandstype-sleutel.
# Langere prefixen eerst: "GRONDSLAG_IP_MBO_" vóór een eventuele "GRONDSLAG_".
_PREFIXES: dict[str, str] = {
    "GRONDSLAG_IP_MBO_": "grondslag",
    "TBGI_": "tbgi",
    "RO_": "ro",
}


def detect_bestandstype(path: str | Path) -> str | None:
    """Detecteer het bestandstype op basis van de bestandsnaam.

    Returns:
        ``"ro"``, ``"grondslag"``, ``"tbgi"``, of ``None`` als het type onbekend is.
    """
    name = Path(path).name.upper()
    for prefix, bestandstype in _PREFIXES.items():
        if name.startswith(prefix):
            return bestandstype
    return None


def run_auto_pipeline(
    source: str | Path,
    target: str | Path,
    fmt: OutputFormat = "parquet",
) -> dict[str, pl.DataFrame]:
    """Detecteer het bestandstype en draai de juiste pipeline automatisch.

    Args:
        source: Pad naar een ruw bekostigingsbestand.
        target: Doelmap voor de uitvoerbestanden.
        fmt:    Uitvoerformaat: ``"parquet"`` (standaard) of ``"csv"``.

    Returns:
        Dict van tabelnaam naar getypeerde DataFrame.

    Raises:
        ValueError: Als het bestandstype niet herkend wordt.
    """
    bestandstype = detect_bestandstype(source)
    if bestandstype is None:
        raise ValueError(
            f"Onbekend bestandstype: {Path(source).name!r}. "
            f"Ondersteund: {sorted(_PIPELINES)}"
        )
    return _PIPELINES[bestandstype](source, target, fmt=fmt)


def _run(
    reader: Callable,
    decoder: Callable,
    validator: Callable,
    source: str | Path,
    target: str | Path,
    fmt: OutputFormat,
) -> dict[str, pl.DataFrame]:
    frames = reader(Path(source))
    frames = decoder(frames)
    validator(frames)
    export_frames(frames, Path(target), fmt=fmt)
    return frames


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
    return _run(read_ro, decode_ro, validate_ro, source, target, fmt)


def run_grondslag_pipeline(
    source: str | Path,
    target: str | Path,
    fmt: OutputFormat = "parquet",
) -> dict[str, pl.DataFrame]:
    """Draai de volledige GRONDSLAG IP MBO-pipeline van ruw bestand naar schone output.

    Args:
        source: Pad naar een ruw GRONDSLAG-bestand in ``data/01-raw/``.
        target: Doelmap voor de uitvoerbestanden in ``data/02-prepared/``.
        fmt:    Uitvoerformaat: ``"parquet"`` (standaard) of ``"csv"``.

    Returns:
        Dict van recordtype-code naar getypeerde DataFrame.
    """
    return _run(
        read_grondslag, decode_grondslag, validate_grondslag, source, target, fmt
    )


def run_tbgi_pipeline(
    source: str | Path,
    target: str | Path,
    fmt: OutputFormat = "parquet",
) -> dict[str, pl.DataFrame]:
    """Draai de volledige TBGI-pipeline van ruw XML-bestand naar schone output.

    Args:
        source: Pad naar een ruw TBGI XML-bestand in ``data/01-raw/``.
        target: Doelmap voor de uitvoerbestanden in ``data/02-prepared/``.
        fmt:    Uitvoerformaat: ``"parquet"`` (standaard) of ``"csv"``.

    Returns:
        Dict van tabelnaam naar getypeerde DataFrame.
    """
    return _run(read_tbgi, decode_tbgi, validate_tbgi, source, target, fmt)


# Registry van bestandstype-sleutel → pipeline-functie.
# Staat ná de functies zodat directe referenties werken zonder lambdas.
_PIPELINES = {
    "ro": run_pipeline,
    "grondslag": run_grondslag_pipeline,
    "tbgi": run_tbgi_pipeline,
}
