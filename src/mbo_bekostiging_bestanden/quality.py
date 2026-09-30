"""Datakwaliteitscontroles: SLR, parseverlies, wees-feiten, sleutels, niveau.

Na validatie van schema: detecteer stille dataverlies en gedeeltelijke verwerking.
Alle controles retourneren gestructureerde dicts (JSON-serialiseerbaar).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from mbo_bekostiging_bestanden import ernst
from mbo_bekostiging_bestanden.canonicalisatie import INSCHRIJVING, REGEL
from mbo_bekostiging_bestanden.contracts import (
    BRON,
    BRON_BID,
    BRON_BII,
    BRON_ISP,
    BRON_TBGI,
    DETAIL_GRAIN,
    HOOFDINSCHRIJVING,
    HOOFDINSCHRIJVING_GROEP,
    KOPPELSTATUS,
    KOPPELSTATUS_BINNEN,
    KOPPELSTATUS_GEEN_INSCHRIJVING,
    PERIODE_SLEUTEL,
    SCHOOLJAAR_FEIT,
    SCHOOLJAAR_GRAIN,
    VEROUDERD_TOT,
    VEROUDERDE_KOLOMMEN,
)
from mbo_bekostiging_bestanden.filters import detail_zonder_inschrijving
from mbo_bekostiging_bestanden.koppelingen import UNIEK
from mbo_bekostiging_bestanden.metadata import pve_bron
from mbo_bekostiging_bestanden.niveau import KOLOM as _NIVEAU_HERKOMST
from mbo_bekostiging_bestanden.niveau import ONBEKEND as _NIVEAU_ONBEKEND
from mbo_bekostiging_bestanden.niveau import SBB_NVT as _NIVEAU_SBB_NVT
from mbo_bekostiging_bestanden.provenance import run_provenance
from mbo_bekostiging_bestanden.referentiedata import (
    OPLEIDINGSREFERENTIES,
    bekende_opleidingscodes,
)
from mbo_bekostiging_bestanden.referentiedata import TABEL as _META_REFERENTIEDATA

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


# Waarschuwing per onderdeel van ``ingest.inventariseer_regels`` (#120) en
# ``ingest.inventariseer_xml_elementen`` (#324).
_REGELINVENTARIS_MELDINGEN = {
    "onbekende_xml_elementen": "XML-elementen buiten het schema niet ingelezen",
    "spiegel_afwijkingen": (
        "Posities buiten het PvE verschillen van het veld dat ze meestal "
        "herhalen; betekenis onbekend, waarde bewaard in de brondata"
    ),
}


class KwaliteitsFout(Exception):
    """De kwaliteitsstatus van een run is ``fail`` en de aanroeper staat dat niet toe.

    ``quality.json`` is op dat moment al geschreven, zodat de oorzaak leesbaar blijft.
    """


def lees_status(quality_json: Path | str) -> tuple[str, int]:
    """``(status, aantal errors)`` uit een geschreven ``quality.json``."""
    samenvatting = json.loads(Path(quality_json).read_text(encoding="utf-8"))["summary"]
    return samenvatting["status"], samenvatting["total_errors"]


# Deelaantallen van een domeinafwijking en hun tekst in de melding. Lege
# waarden apart sinds #320; buiten de geldigheidsperiode, of niet controleerbaar
# bij een ontbrekende peildatum, sinds #325.
_DEELAANTALLEN = {
    "leeg": "waarvan leeg",
    "buiten_geldigheid": "waarvan buiten hun geldigheid",
    "zonder_peildatum": "zonder peildatum voor de geldigheid",
}


def _aantal_tekst(afwijking: dict[str, int | str]) -> int | str:
    """Aantal afwijkende waarden, met de deelaantallen apart benoemd."""
    delen = [
        f"{tekst}: {afwijking[sleutel]}"
        for sleutel, tekst in _DEELAANTALLEN.items()
        if afwijking.get(sleutel)
    ]
    if not delen:
        return afwijking["aantal"]
    return f"{afwijking['aantal']} ({'; '.join(delen)})"


# Conformiteit (#331): wat de uitkomst betekent, naast of ze technisch klopt.
# JR/DR zijn proxy's tot #296 besloten is; de waarde staat hier op één plek.
INDICATOREN_STATUS = "proxy"
# Manifest-hash en upstream-check van de PvE-bron draaien in CI (#364, #299);
# `test_pve_bron.py` en de `pve-upstream`-workflow breken zodra de bron afwijkt.
PVE_BRON_INTEGRITEIT = "pass"
# Veldconformiteit en businessregelconformiteit nog niet formeel afgetekend (#364).
PVE_INHOUDELIJKE_CONFORMITEIT = "niet_beoordeeld"
# DUO heeft niet bevestigd dat het omgenummerde GRONDSLAG-PGN over studiejaren
# gelijk blijft (#128); de koppeling neemt aan van wel.
PGN_STABILITEIT = "onbekend"
PROFIEL_BRONDATA = "brondata"
PROFIEL_GEPSEUDONIMISEERD = "gepseudonimiseerd"


@dataclass
class QualityReport:
    """Gestructureerd kwaliteitsrapport per leveringsbestand."""

    levering: str
    schema_type: str
    slr_checks: dict[str, dict[str, int]] = field(default_factory=dict)
    slr_status: str = "unknown"  # match | mismatch | unknown | not_applicable
    parseverlies: dict[str, dict[str, int]] = field(default_factory=dict)
    regelinventaris: dict[str, dict] = field(default_factory=dict)
    # Gekozen layout per recordtype met varianten (``ingest.layoutvarianten``).
    layoutvarianten: dict[str, dict] = field(default_factory=dict)
    domeinafwijkingen: dict[str, dict[str, dict[str, int | str]]] = field(
        default_factory=dict
    )
    # Schemavelden per soort domeindekking (``waardenlijsten.dekkingsoverzicht``).
    domeindekking: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Naam, sha256 en PvE-versie van het ruwe bestand (#300); None in rapporten
    # van vóór #300.
    bronbestand: dict[str, str] | None = None

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
        """Neem de spiegelafwijkingen op (zie ``ingest.inventariseer_regels``)."""
        self.regelinventaris = inventaris
        for sleutel, tekst in _REGELINVENTARIS_MELDINGEN.items():
            if inventaris.get(sleutel):
                self.warnings.append(f"{tekst}: {inventaris[sleutel]}")

    def meld_domeinafwijkingen(
        self, afwijkingen: dict[str, dict[str, dict[str, int | str]]]
    ) -> None:
        """Neem waarden buiten hun domein op (``controleer_waardedomeinen``).

        Een afwijking met ``ernst == "error"`` (bijv. BRIN, Studiejaar: een
        verschoven recordlayout, #238; lege verplichte waarden, #320) meldt in
        ``errors``; de rest in ``warnings``.
        """
        self.domeinafwijkingen = afwijkingen
        for niveau, sleutel in ((ernst.ERROR, "errors"), (ernst.WARNING, "warnings")):
            gefilterd = {
                rt: {
                    veld: _aantal_tekst(info)
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
        return {
            "levering": self.levering,
            "schema_type": self.schema_type,
            "slr_status": self.slr_status,
            "slr_details": self.slr_checks,
            "parseverlies": self.parseverlies,
            "regelinventaris": self.regelinventaris,
            "layoutvarianten": self.layoutvarianten,
            "domeinafwijkingen": self.domeinafwijkingen,
            "domeindekking": self.domeindekking,
            "warnings": self.warnings,
            "errors": self.errors,
            "bronbestand": self.bronbestand,
            "privacyprofiel": PROFIEL_BRONDATA,
        }


def tel_parseverlies(
    ruw: dict[str, pl.DataFrame], getypeerd: dict[str, pl.DataFrame]
) -> dict[str, dict[str, int]]:
    """Alleen kolommen die van tekst naar een ander type gingen tellen mee: een
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
        layoutvarianten=data.get("layoutvarianten", {}),
        domeinafwijkingen=data.get("domeinafwijkingen", {}),
        domeindekking=data.get("domeindekking", {}),
        warnings=data.get("warnings", []),
        errors=data.get("errors", []),
        bronbestand=data.get("bronbestand"),
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


def _wees_feiten(star: dict[str, pl.DataFrame]) -> dict[str, Any]:
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

    return orphaned_facts


def controleer_koppelingen(star: dict[str, pl.DataFrame]) -> list[str]:
    """Eén melding per detail-feit met wees-rijen, voor weergave in de app."""
    meldingen: list[str] = []
    wees_per_feit = _wees_feiten(star)
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
        _CENTRAAL_FEIT, PERIODE_SLEUTEL, "{n} {sleutels} meer dan één keer voor"
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
    # Detailfeiten op hun business key (#328).
    **{
        feit: _Uniciteit(feit, grain, "{n} {sleutels} meer dan één keer voor")
        for feit, grain in DETAIL_GRAIN.items()
    },
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


def _sleuteldubbelingen(star: dict[str, pl.DataFrame]) -> dict[str, Any]:
    """Per uniciteitscontract: aantal dubbele sleutels en getroffen rijen."""
    return {
        naam: _dubbele_sleutels(star, contract) for naam, contract in _UNICITEIT.items()
    }


def controleer_sleuteluniciteit(star: dict[str, pl.DataFrame]) -> list[str]:
    """Eén melding per geschonden uniciteitscontract, voor weergave in de app."""
    meldingen = []
    for naam, dubbel in _sleuteldubbelingen(star).items():
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


def _niveau_issues(star: dict[str, pl.DataFrame]) -> dict[str, int]:
    """Inschrijvingen zonder bekend niveau, naar oorzaak (#130)."""
    feit = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    if _NIVEAU_HERKOMST not in feit.columns or feit.is_empty():
        return {"unknown_code": 0, "sbb_without_level": 0, "total": 0}

    herkomst = feit[_NIVEAU_HERKOMST]
    onbekend = int((herkomst == _NIVEAU_ONBEKEND).sum())
    sbb_nvt = int((herkomst == _NIVEAU_SBB_NVT).sum())
    return {
        "unknown_code": onbekend,
        "sbb_without_level": sbb_nvt,
        "total": onbekend + sbb_nvt,
    }


def controleer_niveau(star: dict[str, pl.DataFrame]) -> list[str]:
    """Melding over inschrijvingen zonder bekend niveau, voor de app."""
    niveau_issues = _niveau_issues(star)
    total = niveau_issues["total"]
    if total == 0:
        return []

    onbekend = niveau_issues["unknown_code"]
    sbb_nvt = niveau_issues["sbb_without_level"]
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
    """Bevindingen van de star-checks, elk met zijn ernst (zie ``_STER_CHECKS``).

    Een sleutel die in ``star`` ontbreekt (rapport van vóór die check) geeft
    geen meldingen.
    """
    return [
        melding
        for check in _STER_CHECKS
        if check.sleutel in star
        for melding in check.meldingen(star[check.sleutel])
    ]


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
    invoer: dict[str, pl.DataFrame] | None = None,
    fouten_toegestaan: bool = False,
) -> dict[str, Any]:
    """Stel ``quality.json`` samen voor een ster-run (``docs/quality.schema.json``).

    ``deliveries`` gebruikt dezelfde labels als de ster; zonder ``invoer`` blijft de
    dekkingstabel leeg. ``fouten_toegestaan`` komt in de provenance, zodat een run
    die quality-errors negeerde (#289) herkenbaar is.
    """
    deliveries_list = []
    if deliveries:
        for _levering, report in sorted(deliveries.items()):
            deliveries_list.append(report.as_dict())

    star_checks = {
        check.sleutel: check.bereken(star, invoer or {}) for check in _STER_CHECKS
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
        "provenance": run_provenance()
        | {"kwaliteitsfouten_toegestaan": fouten_toegestaan},
        "conformiteit": {
            "pve_versie": pve_bron()["versie"],
            "pve_bron_integriteit": PVE_BRON_INTEGRITEIT,
            "pve_inhoudelijke_conformiteit": PVE_INHOUDELIJKE_CONFORMITEIT,
            "indicatoren": INDICATOREN_STATUS,
            "privacyprofiel": PROFIEL_GEPSEUDONIMISEERD,
            "pgn_stabiliteit": PGN_STABILITEIT,
        },
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
    """Schrijf het kwaliteitsrapport naar ``output_path`` en geef dat pad terug."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    return output_path


def _overlappende_leveringen(star: dict[str, pl.DataFrame]) -> list[dict[str, Any]]:
    """Inschrijvingen die na canonicalisatie nog in meerdere leveringen staan.

    Een inschrijving is ``BRIN × _persoon_id × Inschrijvingvolgnummer`` (zie
    :mod:`~mbo_bekostiging_bestanden.canonicalisatie`). Na canonicalisatie hoort
    elke inschrijving uit precies één levering te komen; elke treffer hier is
    dubbeltelling in de output.

    Returns:
        ``[{key, deliveries, count}, ...]``, gesorteerd op ``key``.
    """
    feit = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    if not {"levering", *INSCHRIJVING} <= set(feit.columns):
        return []

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
    return sorted(overlaps, key=lambda x: x["key"])


def _canonicalisatie(star: dict[str, pl.DataFrame]) -> dict[str, Any]:
    meta = star.get(_META_CANONICALISATIE, pl.DataFrame())
    per_levering = meta.to_dicts() if not meta.is_empty() else []
    return {
        "regel": REGEL,
        "vervangen_inschrijvingen": sum(r["inschrijvingen"] for r in per_levering),
        "vervangen_isp_perioden": sum(r["isp_perioden"] for r in per_levering),
        "per_levering": per_levering,
    }


def _join_keuzes(star: dict[str, pl.DataFrame]) -> list[dict[str, Any]]:
    """Koppelingen met meer dan één kandidaat per sleutel (``meta_koppelkeuzes``)."""
    keuzes = star.get(_META_KOPPELKEUZES, pl.DataFrame())
    if keuzes.is_empty():
        return []
    return keuzes.filter(pl.col("meervoudige_sleutels") > 0).to_dicts()


def _leveringen_zonder_schooljaar(
    star: dict[str, pl.DataFrame],
) -> list[dict[str, Any]]:
    """Leveringen met inschrijvingen maar zonder rij in de schooljaar-fact.

    Zonder schooljaar-fact in de ster (niet gebouwd) valt er niets te melden.
    """
    inschrijvingen = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    jaren = star.get(SCHOOLJAAR_FEIT)
    if jaren is None or "levering" not in inschrijvingen.columns:
        return []
    per_levering = inschrijvingen.group_by("levering").agg(
        pl.len().alias("inschrijvingen")
    )
    if "levering" in jaren.columns:
        per_levering = per_levering.join(
            jaren.select("levering").unique(), on="levering", how="anti"
        )
    return per_levering.sort("levering").to_dicts()


@dataclass(frozen=True)
class _Doorvertaling:
    """Het feit waarin de records van een recordtype landen (#295)."""

    feit: str
    # Recordtype in de ``Bron``-kolom, als het feit meerdere bronnen combineert.
    bron: str | None = None
    # Een gat in de bekostiging is een error, anders een warning.
    bekostiging: bool = False
    # Recordtypes zonder eigen feit vullen kolommen van een ander feit (#326):
    # bereikt = rijen waarin minstens één van die kolommen gevuld is. De kolommen
    # komen uit het feit zelf (``kolomprefix``) of staan expliciet in ``kolommen``.
    kolomprefix: str | None = None
    kolommen: tuple[str, ...] = ()


_DOORVERTALING = {
    "ISP": _Doorvertaling(_CENTRAAL_FEIT, BRON_ISP),
    "BPV": _Doorvertaling("fact_bpv"),
    "KZD": _Doorvertaling("fact_kzd"),
    "AMO": _Doorvertaling("fact_amo"),
    "GEO": _Doorvertaling("fact_geo"),
    "BII": _Doorvertaling("fact_bekostiging", BRON_BII, bekostiging=True),
    "Teldatum": _Doorvertaling("fact_bekostiging", BRON_TBGI, bekostiging=True),
    "BID": _Doorvertaling("fact_bekostiging_diploma", BRON_BID, bekostiging=True),
    "Diploma": _Doorvertaling("fact_bekostiging_diploma", BRON_TBGI, bekostiging=True),
    "DIP": _Doorvertaling(_CENTRAAL_FEIT, kolomprefix="DIP_"),
    "ISE": _Doorvertaling(_CENTRAAL_FEIT, kolomprefix="ISE_"),
    "ISG": _Doorvertaling(_CENTRAAL_FEIT, kolommen=("DatumInschrijving",)),
}
# Recordtypes zonder eigen feit, bewust: hun rijtelling zegt niets over dekking.
_NIET_DOORVERTAALD = {
    "VLP": "leveringsmetadata in meta_leveringen",
    "SLR": "controletotalen in meta_leveringen en slr_details",
    "PER": "persoonskenmerken in dim_deelnemer",
    "Inschrijving": (
        "context van Teldatum en Diploma; eigen rij in fact_inschrijving alleen "
        "zonder ISP-periode (#196)"
    ),
    "Signaal": "alleen in de brondata (02-prepared)",
    "BekostigingsrelevanteBPV": "alleen in de brondata (02-prepared)",
}


def _per_levering(df: pl.DataFrame | None) -> dict[str, int]:
    if df is None or df.is_empty() or "levering" not in df.columns:
        return {}
    return dict(df.group_by("levering").len().iter_rows())


def _bereikt_per_levering(
    doel: _Doorvertaling, star: dict[str, pl.DataFrame]
) -> dict[str, int]:
    """Rijen per levering in het feit van ``doel`` (bij kolomdekking: gevulde rijen)."""
    feit = star.get(doel.feit, pl.DataFrame())
    if doel.bron is not None and BRON in feit.columns:
        feit = feit.filter(pl.col(BRON) == doel.bron)
    if doel.kolomprefix or doel.kolommen:
        kolommen = [
            c
            for c in feit.columns
            if c in doel.kolommen
            or (doel.kolomprefix and c.startswith(doel.kolomprefix))
        ]
        if not kolommen:
            return {}
        feit = feit.filter(pl.any_horizontal(pl.col(kolommen).is_not_null()))
    return _per_levering(feit)


def controleer_dekking(
    invoer: dict[str, pl.DataFrame], star: dict[str, pl.DataFrame]
) -> list[dict[str, Any]]:
    """Per levering × recordtype: ingelezen records en rijen in het analysemodel.

    Alleen een volledig gat krijgt een ernst: de aantallen hoeven niet gelijk te
    zijn (canonicalisatie, koppelingen), maar nul rijen uit een gevulde levering
    betekent dat het recordtype niet wordt doorvertaald (#258, #295). Een levering
    die helemaal vervangen is door een recentere, is verklaard (#174). Recordtypes
    die kolommen van een ander feit vullen (DIP, ISE, ISG) tellen de rijen waarin
    die kolommen gevuld zijn (#326).

    Args:
        invoer: Gestapelde prepared-tabellen (:func:`~.stack.stack_prepared`).
        star:   Tabellen van :func:`~mbo_bekostiging_bestanden.star.build_star`.
    """
    canonicalisatie = star.get(_META_CANONICALISATIE, pl.DataFrame())
    vervangen_door = (
        dict(canonicalisatie.select("levering", "vervangen_door").iter_rows())
        if not canonicalisatie.is_empty()
        else {}
    )
    in_model = set(_per_levering(star.get(_CENTRAAL_FEIT)))

    rijen = []
    for recordtype, records in sorted(invoer.items()):
        doel = _DOORVERTALING.get(recordtype)
        bereikt = _bereikt_per_levering(doel, star) if doel is not None else {}
        for levering, ingelezen in sorted(_per_levering(records).items()):
            rij = {
                "levering": levering,
                "recordtype": recordtype,
                "feit": doel.feit if doel else None,
                "ingelezen": ingelezen,
                "bereikt": bereikt.get(levering, 0) if doel else None,
                "ernst": None,
                "verklaring": _NIET_DOORVERTAALD.get(recordtype),
            }
            if doel is None and rij["verklaring"] is None:
                rij["ernst"] = ERNST_WARNING
                rij["verklaring"] = "geen doorvertaling naar het analysemodel bekend"
            elif doel is not None and rij["bereikt"] == 0:
                if levering in vervangen_door and levering not in in_model:
                    rij["verklaring"] = (
                        f"levering vervangen door {vervangen_door[levering]}"
                    )
                else:
                    rij["ernst"] = ERNST_ERROR if doel.bekostiging else ERNST_WARNING
            rijen.append(rij)
    return rijen


def _periode_koppelstatus(star: dict[str, pl.DataFrame]) -> dict[str, Any]:
    """Per detail-feit het aantal rijen per koppelstatus (#121)."""
    return {
        naam: dict(sorted(feit.group_by(KOPPELSTATUS).len().iter_rows()))
        for naam, feit in sorted(star.items())
        if KOPPELSTATUS in feit.columns
    }


def _dr_scope(star: dict[str, pl.DataFrame]) -> dict[str, Any]:
    """Instellingen waarbinnen DR- en Entree-uitstroom bepaald zijn (#118).

    Uitstroom zoekt de persoon in ``t+1`` bij alle instellingen in de dataset;
    een overstap naar een instelling daarbuiten telt als uitstroom. De dataset
    bevat alleen eigen leveringen, dus nooit de hele mbo-populatie.
    """
    jaren = star.get(SCHOOLJAAR_FEIT, pl.DataFrame())
    brins = (
        sorted(jaren["BRIN"].drop_nulls().unique().to_list())
        if "BRIN" in jaren.columns
        else []
    )
    return {"brins": brins, "mbo_breed": False}


def _referentiedata(star: dict[str, pl.DataFrame]) -> dict[str, Any]:
    """Herkomst van de referenties, en of de data voorbij hun dekking loopt (#132).

    Een opleidingscode die geen referentie kent, in een inschrijving die begint
    na de dekking van de opleidingsreferenties, wijst op een verouderde
    referentie. Binnen de dekking is de code zelf onbekend (``niveau_issues``).
    """
    meta = star.get(_META_REFERENTIEDATA, pl.DataFrame())
    if meta.is_empty():
        return {"bestanden": [], "onbekende_codes_na_dekking": None}
    dekking_tot = (
        meta.filter(pl.col("bestand").is_in(OPLEIDINGSREFERENTIES))
        .select(pl.col("dekking_tot").max())
        .item()
    )
    na_dekking = None
    inschrijvingen = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    if dekking_tot is not None and {"Opleidingcode", "DatumBegin"} <= set(
        inschrijvingen.columns
    ):
        codes = (
            inschrijvingen.filter(pl.col("DatumBegin") > dekking_tot)["Opleidingcode"]
            .drop_nulls()
            .unique()
        )
        onbekend = sorted(set(codes) - bekende_opleidingscodes())
        na_dekking = {"dekking_tot": dekking_tot.isoformat(), "codes": onbekend}
    return {
        "bestanden": meta.with_columns(
            pl.col("opgenomen", "dekking_tot").dt.to_string()
        ).to_dicts(),
        "onbekende_codes_na_dekking": na_dekking,
    }


def _verouderde_kolommen(star: dict[str, pl.DataFrame]) -> dict[str, list[str]]:
    """Legacy jaarkolommen die de ster nog heeft; ze verdwijnen in v4.0.0 (#201)."""
    inschrijvingen = star.get(_CENTRAAL_FEIT, pl.DataFrame())
    aanwezig = [k for k in VEROUDERDE_KOLOMMEN if k in inschrijvingen.columns]
    return {_CENTRAAL_FEIT: aanwezig} if aanwezig else {}


def _ster(ernst_: str, tekst: str) -> Melding:
    return Melding(ernst_, _BRON_STER, tekst)


def _meldingen_wees_feiten(wees_per_feit: dict[str, Any]) -> Iterator[Melding]:
    """Onverklaarde wees-rijen zijn een error, verklaarde (#196) info."""
    for naam, wees in wees_per_feit.items():
        onverklaard = wees["orphaned_rows"] - wees["explained_rows"]
        if onverklaard > 0:
            yield _ster(
                ERNST_ERROR,
                f"{naam}: {onverklaard} van {wees['total_rows']} rijen zonder "
                f"inschrijving in {_CENTRAAL_FEIT}",
            )
        if wees["explained_rows"]:
            yield _ster(
                ERNST_INFO,
                f"{naam}: {wees['explained_rows']} rijen zonder inschrijving, "
                f"verklaard: {wees['explanation']}",
            )


def _meldingen_sleuteldubbelingen(per_contract: dict[str, Any]) -> Iterator[Melding]:
    for naam, dubbel in per_contract.items():
        if dubbel.get("duplicate_keys", 0) > 0:
            yield _ster(
                ERNST_ERROR,
                f"{naam}: {dubbel['duplicate_keys']} dubbele sleutels "
                f"({', '.join(dubbel.get('sleutel', []))})",
            )


def _meldingen_niveau(niveau_issues: dict[str, int]) -> Iterator[Melding]:
    if niveau_issues.get("total", 0) > 0:
        yield _ster(
            ERNST_WARNING,
            f"{niveau_issues['total']} inschrijvingen zonder bekend niveau",
        )


def _meldingen_overlap(overlap: list[dict[str, Any]]) -> Iterator[Melding]:
    """Overlap die na canonicalisatie (#174) blijft, telt dubbel: error."""
    if overlap:
        yield _ster(
            ERNST_ERROR,
            f"{len(overlap)} overlappende leveringen na canonicalisatie",
        )


def _meldingen_canonicalisatie(canonicalisatie: dict[str, Any]) -> Iterator[Melding]:
    vervangen = canonicalisatie.get("vervangen_inschrijvingen", 0)
    if vervangen:
        yield _ster(
            ERNST_INFO,
            f"{vervangen} inschrijvingen vervangen door een recentere levering",
        )


def _meldingen_join_keuzes(keuzes: list[dict[str, Any]]) -> Iterator[Melding]:
    """Meervoudige matches (#209): een error bij regel ``uniek``, want het PvE
    staat daar één kandidaat toe; anders een warning (#239). Rapporten van vóór
    #239 hebben geen regel en blijven een warning."""
    meervoudig = [k for k in keuzes if k["meervoudige_sleutels"]]
    for ernst_, groep in (
        (ERNST_ERROR, [k for k in meervoudig if k.get("regel") == UNIEK]),
        (ERNST_WARNING, [k for k in meervoudig if k.get("regel") != UNIEK]),
    ):
        if groep:
            yield _ster(
                ernst_,
                "meervoudige matches bij koppelen: "
                + ", ".join(
                    f"{k['koppeling']} ({k['meervoudige_sleutels']}, regel "
                    f"{k.get('regel', 'onbekend')})"
                    for k in groep
                ),
            )


def _meldingen_zonder_schooljaar(leveringen: list[dict[str, Any]]) -> Iterator[Melding]:
    if leveringen:
        yield _ster(
            ERNST_WARNING,
            "leveringen zonder waarneembare peildatum: "
            + ", ".join(r["levering"] for r in leveringen),
        )


def _meldingen_verouderd(per_tabel: dict[str, list[str]]) -> Iterator[Melding]:
    for tabel, kolommen in per_tabel.items():
        yield _ster(
            ERNST_INFO,
            f"{tabel}: {len(kolommen)} verouderde jaargebonden kolommen verdwijnen "
            f"in {VEROUDERD_TOT}; gebruik {SCHOOLJAAR_FEIT} (#201)",
        )


def _meldingen_dr_scope(scope: dict[str, Any]) -> Iterator[Melding]:
    brins = scope.get("brins", [])
    if brins:
        yield _ster(
            ERNST_INFO,
            f"DR- en Entree-uitstroom bepaald binnen {len(brins)} "
            f"{'instelling' if len(brins) == 1 else 'instellingen'} "
            f"({', '.join(brins)}); een overstap naar een instelling buiten de "
            "dataset telt als uitstroom (#118)",
        )


def _meldingen_koppelstatus(per_feit: dict[str, dict[str, int]]) -> Iterator[Melding]:
    """Detailrijen die op de eerste periode terugvielen (#121): info."""
    for naam, per_status in per_feit.items():
        terugval = {
            status: n
            for status, n in per_status.items()
            if status not in (KOPPELSTATUS_BINNEN, KOPPELSTATUS_GEEN_INSCHRIJVING)
        }
        if terugval:
            details = ", ".join(f"{s}: {n}" for s, n in terugval.items())
            yield _ster(
                ERNST_INFO,
                f"{naam}: {sum(terugval.values())} rijen aan de eerste periode van "
                f"hun inschrijving gehangen ({details}); filter op {KOPPELSTATUS} "
                "(#121)",
            )


def _meldingen_referentiedata(referentie: dict[str, Any]) -> Iterator[Melding]:
    """Afwijking van het manifest of data voorbij de dekking (#132): warning."""
    afwijkend = [
        r["bestand"] for r in referentie.get("bestanden", []) if r["afwijkend"]
    ]
    if afwijkend:
        yield _ster(
            ERNST_WARNING,
            "referentiebestanden wijken af van metadata/referentiedata.json: "
            + ", ".join(afwijkend),
        )
    na_dekking = referentie.get("onbekende_codes_na_dekking") or {}
    if na_dekking.get("codes"):
        yield _ster(
            ERNST_WARNING,
            f"opleidingscodes {', '.join(na_dekking['codes'])} onbekend in de "
            f"referentie, in inschrijvingen na haar dekking "
            f"({na_dekking['dekking_tot']}): werk de referentie bij (#132)",
        )


def _meldingen_dekking(rijen: list[dict[str, Any]]) -> Iterator[Melding]:
    """De dekkingstabel (#295) draagt zijn ernst al; bron is de levering."""
    for rij in rijen:
        if rij["ernst"]:
            doel = f"0 in {rij['feit']}" if rij["feit"] else rij["verklaring"]
            yield Melding(
                rij["ernst"],
                rij["levering"],
                f"{rij['recordtype']}: {rij['ingelezen']} records ingelezen, {doel}",
            )


def _grondslag_studiejaren(star: dict[str, pl.DataFrame]) -> dict[str, list[int]]:
    """Per BRIN de studiejaren van de GRONDSLAG-leveringen in de ster (#128).

    Alleen het GRONDSLAG-voorlooprecord heeft een ``Studiejaar``.
    """
    meta = star.get("meta_leveringen", pl.DataFrame())
    if not {"BRIN", "Studiejaar"} <= set(meta.columns):
        return {}
    per_brin = (
        meta.drop_nulls(["BRIN", "Studiejaar"])
        .group_by("BRIN")
        .agg(pl.col("Studiejaar").unique().sort())
        .sort("BRIN")
    )
    return dict(per_brin.iter_rows())


def _meldingen_pgn(studiejaren: dict[str, list[int]]) -> Iterator[Melding]:
    """Info zodra de ster op een onbevestigde PGN-stabiliteit leunt (#128)."""
    meerdere = {brin: jaren for brin, jaren in studiejaren.items() if len(jaren) > 1}
    if meerdere:
        details = ", ".join(
            f"{brin}: {', '.join(map(str, jaren))}" for brin, jaren in meerdere.items()
        )
        yield _ster(
            ERNST_INFO,
            f"GRONDSLAG-leveringen uit meerdere studiejaren ({details}): personen "
            "koppelen op het omgenummerde PGN, waarvan de stabiliteit over "
            f"studiejaren {PGN_STABILITEIT} is (#128)",
        )


@dataclass(frozen=True)
class _SterCheck:
    """Eén star-check: waarde onder ``sleutel`` in ``quality.json`` → ``star``.

    ``bereken`` krijgt de ster en de gestapelde invoer; ``meldingen`` krijgt de
    (uit JSON teruggelezen) waarde, zodat het dashboard een geschreven rapport
    kan tonen zonder de ster opnieuw te bouwen.
    """

    sleutel: str
    bereken: Callable[[dict[str, pl.DataFrame], dict[str, pl.DataFrame]], Any]
    meldingen: Callable[[Any], Iterable[Melding]]


def _alleen_ster(
    functie: Callable[[dict[str, pl.DataFrame]], Any],
) -> Callable[[dict[str, pl.DataFrame], dict[str, pl.DataFrame]], Any]:
    return lambda star, _invoer: functie(star)


# Register van alle star-checks (#329), in de sleutelvolgorde van quality.json.
# Een check toevoegen = een reken- en een meldingenfunctie plus één regel hier,
# en de sleutel in docs/quality.schema.json (tests/test_checkregister.py).
_STER_CHECKS: tuple[_SterCheck, ...] = (
    _SterCheck("orphaned_facts", _alleen_ster(_wees_feiten), _meldingen_wees_feiten),
    _SterCheck(
        "key_duplicates",
        _alleen_ster(_sleuteldubbelingen),
        _meldingen_sleuteldubbelingen,
    ),
    _SterCheck("niveau_issues", _alleen_ster(_niveau_issues), _meldingen_niveau),
    _SterCheck(
        "overlapping_deliveries",
        _alleen_ster(_overlappende_leveringen),
        _meldingen_overlap,
    ),
    _SterCheck(
        "canonicalisatie",
        _alleen_ster(_canonicalisatie),
        _meldingen_canonicalisatie,
    ),
    _SterCheck("join_keuzes", _alleen_ster(_join_keuzes), _meldingen_join_keuzes),
    _SterCheck(
        "leveringen_zonder_schooljaar",
        _alleen_ster(_leveringen_zonder_schooljaar),
        _meldingen_zonder_schooljaar,
    ),
    _SterCheck(
        "verouderde_kolommen",
        _alleen_ster(_verouderde_kolommen),
        _meldingen_verouderd,
    ),
    _SterCheck("dr_scope", _alleen_ster(_dr_scope), _meldingen_dr_scope),
    _SterCheck(
        "periode_koppelstatus",
        _alleen_ster(_periode_koppelstatus),
        _meldingen_koppelstatus,
    ),
    _SterCheck(
        "referentiedata",
        _alleen_ster(_referentiedata),
        _meldingen_referentiedata,
    ),
    _SterCheck(
        "grondslag_studiejaren",
        _alleen_ster(_grondslag_studiejaren),
        _meldingen_pgn,
    ),
    _SterCheck(
        "dekking",
        lambda star, invoer: controleer_dekking(invoer, star),
        _meldingen_dekking,
    ),
)
