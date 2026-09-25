"""Inlezen van ruwe bekostigingsbestanden."""

import xml.etree.ElementTree as ET
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.metadata import load_schema

_XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"

# TBGI: velden die een kind-rij (Teldatum, Signaal) van zijn ouder-element erft.
_TBGI_PERSOON = ("BRIN", "Burgerservicenummer", "Onderwijsnummer")
_TBGI_INSCHRIJVING_CONTEXT = (*_TBGI_PERSOON, "Inschrijvingvolgnummer")
_TBGI_DIPLOMA_CONTEXT = (*_TBGI_PERSOON, "Resultaatvolgnummer")
_TBGI_BPV_PREFIX = "BPV_"


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


def read_multi_record_csv(
    path: str | Path,
    schema_name: str,
) -> dict[str, pl.DataFrame]:
    """Lees een multi-record CSV-bestand in en splits per recordtype.

    Geschikt voor elk DUO-bestandstype dat de multi-record CSV-structuur
    gebruikt (RO, GRONDSLAG IP MBO, …). Kolomnamen komen uit het opgegeven
    schema-TOML.

    Args:
        path:        Pad naar het bronbestand.
        schema_name: Naam van het schema (bijv. ``"ro"`` of ``"grondslag"``).

    Returns:
        Dict met recordtype-code als sleutel en een DataFrame als waarde.

    Raises:
        FileNotFoundError: Als het bronbestand of schema niet bestaat.
        ValueError:        Als het bestand leeg is.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Bronbestand niet gevonden: {path}")

    raw_schema = load_schema(schema_name)
    schema = {rt: v["fields"] for rt, v in raw_schema.items()}

    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        content = path.read_text(encoding="latin-1")

    lines = [line.rstrip("\r") for line in content.splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"Leeg bestand: {path}")

    sep = _detect_separator(lines[0])

    rows_by_type: dict[str, list[list[str]]] = {rt: [] for rt in schema}
    for line in lines:
        fields = line.rstrip(sep).split(sep)
        rt = fields[0] if fields else ""
        if rt in rows_by_type:
            rows_by_type[rt].append(fields)

    result: dict[str, pl.DataFrame] = {}
    for rt, rows in rows_by_type.items():
        if not rows:
            continue
        cols = schema[rt]
        n = len(cols)
        normalized = [_normalize_row(row, n) for row in rows]
        result[rt] = pl.DataFrame(
            {col: [r[i] for r in normalized] for i, col in enumerate(cols)}
        )

    return result


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


def _lees_velden(
    elem: ET.Element | None, velden: list[str], prefix: str = ""
) -> dict[str, str | None]:
    """Lees ``velden`` als child-elementen van ``elem`` (tag zonder ``prefix``)."""
    return {veld: _elem_text(elem, veld.removeprefix(prefix)) for veld in velden}


def _signaal_rijen(
    ouder: ET.Element, context: dict[str, str | None], velden: list[str]
) -> list[dict[str, str | None]]:
    """Eén rij per ``<Signaal>`` onder ``ouder``, aangevuld met de ouder-``context``."""
    signaal_velden = [v for v in velden if v.startswith("Signaal")]
    parameter_velden = [v for v in velden if v.startswith("Parameter")]
    return [
        dict.fromkeys(velden)
        | context
        | _lees_velden(sig, signaal_velden)
        | _lees_velden(sig.find("Parameter"), parameter_velden)
        for sig in ouder.findall("Signaal")
    ]


def read_tbgi(path: str | Path) -> dict[str, pl.DataFrame]:
    """Lees een TBGI XML-bestand in en plat het naar vier DataFrames.

    De geneste XML-structuur wordt omgezet naar vier tabellen:

    - ``Inschrijving`` — één rij per inschrijving.
    - ``Teldatum`` — één rij per (inschrijving × teldatum), met
      BekostigingsrelevanteBPV-velden geprefixed als ``BPV_``.
    - ``Diploma`` — één rij per diploma.
    - ``Signaal`` — één rij per signaal (van Teldatum of Diploma);
      kolom ``Bron`` geeft de herkomst aan.

    Teldatum- en Signaal-rijen dragen de persoons-identifiers van hun
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
        v
        for v in velden["Teldatum"]
        if v not in _TBGI_INSCHRIJVING_CONTEXT and not v.startswith(_TBGI_BPV_PREFIX)
    ]
    teldatum_bpv = [v for v in velden["Teldatum"] if v.startswith(_TBGI_BPV_PREFIX)]

    inschrijving_rows: list[dict] = []
    teldatum_rows: list[dict] = []
    diploma_rows: list[dict] = []
    signaal_rows: list[dict] = []

    for isg in root.findall("Inschrijving"):
        inschrijving = _lees_velden(isg, velden["Inschrijving"])
        inschrijving_rows.append(inschrijving)
        context = {v: inschrijving[v] for v in _TBGI_INSCHRIJVING_CONTEXT}

        for td in isg.findall("Teldatum"):
            teldatum = (
                context
                | _lees_velden(td, teldatum_eigen)
                | _lees_velden(
                    td.find("BekostigingsrelevanteBPV"), teldatum_bpv, _TBGI_BPV_PREFIX
                )
            )
            teldatum_rows.append(teldatum)
            signaal_rows += _signaal_rijen(
                td,
                context | {"Bron": "Inschrijving", "Teldatum": teldatum["Teldatum"]},
                velden["Signaal"],
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
