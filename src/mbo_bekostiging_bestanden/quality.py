"""Datakwaliteitscontroles: SLR-reconciliatie en waarschuwingen.

Na validatie van schema: detecteer stille dataverlies en gedeeltelijke verwerking.
Rapporteer problemen gestructureerd zonder te faillen op waarschuwingen.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

# Icoon per tri-state SLR-status voor de app-weergave.
_SLR_STATUS_ICONS = {"match": "✅", "mismatch": "❌", "unknown": "⚠️"}


def slr_status_icoon(status: str | None) -> str:
    """Vertaal een SLR-status naar een weergave-icoon.

    Alles wat geen gedefinieerde tri-state waarde is (incl. ``None`` en oude
    ``quality.json``-bestanden zonder ``slr_status``) valt veilig terug op ⚠️.
    """
    return _SLR_STATUS_ICONS.get(status, "⚠️")


@dataclass
class QualityReport:
    """Gestructureerd kwaliteitsrapport per leveringsbestand."""

    levering: str
    schema_type: str
    slr_checks: dict[str, dict[str, int]] = None  # type: ignore
    slr_status: str = "unknown"  # match | mismatch | unknown
    warnings: list[str] = None  # type: ignore
    errors: list[str] = None  # type: ignore

    def __post_init__(self):
        if self.slr_checks is None:
            self.slr_checks = {}
        if self.warnings is None:
            self.warnings = []
        if self.errors is None:
            self.errors = []

    def as_dict(self) -> dict:
        """Zet rapport om naar dict voor JSON-export."""
        return {
            "levering": self.levering,
            "schema_type": self.schema_type,
            "slr_status": self.slr_status,
            "slr_details": self.slr_checks,
            "warnings": self.warnings,
            "errors": self.errors,
        }


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
        schema_type="unknown",
    )

    # Bepaal schema-type op basis van beschikbare recordtypes
    if "VLP" in frames and frames["VLP"].shape[0] > 0:
        vlp = frames["VLP"].row(0, named=True) if frames["VLP"].shape[0] > 0 else {}
        if "GRONDSLAG" in vlp.get("Recordsoort", ""):
            report.schema_type = "grondslag"
        else:
            report.schema_type = "ro"

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
        report.warnings.append(
            f"SLR-mismatch: {'; '.join(mismatches)}"
        )
    else:
        report.slr_status = "match"
        report.warnings.append("SLR-reconciliatie: OK")

    return report


def quality_report_summary(reports: list[QualityReport]) -> str:
    """Maak tekstsamenvatting van kwaliteitsrapporten."""
    lines = []
    for r in reports:
        status_icon = (
            "✓" if r.slr_status == "match"
            else "⚠" if r.slr_status == "unknown"
            else "✗"
        )
        lines.append(
            f"{status_icon} {r.levering}: {len(r.warnings)} waarschuwing(en)"
        )
        for w in r.warnings:
            lines.append(f"  ⚠ {w}")
        for e in r.errors:
            lines.append(f"  ✗ {e}")
    return "\n".join(lines)
