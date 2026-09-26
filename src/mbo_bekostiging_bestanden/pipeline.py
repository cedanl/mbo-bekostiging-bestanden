"""Orkestratie van de ingestion-pipeline: ingest > decode > validate > export."""

import json
from collections.abc import Callable, Sequence
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.decode import decode_grondslag, decode_ro, decode_tbgi
from mbo_bekostiging_bestanden.export import OutputFormat, export_frames
from mbo_bekostiging_bestanden.ingest import read_grondslag, read_ro, read_tbgi
from mbo_bekostiging_bestanden.quality import (
    SCENARIO_ONBEKEND,
    QualityReport,
    check_slr_reconciliation,
    compile_quality_report,
    tel_parseverlies,
    write_quality_json,
)
from mbo_bekostiging_bestanden.stack import stack_prepared
from mbo_bekostiging_bestanden.star import build_star
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
    source_path = Path(source)
    target_path = Path(target)

    ruw = reader(source_path)
    frames = decoder(ruw)
    validator(frames)

    # Genereer kwaliteitsrapport (SLR-reconciliatie, parseverlies)
    levering = source_path.stem  # bijv. "RO_27DV_20240731_20260324"
    quality_report = check_slr_reconciliation(frames, levering)
    quality_report.meld_parseverlies(tel_parseverlies(ruw, frames))

    # Sla rapport op als JSON
    report_path = target_path / "quality.json"
    target_path.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(quality_report.as_dict(), f, indent=2, ensure_ascii=False)

    export_frames(frames, target_path, fmt=fmt)
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


def run_star(
    sources: Sequence[Path | str],
    target: str | Path,
    relative_to: Path | str | None = None,
    scenario: str = SCENARIO_ONBEKEND,
) -> dict[str, pl.DataFrame]:
    """Stapel prepared-mappen, bouw het star schema en exporteer het.

    Args:
        sources:     Lijst van mappen met prepared Parquet-bestanden.
        target:      Doelmap; star schema komt in ``<target>/datamodel/``.
        relative_to: Basispad voor automatische leveringslabels (optioneel).
        scenario:    Label voor ``quality.json`` (bijv. ``"demo"``, ``"prod"``).

    Returns:
        Dict met de twaalf star-schema-tabellen; tevens geschreven naar
        ``<target>/datamodel/``.
    """
    target = Path(target)
    stacked = stack_prepared(sources, relative_to=relative_to)
    star_tables = build_star(stacked)
    export_frames(star_tables, target / "datamodel")

    # Read quality reports from prepared sources to include SLR + parseverlies
    deliveries_dict: dict[str, QualityReport] = {}
    for source in sources:
        source_path = Path(source)
        quality_json = source_path / "quality.json"
        if quality_json.exists():
            with open(quality_json) as f:
                report_data = json.load(f)
                # Reconstruct QualityReport from JSON
                levering = report_data.get("levering", source_path.name)
                report = QualityReport(
                    levering=levering,
                    schema_type=report_data.get("schema_type", "unknown"),
                    slr_status=report_data.get("slr_status", "unknown"),
                    slr_checks=report_data.get("slr_details", {}),
                    parseverlies=report_data.get("parseverlies", {}),
                    warnings=report_data.get("warnings", []),
                    errors=report_data.get("errors", []),
                )
                deliveries_dict[levering] = report

    quality_report = compile_quality_report(
        star_tables,
        deliveries=deliveries_dict if deliveries_dict else None,
        scenario=scenario,
    )
    write_quality_json(quality_report, target / "quality.json")

    return star_tables


# Registry van bestandstype-sleutel → pipeline-functie.
# Staat ná de functies zodat directe referenties werken zonder lambdas.
_PIPELINES = {
    "ro": run_pipeline,
    "grondslag": run_grondslag_pipeline,
    "tbgi": run_tbgi_pipeline,
}
