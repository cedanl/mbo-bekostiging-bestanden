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

from mbo_bekostiging_bestanden import ernst
from mbo_bekostiging_bestanden.canonicalisatie import INSCHRIJVING, REGEL
from mbo_bekostiging_bestanden.filters import (
    _PERIODE_SLEUTEL,
    detail_zonder_inschrijving,
)
from mbo_bekostiging_bestanden.niveau import KOLOM as _NIVEAU_HERKOMST
from mbo_bekostiging_bestanden.niveau import ONBEKEND as _NIVEAU_ONBEKEND
from mbo_bekostiging_bestanden.niveau import SBB_NVT as _NIVEAU_SBB_NVT
from mbo_bekostiging_bestanden.schooljaar import (
    FEIT as SCHOOLJAAR_FEIT,
)
from mbo_bekostiging_bestanden.schooljaar import (
    GRAIN as SCHOOLJAAR_GRAIN,
)
from mbo_bekostiging_bestanden.schooljaar import (
    HOOFDINSCHRIJVING,
    HOOFDINSCHRIJVING_GROEP,
)
from mbo_bekostiging_bestanden.transform import BRON, BRON_TBGI

# Icoon per SLR-status voor de app-weergave.
_SLR_STATUS_ICONS = {
    "match": "✅",
    "mismatch": "❌",
    "unknown": "⚠️",
    "not_applicable": "ℹ️",
}


