"""Orkestratie van de ingestion-pipeline: ingest > decode > validate > export."""

from collections.abc import Callable
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.decode import decode_grondslag, decode_ro
from mbo_bekostiging_bestanden.export import OutputFormat, export_frames
from mbo_bekostiging_bestanden.ingest import read_grondslag, read_ro
from mbo_bekostiging_bestanden.validate import validate_grondslag, validate_ro

# Bestandsnaam-prefix (hoofdletters) → bestandstype-sleutel.
# Volgorde is relevant: langere prefixen eerst zodat "GRONDSLAG_IP_MBO_" niet
# matcht op een hypothetische prefix "GRONDSLAG_".
_PREFIXES: dict[str, str] = {
    "GRONDSLAG_IP_MBO_": "grondslag",
    "RO_": "ro",
}


def detect_bestandstype(path: str | Path) -> str | None:
    """Detecteer het bestandstype op basis van de bestandsnaam.

    Returns:
        ``"ro"``, ``"grondslag"``, of ``None`` als het type onbekend is.
    """
    name = Path(path).name.upper()
    for prefix, bestandstype in _PREFIXES.items():
        if name.startswith(prefix):
            return bestandstype
    return None


# Registry van bestandstype-sleutel → pipeline-functie.
# Type is Callable zodat mypy/ty de signatuur kan verifiëren bij uitbreiding.
_PIPELINES: dict[str, Callable[..., dict[str, pl.DataFrame]]] = {
    "ro": lambda s, t, fmt: run_pipeline(s, t, fmt=fmt),
    "grondslag": lambda s, t, fmt: run_grondslag_pipeline(s, t, fmt=fmt),
}


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
        Dict van recordtype-code naar getypeerde DataFrame.

    Raises:
        ValueError: Als het bestandstype niet herkend wordt.
    """
    bestandstype = detect_bestandstype(source)
    if bestandstype is None:
        raise ValueError(
            f"Onbekend bestandstype: {Path(source).name!r}. "
            f"Ondersteund: {sorted(_PIPELINES)}"
        )
    return _PIPELINES[bestandstype](source, target, fmt)


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
    validate_ro(frames)
    export_frames(frames, Path(target), fmt=fmt)
    return frames


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
    frames = read_grondslag(Path(source))
    frames = decode_grondslag(frames)
    validate_grondslag(frames)
    export_frames(frames, Path(target), fmt=fmt)
    return frames
