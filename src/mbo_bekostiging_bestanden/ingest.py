"""Inlezen van ruwe bekostigingsbestanden."""

import xml.etree.ElementTree as ET
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.metadata import extra_kolommen, load_schema

_XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"

# TBGI: velden die een kind-rij (Teldatum, BPV, Signaal) van zijn ouder erft.
_TBGI_PERSOON = ("BRIN", "Burgerservicenummer", "Onderwijsnummer")
_TBGI_INSCHRIJVING_CONTEXT = (*_TBGI_PERSOON, "Inschrijvingvolgnummer")
_TBGI_DIPLOMA_CONTEXT = (*_TBGI_PERSOON, "Resultaatvolgnummer")
_TBGI_BPV = "BekostigingsrelevanteBPV"
# Kolommen waarvan de XML-tag afwijkt: de BPV noemt zijn eigen inschrijving,
# die naast die van de ouder-inschrijving staat.
_TBGI_TAG = {"InschrijvingvolgnummerBPV": "Inschrijvingvolgnummer"}


def _elem_text(parent: ET.Element | None, tag: str) -> str | None:
    """Haal tekst op uit een child-element; None bij ontbrekend of xsi:nil."""
    if parent is None:
        return None
    child = parent.find(tag)
    if child is None or child.get(_XSI_NIL) == "true":
        return None
    return child.text or None


def _detect_separator(line: str) -> str:
    return "|" if line.count("|") >= line.count(";") else ";"


def _normalize_row(row: list[str], n: int) -> list[str]:
    """Clip of pad een rij tot exact n velden."""
    if len(row) >= n:
        return row[:n]
    return row + [""] * (n - len(row))


def _velden_voorbij_schema(
    fields: list[str], kolommen: list[str], spiegelvelden: list[str]
) -> list[str]:
    """Gevulde velden voorbij schema + gedeclareerde spiegelvelden (#257).

    Spiegelvelden (posities buiten het PvE, zie schema-TOML) tellen niet mee:
    ze worden als eigen kolom ingelezen (#260).
    """
    return fields[len(kolommen) + len(spiegelvelden) :]


def _lees_regels(path: Path) -> list[list[str]]:
    """Niet-lege regels van een multi-record CSV, gesplitst op het scheidingsteken.

    Lege velden aan het eind van een regel vallen weg (``rstrip`` van het
    scheidingsteken); het schema vult ze bij het inlezen weer aan.

    Raises:
        FileNotFoundError: Als het bronbestand niet bestaat.
        ValueError:        Als het bestand leeg is.
    """
    if not path.exists():
        raise FileNotFoundError(f"Bronbestand niet gevonden: {path}")
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        content = path.read_text(encoding="latin-1")

    lines = [line.rstrip("\r") for line in content.splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"Leeg bestand: {path}")
    sep = _detect_separator(lines[0])
    return [line.rstrip(sep).split(sep) for line in lines]


def read_multi_record_csv(
    path: str | Path,
    schema_name: str,
) -> dict[str, pl.DataFrame]:
    """Lees een multi-record CSV-bestand in en splits per recordtype.

    Geschikt voor elk DUO-bestandstype dat de multi-record CSV-structuur
    gebruikt (RO, GRONDSLAG IP MBO, …). Kolomnamen komen uit het opgegeven
    schema-TOML. Fail-closed (#257): een onbekend recordtype of een gevuld
    veld voorbij de schemabreedte (incl. gedeclareerde spiegelvelden) is een
    teken dat het bestand niet is wat het zegt te zijn, en breekt de ingest
    in plaats van stil te worden genegeerd/afgeknipt. Een regel die *korter*
    is dan het schema wordt (nog) gepad: optionele achtervelden zijn niet
    per-recordtype gemarkeerd in het schema, dus dat is vooralsnog niet te
    onderscheiden van een echte fout.

    Args:
        path:        Pad naar het bronbestand.
        schema_name: Naam van het schema (bijv. ``"ro"`` of ``"grondslag"``).

    Returns:
        Dict met recordtype-code als sleutel en een DataFrame als waarde.

    Raises:
        FileNotFoundError: Als het bronbestand of schema niet bestaat.
        ValueError: Als het bestand leeg is, een regel een onbekend
            recordtype heeft, of een regel een gevuld veld heeft voorbij de
            schemabreedte.
    """
    schema = load_schema(schema_name)

    rows_by_type: dict[str, list[list[str]]] = {rt: [] for rt in schema}
    for regelnr, fields in enumerate(_lees_regels(Path(path)), start=1):
        rt = fields[0]
        if rt not in rows_by_type:
            raise ValueError(
                f"{path}: regel {regelnr} heeft een onbekend recordtype {rt!r}"
            )
        kolommen = schema[rt]["fields"]
        spiegelvelden = schema[rt].get("spiegelvelden", [])
        extra = _velden_voorbij_schema(fields, kolommen, spiegelvelden)
        if any(extra):
            raise ValueError(
                f"{path}: regel {regelnr} ({rt}) heeft gevulde velden voorbij "
                f"de schemabreedte: {extra}"
            )
        rows_by_type[rt].append(fields)

    result: dict[str, pl.DataFrame] = {}
    for rt, rows in rows_by_type.items():
        if not rows:
            continue
        cols = [*schema[rt]["fields"], *extra_kolommen(schema[rt])]
        n = len(cols)
        normalized = [_normalize_row(row, n) for row in rows]
        result[rt] = pl.DataFrame(
            {col: [r[i] for r in normalized] for i, col in enumerate(cols)}
        )

    return result


