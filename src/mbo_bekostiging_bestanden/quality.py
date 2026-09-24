"""Datakwaliteitscontroles: SLR-reconciliatie, wees-feiten en waarschuwingen.

Na validatie van schema: detecteer stille dataverlies en gedeeltelijke verwerking.
Rapporteer problemen gestructureerd zonder te faillen op waarschuwingen.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from mbo_bekostiging_bestanden.filters import filter_detail_op_inschrijvingen

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


def controleer_koppelingen(star: dict[str, pl.DataFrame]) -> list[str]:
    """Signaleer detail-feiten waarvan rijen niet aan ``fact_inschrijving`` koppelen.

    Een wees-rij hangt los van het datamodel (bijv. bekostiging uit een andere
    levering of instelling dan de inschrijvingen) en telt stil niet mee in
    analyses per inschrijving.  Koppelt via dezelfde sleutel als de app-filters.
    Geeft één melding per feit met wees-rijen; lege feiten worden overgeslagen.
    """
    inschrijvingen = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    meldingen: list[str] = []
    for naam, feit in sorted(star.items()):
        if not naam.startswith(_FEIT_PREFIX) or naam == _CENTRAAL_FEIT:
            continue
        if feit.is_empty():
            continue
        gekoppeld = filter_detail_op_inschrijvingen(feit, inschrijvingen).height
        wees = feit.height - gekoppeld
        if wees == 0:
            continue
        if gekoppeld == 0:
            meldingen.append(
                f"{naam}: geen enkele rij ({feit.height}) koppelt aan {_CENTRAAL_FEIT}"
            )
        else:
            meldingen.append(
                f"{naam}: {wees} van {feit.height} rijen ({wees / feit.height:.0%}) "
                f"koppelen niet aan {_CENTRAAL_FEIT}"
            )
    return meldingen
