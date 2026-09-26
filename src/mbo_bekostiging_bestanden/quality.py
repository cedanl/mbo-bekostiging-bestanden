"""Datakwaliteitscontroles: SLR, parseverlies, wees-feiten, sleutels, niveau.

Na validatie van schema: detecteer stille dataverlies en gedeeltelijke verwerking.
Alle controles retourneren gestructureerde dicts (JSON-serialiseerbaar).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from mbo_bekostiging_bestanden.filters import (
    _PERIODE_SLEUTEL,
    filter_detail_op_inschrijvingen,
)
from mbo_bekostiging_bestanden.transform import (
    _NIVEAU_HERKOMST,
    _NIVEAU_ONBEKEND,
    _NIVEAU_SBB_NVT,
)

# Icoon per tri-state SLR-status voor de app-weergave.
_SLR_STATUS_ICONS = {"match": "✅", "mismatch": "❌", "unknown": "⚠️"}


def slr_status_icoon(status: str | None) -> str:
    """Vertaal een SLR-status naar een weergave-icoon.

    Alles wat geen gedefinieerde tri-state waarde is (incl. ``None`` en oude
    ``quality.json``-bestanden zonder ``slr_status``) valt veilig terug op ⚠️.
    """
    return _SLR_STATUS_ICONS.get(status, "⚠️")


# Recordtypes die alleen in GRONDSLAG IP MBO voorkomen; VLP.Recordsoort is altijd
# "VLP" en kan een GRONDSLAG-bestand dus niet onderscheiden van een RO-bestand.
_GRONDSLAG_ONLY_RECORDTYPES = ("BII", "BID")
# VLP-veld dat alleen in de GRONDSLAG-variant voorkomt
# (zie metadata/grondslag_schema.toml).
_GRONDSLAG_VLP_KOLOM = "BekostigingsType"


def _bepaal_schema_type(frames: dict[str, pl.DataFrame]) -> str:
    """Leid het schema-type (ro|grondslag) af uit de aanwezige recordtypes.

    Twee onafhankelijke signalen: GRONDSLAG-only recordtypes (BII/BID) óf de
    VLP-variant met ``BekostigingsType`` — zo blijft een (demo)subset herkend
    worden, zelfs als daar geen BII/BID-records in zitten.
    """
    for rt in _GRONDSLAG_ONLY_RECORDTYPES:
        gronds_lag_frame = frames.get(rt)
        if gronds_lag_frame is not None and not gronds_lag_frame.is_empty():
            return "grondslag"
    vlp = frames.get("VLP")
    if vlp is not None and not vlp.is_empty():
        if _GRONDSLAG_VLP_KOLOM in vlp.columns:
            return "grondslag"
        return "ro"
    return "unknown"


@dataclass
class QualityReport:
    """Gestructureerd kwaliteitsrapport per leveringsbestand."""

    levering: str
    schema_type: str
    slr_checks: dict[str, dict[str, int]] = field(default_factory=dict)
    slr_status: str = "unknown"  # match | mismatch | unknown
    parseverlies: dict[str, dict[str, int]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def meld_parseverlies(self, verlies: dict[str, dict[str, int]]) -> None:
        """Neem parseverlies (zie :func:`tel_parseverlies`) op, met waarschuwing."""
        self.parseverlies = verlies
        if verlies:
            details = "; ".join(
                f"{tabel}.{kolom}: {n}"
                for tabel, per_kolom in verlies.items()
                for kolom, n in per_kolom.items()
            )
            self.warnings.append(
                f"Parseverlies (gevulde waarden die na typering leeg zijn): {details}"
            )

    def as_dict(self) -> dict:
        """Zet rapport om naar dict voor JSON-export."""
        return {
            "levering": self.levering,
            "schema_type": self.schema_type,
            "slr_status": self.slr_status,
            "slr_details": self.slr_checks,
            "parseverlies": self.parseverlies,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def tel_parseverlies(
    ruw: dict[str, pl.DataFrame], getypeerd: dict[str, pl.DataFrame]
) -> dict[str, dict[str, int]]:
    """Tel per tabel en kolom de gevulde bronwaarden die na typering leeg zijn.

    Alleen kolommen die van tekst naar een ander type gingen tellen mee: een
    ongeldige datum of een getal met tekst wordt bij het decoderen niet-strikt
    null.  ``ruw`` en ``getypeerd`` hebben per tabel dezelfde rijvolgorde.
    """
    verlies: dict[str, dict[str, int]] = {}
    for tabel, typed in getypeerd.items():
        bron = ruw.get(tabel)
        if bron is None:
            continue
        per_kolom = {}
        for kolom in typed.columns:
            if kolom not in bron.columns or typed[kolom].dtype == pl.Utf8:
                continue
            if bron[kolom].dtype != pl.Utf8:
                continue
            gevuld = bron[kolom].is_not_null() & (bron[kolom] != "")
            aantal = int((gevuld & typed[kolom].is_null()).sum())
            if aantal:
                per_kolom[kolom] = aantal
        if per_kolom:
            verlies[tabel] = per_kolom
    return verlies


def check_slr_reconciliation(
    frames: dict[str, pl.DataFrame],
    levering: str,
) -> QualityReport:
    """Reconcilieer geparste recordaantallen met SLR-controletotalen.

    SLR (sluitrecord) bevat DUO's eigen controletotalen per recordtype.
    Returns QualityReport met SLR-match status.
    """
    report = QualityReport(
        levering=levering,
        schema_type=_bepaal_schema_type(frames),
    )

    # Haal SLR op
    slr = frames.get("SLR")
    if slr is None or slr.is_empty():
        msg = "SLR (sluitrecord) niet gevonden; kan niet reconciliëren"
        report.warnings.append(msg)
        report.slr_status = "unknown"
        return report

    slr_row = slr.row(0, named=True)

    # Mapping: SLR-veldnaam -> recordtype (RO + GRONDSLAG recordtypes)
    slr_mapping = {
        "AantalPER": "PER",
        "AantalISG": "ISG",
        "AantalISP": "ISP",
        "AantalBPV": "BPV",
        "AantalDIP": "DIP",
        "AantalAMO": "AMO",
        "AantalGEO": "GEO",
        "AantalKZD": "KZD",
        "AantalISE": "ISE",  # GRONDSLAG
        "AantalBII": "BII",  # GRONDSLAG
        "AantalBID": "BID",  # GRONDSLAG
    }

    mismatches = []
    for slr_veld, rt in slr_mapping.items():
        expected = int(slr_row.get(slr_veld, 0)) if slr_row.get(slr_veld) else 0
        actual = frames.get(rt, pl.DataFrame()).shape[0]

        report.slr_checks[rt] = {"verwacht": expected, "gelezen": actual}

        if expected != actual:
            mismatches.append(f"{rt}: verwacht {expected}, gelezen {actual}")

    if mismatches:
        report.slr_status = "mismatch"
        report.warnings.append(f"SLR-mismatch: {'; '.join(mismatches)}")
    else:
        # Match = geen problemen: de status zelf is het signaal, dus géén
        # 'SLR-reconciliatie: OK'-start in warnings (die tonen in de UI ⚠️).
        report.slr_status = "match"

    return report


_FEIT_PREFIX = "fact_"
_CENTRAAL_FEIT = "fact_inschrijving"
# Scenario als de aanroeper er geen opgeeft; nooit afgeleid uit een pad (#176).
SCENARIO_ONBEKEND = "unknown"


def _check_orphaned_facts_structured(star: dict[str, pl.DataFrame]) -> dict[str, Any]:
    """Core check: detail-feiten for orphaned rows. Returns structured dict."""
    inschrijvingen = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    orphaned_facts: dict[str, Any] = {}

    for naam, feit in sorted(star.items()):
        if not naam.startswith(_FEIT_PREFIX) or naam == _CENTRAAL_FEIT:
            continue
        if feit.is_empty():
            continue

        gekoppeld = filter_detail_op_inschrijvingen(feit, inschrijvingen).height
        wees = feit.height - gekoppeld
        if wees == 0:
            continue

        wees_pct = wees / feit.height if feit.height > 0 else 0.0
        orphaned_facts[naam] = {
            "total_rows": feit.height,
            "orphaned_rows": wees,
            "orphaned_pct": round(wees_pct, 4),
        }

    return {"orphaned_facts": orphaned_facts}


def controleer_koppelingen(star: dict[str, pl.DataFrame]) -> list[str]:
    """Wrapper: gestructureerde check naar strings voor app-display."""
    result = _check_orphaned_facts_structured(star)
    meldingen: list[str] = []

    for naam, metrics in result.get("orphaned_facts", {}).items():
        pct_val = metrics.get("orphaned_pct", 0) * 100
        wees = metrics.get("orphaned_rows", 0)
        totaal = metrics.get("total_rows", 0)

        if wees == totaal:
            meldingen.append(
                f"{naam}: geen enkele rij ({totaal}) koppelt aan {_CENTRAAL_FEIT}"
            )
        else:
            meldingen.append(
                f"{naam}: {wees} van {totaal} rijen ({pct_val:.0f}%) "
                f"koppelen niet aan {_CENTRAAL_FEIT}"
            )

    return meldingen


def _check_key_duplicates_structured(star: dict[str, pl.DataFrame]) -> dict[str, Any]:
    """Core: period key duplicates in fact_inschrijving. Structured dict output."""
    feit = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    key_dupes = {"duplicate_keys": 0, "affected_rows": 0, "by_delivery": {}}

    if not set(_PERIODE_SLEUTEL) <= set(feit.columns):
        return {"key_duplicates": key_dupes}

    gevuld = feit.drop_nulls(_PERIODE_SLEUTEL)
    dubbel = gevuld.filter(gevuld.select(_PERIODE_SLEUTEL).is_duplicated())

    if dubbel.is_empty():
        return {"key_duplicates": key_dupes}

    key_dupes["duplicate_keys"] = dubbel.select(_PERIODE_SLEUTEL).n_unique()
    key_dupes["affected_rows"] = dubbel.height

    if "levering" in dubbel.columns:
        per_lev = dubbel.group_by("levering").len().sort("levering")
        key_dupes["by_delivery"] = {
            lev: int(n) for lev, n in per_lev.iter_rows()
        }

    return {"key_duplicates": key_dupes}


def controleer_sleuteluniciteit(star: dict[str, pl.DataFrame]) -> list[str]:
    """Wrapper: gestructureerde check naar strings voor app-display."""
    result = _check_key_duplicates_structured(star)
    key_dupes = result.get("key_duplicates", {})

    if key_dupes.get("duplicate_keys", 0) == 0:
        return []

    aantal = key_dupes["duplicate_keys"]
    sleutels = "sleutel komt" if aantal == 1 else "sleutels komen"
    melding = f"{_CENTRAAL_FEIT}: {aantal} {sleutels} meer dan één keer voor"

    by_delivery = key_dupes.get("by_delivery", {})
    if by_delivery:
        melding += (
            " ("
            + ", ".join(f"{lev}: {n} rijen" for lev, n in by_delivery.items())
            + ")"
        )

    return [melding]


def _check_niveau_structured(star: dict[str, pl.DataFrame]) -> dict[str, Any]:
    """Core: unknown or missing niveau. Structured dict output."""
    feit = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    niveau_issues = {"unknown_code": 0, "sbb_without_level": 0, "total": 0}

    if _NIVEAU_HERKOMST not in feit.columns or feit.is_empty():
        return {"niveau_issues": niveau_issues}

    herkomst = feit[_NIVEAU_HERKOMST]
    onbekend = int((herkomst == _NIVEAU_ONBEKEND).sum())
    sbb_nvt = int((herkomst == _NIVEAU_SBB_NVT).sum())

    return {
        "niveau_issues": {
            "unknown_code": onbekend,
            "sbb_without_level": sbb_nvt,
            "total": onbekend + sbb_nvt,
        }
    }


def controleer_niveau(star: dict[str, pl.DataFrame]) -> list[str]:
    """Wrapper: gestructureerde check naar strings voor app-display."""
    result = _check_niveau_structured(star)
    niveau_issues = result.get("niveau_issues", {})

    if niveau_issues.get("total", 0) == 0:
        return []

    onbekend = niveau_issues.get("unknown_code", 0)
    sbb_nvt = niveau_issues.get("sbb_without_level", 0)
    total = niveau_issues.get("total", 0)
    feit = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    feit_height = feit.height if not feit.is_empty() else 0

    return [
        f"{_CENTRAAL_FEIT}: {total} van {feit_height} rijen zonder "
        f"bekend niveau ({onbekend} code onbekend, {sbb_nvt} S-BB zonder niveau); "
        "ze vallen buiten JR/DR"
    ]


def _evaluate_star_checks_status(star_checks: dict[str, Any]) -> tuple[int, int]:
    """Evaluate star-checks; return (errors, warnings).

    Errors: orphaned_facts with pct > 0, key duplicates > 0
    Warnings: niveau_issues > 0, overlapping_deliveries > 0
    """
    errors = 0
    warnings = 0

    # Check orphaned facts
    for _tabla, metrics in star_checks.get("orphaned_facts", {}).items():
        if metrics.get("orphaned_pct", 0) > 0:
            errors += 1

    # Check key duplicates
    if star_checks.get("key_duplicates", {}).get("duplicate_keys", 0) > 0:
        errors += 1

    # Check niveau issues
    if star_checks.get("niveau_issues", {}).get("total", 0) > 0:
        warnings += 1

    # Check overlapping deliveries
    if len(star_checks.get("overlapping_deliveries", [])) > 0:
        warnings += 1

    return errors, warnings


def compile_quality_report(
    star: dict[str, pl.DataFrame],
    deliveries: dict[str, QualityReport] | None = None,
    scenario: str = SCENARIO_ONBEKEND,
) -> dict[str, Any]:
    """Compile quality report for quality.json output.

    Args:
        star: Star schema tables (from build_star)
        deliveries: Per-delivery quality reports (from check_slr_reconciliation)
        scenario: Scenario label (e.g., 'demo', 'prod')

    Returns:
        Dict matching quality.schema.json structure, ready for JSON export.
    """
    deliveries_list = []
    if deliveries:
        for _levering, report in sorted(deliveries.items()):
            deliveries_list.append(report.as_dict())

    # Star-level checks
    star_checks = {
        **_check_orphaned_facts_structured(star),
        **_check_key_duplicates_structured(star),
        **_check_niveau_structured(star),
        **check_overlapping_deliveries(star),
    }

    # Count totals from deliveries
    total_warnings = 0
    total_errors = 0
    inschrijvingen = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    total_inschrijvingen = inschrijvingen.height if not inschrijvingen.is_empty() else 0

    for delivery in deliveries_list:
        total_warnings += len(delivery.get("warnings", []))
        total_errors += len(delivery.get("errors", []))

    # Add star-check findings to totals
    star_errors, star_warnings = _evaluate_star_checks_status(star_checks)
    total_errors += star_errors
    total_warnings += star_warnings

    # Overall status: FAIL if any errors, WARN if warnings, PASS otherwise
    status = "fail" if total_errors > 0 else ("warn" if total_warnings > 0 else "pass")

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "scenario": scenario,
        "deliveries": deliveries_list,
        "star": star_checks,
        "summary": {
            "total_deliveries": len(deliveries_list),
            "total_inschrijvingen": total_inschrijvingen,
            "total_warnings": total_warnings,
            "total_errors": total_errors,
            "status": status,
        },
    }


def write_quality_json(
    report: dict[str, Any],
    output_path: Path | str,
) -> Path:
    """Write quality report to JSON file.

    Args:
        report: Quality report dict (from compile_quality_report)
        output_path: Path to write quality.json to

    Returns:
        Path to written file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w") as f:
        json.dump(report, f, indent=2, default=str)

    return output_path