def inventariseer_regels(path: str | Path, schema_name: str) -> dict:
    """Tel afwijkende regels in een bronbestand, los van :func:`read_multi_record_csv`.

    Onbekend recordtype en velden voorbij de schemabreedte laten
    :func:`read_multi_record_csv` sinds #257 fail-closed falen — voor een
    bestand dat de pipeline doorloopt zijn die twee categorieën dus altijd
    leeg. Deze functie leest het bestand onafhankelijk opnieuw en blijft
    nuttig als losstaand diagnosemiddel (bijv. om te controleren wát er zou
    zijn misgegaan) en voor ``spiegel_afwijkingen``, dat wél door de
    pipeline heen komt (#120): een waardeverschil op een spiegelpositie is
    geen schemaoverschrijding.

    Returns:
        ``onbekende_recordtypes``: recordtype → aantal regels buiten het schema.
        ``velden_voorbij_schema``: recordtype → aantal regels met een gevuld
        veld voorbij de schemabreedte (na eventuele spiegelvelden).
        ``spiegel_afwijkingen``: recordtype → kolom (:func:`extra_kolommen`)
        → aantal regels waarin die positie níet gelijk is aan het veld dat ze
        lijkt te herhalen.
    """
    schema = load_schema(schema_name)
    onbekend: dict[str, int] = {}
    voorbij: dict[str, int] = {}
    spiegel: dict[str, dict[str, int]] = {}
    for fields in _lees_regels(Path(path)):
        rt = fields[0]
        if rt not in schema:
            onbekend[rt] = onbekend.get(rt, 0) + 1
            continue
        kolommen = schema[rt]["fields"]
        spiegelkolommen = extra_kolommen(schema[rt])
        rij = dict(zip(kolommen, _normalize_row(fields, len(kolommen)), strict=True))
        extra = fields[len(kolommen) :]
        for (kolom, veld), waarde in zip(spiegelkolommen.items(), extra, strict=False):
            if waarde != rij[veld]:
                per_kolom = spiegel.setdefault(rt, {})
                per_kolom[kolom] = per_kolom.get(kolom, 0) + 1
        if any(extra[len(spiegelkolommen) :]):
            voorbij[rt] = voorbij.get(rt, 0) + 1
    return {
        "onbekende_recordtypes": dict(sorted(onbekend.items())),
        "velden_voorbij_schema": dict(sorted(voorbij.items())),
        "spiegel_afwijkingen": dict(sorted(spiegel.items())),
    }


def read_ro(path: str | Path) -> dict[str, pl.DataFrame]:
    """Lees een RO-bestand in en splits per recordtype.

    Dunne wrapper om :func:`read_multi_record_csv` met schema ``"ro"``.
    """
    return read_multi_record_csv(path, "ro")


def read_grondslag(path: str | Path) -> dict[str, pl.DataFrame]:
    """Lees een GRONDSLAG IP MBO-bestand in en splits per recordtype.

    Dunne wrapper om :func:`read_multi_record_csv` met schema ``"grondslag"``.
    """
    return read_multi_record_csv(path, "grondslag")


def _lees_velden(elem: ET.Element | None, velden: list[str]) -> dict[str, str | None]:
    """Lees ``velden`` als child-elementen van ``elem`` (tag volgens ``_TBGI_TAG``)."""
    return {veld: _elem_text(elem, _TBGI_TAG.get(veld, veld)) for veld in velden}


def _heeft_waarde(rij: dict[str, str | None]) -> bool:
    """Een element met alleen xsi:nil-velden is een lege placeholder, geen record."""
    return any(waarde is not None for waarde in rij.values())


def _bpv_rijen(
    teldatum: ET.Element, context: dict[str, str | None], velden: list[str]
) -> list[dict[str, str | None]]:
    """Eén rij per niet-lege ``<BekostigingsrelevanteBPV>`` onder een teldatum."""
    eigen = [v for v in velden if v not in context]
    rijen = [_lees_velden(bpv, eigen) for bpv in teldatum.findall(_TBGI_BPV)]
    return [context | rij for rij in rijen if _heeft_waarde(rij)]