def slr_status_icoon(status: str | None) -> str:
    """Vertaal een SLR-status naar een weergave-icoon.

    Alles wat geen gedefinieerde status is (incl. ``None`` en oude
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


# Waarschuwing per onderdeel van ``ingest.inventariseer_regels`` (#120).
_REGELINVENTARIS_MELDINGEN = {
    "onbekende_recordtypes": "Regels met onbekend recordtype niet ingelezen",
    "velden_voorbij_schema": "Regels met gevulde velden voorbij het schema",
    "spiegel_afwijkingen": (
        "Posities buiten het PvE verschillen van het veld dat ze meestal "
        "herhalen; betekenis onbekend, waarde bewaard in de brondata"
    ),
}


@dataclass
class QualityReport:
    """Gestructureerd kwaliteitsrapport per leveringsbestand."""

    levering: str
    schema_type: str
    slr_checks: dict[str, dict[str, int]] = field(default_factory=dict)
    slr_status: str = "unknown"  # match | mismatch | unknown | not_applicable
    parseverlies: dict[str, dict[str, int]] = field(default_factory=dict)
    regelinventaris: dict[str, dict] = field(default_factory=dict)
    domeinafwijkingen: dict[str, dict[str, dict[str, int | str]]] = field(
        default_factory=dict
    )
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

    def meld_regelinventaris(self, inventaris: dict[str, dict]) -> None:
        """Neem op wat de ingest niet inlas (zie ``ingest.inventariseer_regels``)."""
        self.regelinventaris = inventaris
        for sleutel, tekst in _REGELINVENTARIS_MELDINGEN.items():
            if inventaris.get(sleutel):
                self.warnings.append(f"{tekst}: {inventaris[sleutel]}")

    def meld_domeinafwijkingen(
        self, afwijkingen: dict[str, dict[str, dict[str, int | str]]]
    ) -> None:
        """Neem waarden buiten hun domein op (``controleer_waardedomeinen``).

        Een afwijking met ``ernst == "error"`` (bijv. BRIN, Studiejaar: een
        verschoven recordlayout, #238) meldt in ``errors``; de rest in
        ``warnings``.
        """
        self.domeinafwijkingen = afwijkingen
        for niveau, sleutel in ((ernst.ERROR, "errors"), (ernst.WARNING, "warnings")):
            gefilterd = {
                rt: {
                    veld: info["aantal"]
                    for veld, info in velden.items()
                    if info["ernst"] == niveau
                }
                for rt, velden in afwijkingen.items()
            }
            gefilterd = {rt: velden for rt, velden in gefilterd.items() if velden}
            if gefilterd:
                getattr(self, sleutel).append(
                    "Waarden buiten hun domein (mogelijk verschoven velden): "
                    f"{gefilterd}"
                )

    def as_dict(self) -> dict:
        """Zet rapport om naar dict voor JSON-export."""
        return {
            "levering": self.levering,
            "schema_type": self.schema_type,
            "slr_status": self.slr_status,
            "slr_details": self.slr_checks,
            "parseverlies": self.parseverlies,
            "regelinventaris": self.regelinventaris,
            "domeinafwijkingen": self.domeinafwijkingen,
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


def lees_leveringsrapport(pad: Path, levering: str) -> QualityReport:
    """Lees het per-levering ``quality.json`` uit een prepared-map.

    ``levering`` is het label uit de ster (zie
    :func:`~mbo_bekostiging_bestanden.stack.leveringslabels`) en vervangt het
    label in het bestand, zodat ``quality.json`` en de feiten dezelfde
    leveringsnamen gebruiken (#188). Ontbreekt het bestand, dan volgt een
    rapport met een waarschuwing i.p.v. een stil ontbrekende levering.
    """
    if not pad.exists():
        return QualityReport(
            levering=levering,
            schema_type="unknown",
            warnings=[f"Geen kwaliteitsrapport gevonden: {pad.name} ontbreekt"],
        )
    data = json.loads(pad.read_text(encoding="utf-8"))
    return QualityReport(
        levering=levering,
        schema_type=data.get("schema_type", "unknown"),
        slr_status=data.get("slr_status", "unknown"),
        slr_checks=data.get("slr_details", {}),
        parseverlies=data.get("parseverlies", {}),
        regelinventaris=data.get("regelinventaris", {}),
        domeinafwijkingen=data.get("domeinafwijkingen", {}),
        warnings=data.get("warnings", []),
        errors=data.get("errors", []),
    )


def check_slr_reconciliation(
    frames: dict[str, pl.DataFrame],
    levering: str,
    schema_naam: str | None = None,
) -> QualityReport:
    """Reconcilieer geparste recordaantallen met SLR-controletotalen.

    SLR (sluitrecord) bevat DUO's eigen controletotalen per recordtype.
    Returns QualityReport met SLR-match status. TBGI-i kent geen sluitrecord
    (PvE §16): daarvoor is de check ``not_applicable`` in plaats van een
    ``unknown``-waarschuwing (#261).
    """
    report = QualityReport(
        levering=levering,
        schema_type=_bepaal_schema_type(frames),
    )

    if schema_naam == "tbgi":
        report.slr_status = "not_applicable"
        return report

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
_META_CANONICALISATIE = "meta_canonicalisatie"
_META_KOPPELKEUZES = "meta_koppelkeuzes"
# Scenario als de aanroeper er geen opgeeft; nooit afgeleid uit een pad (#176).
SCENARIO_ONBEKEND = "unknown"


# Detail-feiten waarvan de parent in fact_inschrijving optioneel is (#196): welke
# wees-rijen verklaard zijn, en waarom. Alleen TBG-i: een GRONDSLAG-BID zonder
# inschrijving mist zijn DIP en is een bronfout (#258).
_OPTIONELE_PARENT = {
    # PvE §16.1: TBG-i voor bekostigingsjaar T bevat de diploma's behaald in
    # kalenderjaar T-2, los van de inschrijvingen in studiejaar T-2.
    "fact_bekostiging_diploma": (
        pl.col(BRON) == BRON_TBGI,
        "TBG-i levert diploma's van het kalenderjaar los van de inschrijvingen "
        "in het bestand (PvE §16.1)",
    ),
}


def _check_orphaned_facts_structured(star: dict[str, pl.DataFrame]) -> dict[str, Any]:
    """Per detail-feit: rijen zonder inschrijving, en hoeveel daarvan verklaard zijn."""
    inschrijvingen = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    orphaned_facts: dict[str, Any] = {}

    for naam, feit in sorted(star.items()):
        if not naam.startswith(_FEIT_PREFIX) or naam == _CENTRAAL_FEIT:
            continue
        if feit.is_empty():
            continue

        wees = detail_zonder_inschrijving(feit, inschrijvingen)
        if wees.is_empty():
            continue

        verklaard, reden = _OPTIONELE_PARENT.get(naam, (pl.lit(False), None))
        orphaned_facts[naam] = {
            "total_rows": feit.height,
            "orphaned_rows": wees.height,
            "orphaned_pct": round(wees.height / feit.height, 4),
            "explained_rows": wees.filter(verklaard).height,
            "explanation": reden,
        }

    return {"orphaned_facts": orphaned_facts}


def controleer_koppelingen(star: dict[str, pl.DataFrame]) -> list[str]:
    """Eén melding per detail-feit met wees-rijen, voor weergave in de app."""
    meldingen: list[str] = []
    wees_per_feit = _check_orphaned_facts_structured(star)["orphaned_facts"]
    for naam, metrics in wees_per_feit.items():
        wees = metrics["orphaned_rows"]
        totaal = metrics["total_rows"]
        if wees == totaal:
            melding = f"{naam}: geen enkele rij ({totaal}) koppelt aan {_CENTRAAL_FEIT}"
        else:
            melding = (
                f"{naam}: {wees} van {totaal} rijen "
                f"({metrics['orphaned_pct'] * 100:.0f}%) "
                f"koppelen niet aan {_CENTRAAL_FEIT}"
            )
        if metrics["explained_rows"]:
            melding += (
                f"; {metrics['explained_rows']} verklaard: {metrics['explanation']}"
            )
        meldingen.append(melding)
    return meldingen


@dataclass(frozen=True)
class _Uniciteit:
    """Contract: ``sleutel`` is uniek in ``feit`` (optioneel alleen waar ``alleen``)."""

    feit: str
    sleutel: tuple[str, ...]
    melding: str
    alleen: str | None = None


# Naam → uniciteitscontract. Een geschonden contract is een error (#122, #200).
_UNICITEIT = {
    _CENTRAAL_FEIT: _Uniciteit(
        _CENTRAAL_FEIT, tuple(_PERIODE_SLEUTEL), "{n} {sleutels} meer dan één keer voor"
    ),
    SCHOOLJAAR_FEIT: _Uniciteit(
        SCHOOLJAAR_FEIT,
        tuple(SCHOOLJAAR_GRAIN),
        "{n} {sleutels} meer dan één keer voor",
    ),
    "hoofdinschrijving_per_schooljaar": _Uniciteit(
        SCHOOLJAAR_FEIT,
        tuple(HOOFDINSCHRIJVING_GROEP),
        "{n} persoon × instelling × schooljaar met meer dan één hoofdinschrijving",
        alleen=HOOFDINSCHRIJVING,
    ),
}


def _dubbele_sleutels(star: dict[str, pl.DataFrame], contract: _Uniciteit) -> dict:
    sleutel = list(contract.sleutel)
    resultaat: dict[str, Any] = {
        "feit": contract.feit,
        "sleutel": sleutel,
        "duplicate_keys": 0,
        "affected_rows": 0,
        "by_delivery": {},
    }
    feit = star.get(contract.feit, pl.DataFrame())
    nodig = {*sleutel, *([contract.alleen] if contract.alleen else [])}
    if not nodig <= set(feit.columns):
        return resultaat
    if contract.alleen:
        feit = feit.filter(pl.col(contract.alleen))
    gevuld = feit.drop_nulls(sleutel)
    dubbel = gevuld.filter(gevuld.select(sleutel).is_duplicated())
    if dubbel.is_empty():
        return resultaat
    resultaat["duplicate_keys"] = dubbel.select(sleutel).n_unique()
    resultaat["affected_rows"] = dubbel.height
    if "levering" in dubbel.columns:
        per_lev = dubbel.group_by("levering").len().sort("levering")
        resultaat["by_delivery"] = {lev: int(n) for lev, n in per_lev.iter_rows()}
    return resultaat


def _check_key_duplicates_structured(star: dict[str, pl.DataFrame]) -> dict[str, Any]:
    """Per uniciteitscontract: aantal dubbele sleutels en getroffen rijen."""
    return {
        "key_duplicates": {
            naam: _dubbele_sleutels(star, contract)
            for naam, contract in _UNICITEIT.items()
        }
    }


def controleer_sleuteluniciteit(star: dict[str, pl.DataFrame]) -> list[str]:
    """Eén melding per geschonden uniciteitscontract, voor weergave in de app."""
    meldingen = []
    for naam, dubbel in _check_key_duplicates_structured(star)[
        "key_duplicates"
    ].items():
        n = dubbel["duplicate_keys"]
        if n == 0:
            continue
        tekst = _UNICITEIT[naam].melding.format(
            n=n, sleutels="sleutel komt" if n == 1 else "sleutels komen"
        )
        melding = f"{dubbel['feit']}: {tekst}"
        if dubbel["by_delivery"]:
            melding += (
                " ("
                + ", ".join(
                    f"{lev}: {r} rijen" for lev, r in dubbel["by_delivery"].items()
                )
                + ")"
            )
        meldingen.append(melding)
    return meldingen


def _check_niveau_structured(star: dict[str, pl.DataFrame]) -> dict[str, Any]:
    """Inschrijvingen zonder bekend niveau, naar oorzaak (#130)."""
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
    """Melding over inschrijvingen zonder bekend niveau, voor de app."""
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


ERNST_ERROR, ERNST_WARNING, ERNST_INFO = ernst.ERROR, ernst.WARNING, ernst.INFO
_BRON_STER = "ster"


@dataclass(frozen=True)
class Melding:
    """Eén bevinding uit ``quality.json``: ernst, bron (levering of ster), tekst."""

    ernst: str
    bron: str
    tekst: str


def _ster_meldingen(star: dict[str, Any]) -> list[Melding]:
    """Bevindingen van de star-checks, elk met zijn ernst.

    Error: onverklaarde wees-feiten, elk geschonden uniciteitscontract, overlap
    die na canonicalisatie (#174) in de ster blijft (telt dubbel).
    Warning: onbekend niveau, meervoudige matches bij koppelingen (#209),
    leveringen zonder waarneembare peildatum (#211).
    Info: verklaarde wees-rijen (#196), vervangen leveringen (#174).
    """
    meldingen: list[Melding] = []

    def melding(ernst: str, tekst: str) -> None:
        meldingen.append(Melding(ernst, _BRON_STER, tekst))

    for naam, wees in star.get("orphaned_facts", {}).items():
        onverklaard = wees["orphaned_rows"] - wees["explained_rows"]
        if onverklaard > 0:
            melding(
                ERNST_ERROR,
                f"{naam}: {onverklaard} van {wees['total_rows']} rijen zonder "
                f"inschrijving in {_CENTRAAL_FEIT}",
            )
        if wees["explained_rows"]:
            melding(
                ERNST_INFO,
                f"{naam}: {wees['explained_rows']} rijen zonder inschrijving, "
                f"verklaard: {wees['explanation']}",
            )
    for naam, dubbel in star.get("key_duplicates", {}).items():
        if dubbel.get("duplicate_keys", 0) > 0:
            melding(
                ERNST_ERROR,
                f"{naam}: {dubbel['duplicate_keys']} dubbele sleutels "
                f"({', '.join(dubbel.get('sleutel', []))})",
            )
    if star.get("overlapping_deliveries"):
        melding(
            ERNST_ERROR,
            f"{len(star['overlapping_deliveries'])} overlappende leveringen na "
            "canonicalisatie",
        )
    if star.get("niveau_issues", {}).get("total", 0) > 0:
        melding(
            ERNST_WARNING,
            f"{star['niveau_issues']['total']} inschrijvingen zonder bekend niveau",
        )
    meervoudig = [k for k in star.get("join_keuzes", []) if k["meervoudige_sleutels"]]
    if meervoudig:
        melding(
            ERNST_WARNING,
            "meervoudige matches bij koppelen: "
            + ", ".join(
                f"{k['koppeling']} ({k['meervoudige_sleutels']})" for k in meervoudig
            ),
        )
    if star.get("leveringen_zonder_schooljaar"):
        melding(
            ERNST_WARNING,
            "leveringen zonder waarneembare peildatum: "
            + ", ".join(r["levering"] for r in star["leveringen_zonder_schooljaar"]),
        )
    vervangen = star.get("canonicalisatie", {}).get("vervangen_inschrijvingen", 0)
    if vervangen:
        melding(
            ERNST_INFO,
            f"{vervangen} inschrijvingen vervangen door een recentere levering",
        )
    return meldingen


def kwaliteitsmeldingen(rapport: dict[str, Any]) -> list[Melding]:
    """Alle bevindingen uit een ``quality.json``-rapport, per levering en uit de ster.

    De ``summary`` van :func:`compile_quality_report` telt precies de meldingen
    met ernst error en warning hieruit.
    """
    meldingen = [
        Melding(ernst, levering["levering"], tekst)
        for levering in rapport.get("deliveries", [])
        for ernst, sleutel in ((ERNST_ERROR, "errors"), (ERNST_WARNING, "warnings"))
        for tekst in levering.get(sleutel, [])
    ]
    return meldingen + _ster_meldingen(rapport.get("star", {}))


def _evaluate_star_checks_status(star_checks: dict[str, Any]) -> tuple[int, int]:
    """Aantal (errors, warnings) in de star-checks; zie :func:`_ster_meldingen`."""
    ernsten = [m.ernst for m in _ster_meldingen(star_checks)]
    return ernsten.count(ERNST_ERROR), ernsten.count(ERNST_WARNING)


def compile_quality_report(
    star: dict[str, pl.DataFrame],
    deliveries: dict[str, QualityReport] | None = None,
    scenario: str = SCENARIO_ONBEKEND,
) -> dict[str, Any]:
    """Stel ``quality.json`` samen voor een ster-run (``docs/quality.schema.json``).

    Args:
        star:       Tabellen van :func:`~mbo_bekostiging_bestanden.star.build_star`.
        deliveries: Rapport per levering (label zoals in de ster).
        scenario:   Label voor de run, bijv. ``"demo"`` of ``"prod"``.
    """
    deliveries_list = []
    if deliveries:
        for _levering, report in sorted(deliveries.items()):
            deliveries_list.append(report.as_dict())

    star_checks = {
        **_check_orphaned_facts_structured(star),
        **_check_key_duplicates_structured(star),
        **_check_niveau_structured(star),
        **check_overlapping_deliveries(star),
        **_check_canonicalisatie_structured(star),
        **_check_join_keuzes_structured(star),
        **_check_leveringen_zonder_schooljaar(star),
    }

    total_warnings = 0
    total_errors = 0
    inschrijvingen = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    total_inschrijvingen = inschrijvingen.height if not inschrijvingen.is_empty() else 0

    for delivery in deliveries_list:
        total_warnings += len(delivery.get("warnings", []))
        total_errors += len(delivery.get("errors", []))

    star_errors, star_warnings = _evaluate_star_checks_status(star_checks)
    total_errors += star_errors
    total_warnings += star_warnings

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
    """Inschrijvingen die na canonicalisatie nog in meerdere leveringen staan.

    Een inschrijving is ``BRIN × _persoon_id × Inschrijvingvolgnummer`` (zie
    :mod:`~mbo_bekostiging_bestanden.canonicalisatie`). Na canonicalisatie hoort
    elke inschrijving uit precies één levering te komen; elke treffer hier is
    dubbeltelling in de output.

    Returns:
        ``{"overlapping_deliveries": [{key, deliveries, count}, ...]}``
    """
    feit = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    if not {"levering", *INSCHRIJVING} <= set(feit.columns):
        return {"overlapping_deliveries": []}

    grouped = (
        feit.group_by(INSCHRIJVING)
        .agg(pl.col("levering").unique().sort().alias("deliveries"))
        .filter(pl.col("deliveries").list.len() > 1)
    )
    overlaps = [
        {
            "key": "|".join(str(row[c]) for c in INSCHRIJVING),
            "deliveries": row["deliveries"],
            "count": len(row["deliveries"]),
        }
        for row in grouped.iter_rows(named=True)
    ]
    return {"overlapping_deliveries": sorted(overlaps, key=lambda x: x["key"])}


def _check_canonicalisatie_structured(
    star: dict[str, pl.DataFrame],
) -> dict[str, Any]:
    """Samenvatting van ``meta_canonicalisatie``: wat is vervangen en waarom."""
    meta = star.get(_META_CANONICALISATIE, pl.DataFrame())
    per_levering = meta.to_dicts() if not meta.is_empty() else []
    return {
        "canonicalisatie": {
            "regel": REGEL,
            "vervangen_inschrijvingen": sum(r["inschrijvingen"] for r in per_levering),
            "vervangen_isp_perioden": sum(r["isp_perioden"] for r in per_levering),
            "per_levering": per_levering,
        }
    }


def _check_join_keuzes_structured(star: dict[str, pl.DataFrame]) -> dict[str, Any]:
    """Koppelingen met meer dan één kandidaat per sleutel (``meta_koppelkeuzes``)."""
    keuzes = star.get(_META_KOPPELKEUZES, pl.DataFrame())
    if keuzes.is_empty():
        return {"join_keuzes": []}
    return {"join_keuzes": keuzes.filter(pl.col("meervoudige_sleutels") > 0).to_dicts()}


def _check_leveringen_zonder_schooljaar(
    star: dict[str, pl.DataFrame],
) -> dict[str, Any]:
    """Leveringen met inschrijvingen maar zonder rij in de schooljaar-fact.

    Zonder schooljaar-fact in de ster (niet gebouwd) valt er niets te melden.
    """
    inschrijvingen = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    jaren = star.get(SCHOOLJAAR_FEIT)
    if jaren is None or "levering" not in inschrijvingen.columns:
        return {"leveringen_zonder_schooljaar": []}
    per_levering = inschrijvingen.group_by("levering").agg(
        pl.len().alias("inschrijvingen")
    )
    if "levering" in jaren.columns:
        per_levering = per_levering.join(
            jaren.select("levering").unique(), on="levering", how="anti"
        )
    return {"leveringen_zonder_schooljaar": per_levering.sort("levering").to_dicts()}