def check_overlapping_deliveries(star: dict[str, pl.DataFrame]) -> dict[str, Any]:
    """Detect persoon×inschrijving×schooljaar appearing in multiple deliveries.

    Returns structured dict with overlaps: [{key, deliveries, count}, ...]
    """
    feit = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    overlaps = []

    if feit.is_empty() or "levering" not in feit.columns:
        return {"overlapping_deliveries": overlaps}

    # Group by (persoon, inschrijving, schooljaar) and count deliveries
    key_cols = ["_persoon_id", "Inschrijvingvolgnummer", "Studiejaar"]
    required = [c for c in key_cols if c in feit.columns]

    if not required:
        return {"overlapping_deliveries": overlaps}

    # Aggregate: count distinct deliveries per key
    grouped = feit.group_by(required).agg(
        pl.col("levering").n_unique().alias("_num_deliveries"),
        pl.col("levering").unique().sort().alias("_deliveries"),
    ).filter(pl.col("_num_deliveries") > 1)

    for row in grouped.iter_rows(named=True):
        key = "|".join(
            str(row.get(c, "")) for c in required
        )
        deliveries = sorted(set(row["_deliveries"]))  # type: ignore
        overlaps.append({
            "key": key,
            "deliveries": deliveries,
            "count": row["_num_deliveries"],
        })

    return {"overlapping_deliveries": sorted(overlaps, key=lambda x: x["key"])}