def _signaal_rijen(
    ouder: ET.Element, context: dict[str, str | None], velden: list[str]
) -> list[dict[str, str | None]]:
    """Eén rij per ``<Parameter>`` van elk niet-leeg ``<Signaal>`` onder ``ouder``.

    Een signaal zonder parameters geeft één rij met lege parametervelden.
    """
    signaal_velden = [v for v in velden if v.startswith("Signaal")]
    parameter_velden = [v for v in velden if v.startswith("Parameter")]
    rijen: list[dict[str, str | None]] = []
    for sig in ouder.findall("Signaal"):
        signaal = _lees_velden(sig, signaal_velden)
        parameters = [
            _lees_velden(p, parameter_velden) for p in sig.findall("Parameter")
        ]
        parameters = [p for p in parameters if _heeft_waarde(p)]
        if not _heeft_waarde(signaal) and not parameters:
            continue
        basis = dict.fromkeys(velden) | context | signaal
        rijen += [basis | p for p in parameters] or [basis]
    return rijen


def read_tbgi(path: str | Path) -> dict[str, pl.DataFrame]:
    """Lees een TBGI XML-bestand in en plat het naar vijf DataFrames.

    De geneste XML-structuur wordt omgezet naar vijf tabellen:

    - ``Inschrijving`` — één rij per inschrijving.
    - ``Teldatum`` — één rij per (inschrijving × teldatum).
    - ``BekostigingsrelevanteBPV`` — één rij per BPV per teldatum (0..n).
    - ``Diploma`` — één rij per diploma.
    - ``Signaal`` — één rij per signaalparameter (van Teldatum of Diploma);
      kolom ``Bron`` geeft de herkomst aan.

    Elementen met alleen xsi:nil-velden (lege BPV-/Signaal-placeholders) geven
    geen rij.  Kind-rijen dragen de persoons-identifiers van hun
    ouder-element: ``Inschrijvingvolgnummer`` is alleen uniek per persoon
    (PvE §16.5.1), dus achteraf koppelen via het volgnummer is niet eenduidig.

    Args:
        path: Pad naar het TBGI XML-bestand.

    Returns:
        Dict van tabelnaam naar getypeerde DataFrame.

    Raises:
        FileNotFoundError: Als het bestand niet bestaat.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Bronbestand niet gevonden: {path}")

    velden = {tabel: spec["fields"] for tabel, spec in load_schema("tbgi").items()}
    root = ET.parse(path).getroot()

    teldatum_eigen = [
        v for v in velden["Teldatum"] if v not in _TBGI_INSCHRIJVING_CONTEXT
    ]

    inschrijving_rows: list[dict] = []
    teldatum_rows: list[dict] = []
    bpv_rows: list[dict] = []
    diploma_rows: list[dict] = []
    signaal_rows: list[dict] = []

    for isg in root.findall("Inschrijving"):
        inschrijving = _lees_velden(isg, velden["Inschrijving"])
        inschrijving_rows.append(inschrijving)
        context = {v: inschrijving[v] for v in _TBGI_INSCHRIJVING_CONTEXT}

        for td in isg.findall("Teldatum"):
            teldatum = context | _lees_velden(td, teldatum_eigen)
            teldatum_rows.append(teldatum)
            teldatum_context = context | {"Teldatum": teldatum["Teldatum"]}
            bpv_rows += _bpv_rijen(td, teldatum_context, velden[_TBGI_BPV])
            signaal_rows += _signaal_rijen(
                td, teldatum_context | {"Bron": "Inschrijving"}, velden["Signaal"]
            )

    for dip in root.findall("Diploma"):
        diploma = _lees_velden(dip, velden["Diploma"])
        diploma_rows.append(diploma)
        context = {v: diploma[v] for v in _TBGI_DIPLOMA_CONTEXT}
        signaal_rows += _signaal_rijen(
            dip, context | {"Bron": "Diploma"}, velden["Signaal"]
        )

    tables = {
        "Inschrijving": inschrijving_rows,
        "Teldatum": teldatum_rows,
        _TBGI_BPV: bpv_rows,
        "Diploma": diploma_rows,
        "Signaal": signaal_rows,
    }
    # Expliciet Utf8: typeherkenning op de eerste rijen faalt als een kolom daar
    # alleen xsi:nil bevat (bijv. Onderwijsnummer); decode_frames typeert daarna.
    result = {
        tabel: pl.DataFrame(rows, schema=dict.fromkeys(velden[tabel], pl.Utf8))
        for tabel, rows in tables.items()
    }
    return result
