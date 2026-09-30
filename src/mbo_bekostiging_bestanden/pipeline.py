"""Orkestratie van de ingestion-pipeline: ingest > decode > validate > export."""

import json
from collections.abc import Callable, Sequence
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.decode import decode_grondslag, decode_ro, decode_tbgi
from mbo_bekostiging_bestanden.export import OutputFormat, export_frames
from mbo_bekostiging_bestanden.ingest import (
    inventariseer_regels,
    inventariseer_xml_elementen,
    layoutvarianten,
    read_grondslag,
    read_ro,
    read_tbgi,
)
from mbo_bekostiging_bestanden.provenance import bronbestand, met_bronbestanden
from mbo_bekostiging_bestanden.quality import (
    SCENARIO_ONBEKEND,
    KwaliteitsFout,
    check_slr_reconciliation,
    compile_quality_report,
    lees_leveringsrapport,
    tel_parseverlies,
    write_quality_json,
)
from mbo_bekostiging_bestanden.stack import leveringslabels, stack_prepared
from mbo_bekostiging_bestanden.star import build_star
from mbo_bekostiging_bestanden.validate import (
    validate_grondslag,
    validate_ro,
    validate_tbgi,
)
from mbo_bekostiging_bestanden.waardenlijsten import (
    controleer_waardedomeinen,
    dekkingsoverzicht,
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
    schema_naam: str,
    inventaris: Callable[[Path, str], dict] = inventariseer_regels,
    layouts: Callable[[Path, str], dict] | None = layoutvarianten,
) -> dict[str, pl.DataFrame]:
    source_path = Path(source)
    target_path = Path(target)

    ruw = reader(source_path)
    frames = decoder(ruw)
    validator(frames)

    # Genereer kwaliteitsrapport (SLR-reconciliatie, parseverlies)
    levering = source_path.stem  # bijv. "RO_27DV_20240731_20260324"
    quality_report = check_slr_reconciliation(frames, levering, schema_naam=schema_naam)
    quality_report.meld_parseverlies(tel_parseverlies(ruw, frames))
    quality_report.meld_domeinafwijkingen(
        controleer_waardedomeinen(ruw, schema_naam, getypeerd=frames)
    )
    quality_report.domeindekking = dekkingsoverzicht(schema_naam)
    quality_report.bronbestand = bronbestand(source_path)
    quality_report.meld_regelinventaris(inventaris(source_path, schema_naam))
    if layouts is not None:
        quality_report.layoutvarianten = layouts(source_path, schema_naam)

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
    return _run(
        read_ro,
        decode_ro,
        validate_ro,
        source,
        target,
        fmt,
        schema_naam="ro",
    )


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
        read_grondslag,
        decode_grondslag,
        validate_grondslag,
        source,
        target,
        fmt,
        schema_naam="grondslag",
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
    return _run(
        read_tbgi,
        decode_tbgi,
        validate_tbgi,
        source,
        target,
        fmt,
        schema_naam="tbgi",
        inventaris=inventariseer_xml_elementen,
        layouts=None,
    )


def run_star(
    sources: Sequence[Path | str],
    target: str | Path,
    relative_to: Path | str | None = None,
    scenario: str = SCENARIO_ONBEKEND,
    fail_on_errors: bool = True,
) -> dict[str, pl.DataFrame]:
    """Stapel prepared-mappen, bouw het star schema en exporteer het.

    Args:
        sources:     Lijst van mappen met prepared Parquet-bestanden.
        target:      Doelmap; star schema komt in ``<target>/datamodel/``.
        relative_to: Basispad voor automatische leveringslabels (optioneel).
        scenario:    Label voor ``quality.json`` (bijv. ``"demo"``, ``"prod"``).
        fail_on_errors: Werp :class:`KwaliteitsFout` als de status ``fail`` is
                     (#289). ``False`` is de override voor exploratief werk en de
                     app, die de status zelf toont; de override staat in de
                     provenance van ``quality.json``.

    Returns:
        Dict met de star-schema-tabellen; tevens geschreven naar
        ``<target>/datamodel/``.

    Raises:
        KwaliteitsFout: Bij status ``fail`` en ``fail_on_errors``; de ster en
            ``quality.json`` zijn dan wel al geschreven, als diagnose.
    """
    target = Path(target)
    labels = leveringslabels(sources, relative_to)
    invoer = stack_prepared(sources, labels=labels)
    star_tables = build_star(invoer)
    # Per-levering SLR, parseverlies en bronbestand, onder het label uit de ster.
    deliveries = {
        label: lees_leveringsrapport(Path(source) / "quality.json", label)
        for source, label in zip(sources, labels, strict=True)
    }

    star_tables["meta_leveringen"] = met_bronbestanden(
        star_tables["meta_leveringen"], deliveries
    )
    export_frames(star_tables, target / "datamodel")
    quality_report = compile_quality_report(
        star_tables,
        deliveries=deliveries,
        scenario=scenario,
        invoer=invoer,
        fouten_toegestaan=not fail_on_errors,
    )
    rapport_pad = write_quality_json(quality_report, target / "quality.json")
    samenvatting = quality_report["summary"]
    if fail_on_errors and samenvatting["status"] == "fail":
        raise KwaliteitsFout(
            f"Kwaliteitsstatus fail ({samenvatting['total_errors']} error(s)); "
            f"zie {rapport_pad}"
        )

    return star_tables


# Registry van bestandstype-sleutel → pipeline-functie.
# Staat ná de functies zodat directe referenties werken zonder lambdas.
_PIPELINES = {
    "ro": run_pipeline,
    "grondslag": run_grondslag_pipeline,
    "tbgi": run_tbgi_pipeline,
}
