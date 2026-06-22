"""Inlezen van ruwe bekostigingsbestanden."""

import xml.etree.ElementTree as ET
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.metadata import load_schema

_XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"


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


def read_tbgi(path: str | Path) -> dict[str, pl.DataFrame]:
    """Lees een TBGI XML-bestand in en plat het naar vier DataFrames.

    De geneste XML-structuur wordt omgezet naar vier tabellen:

    - ``Inschrijving`` — één rij per inschrijving.
    - ``Teldatum`` — één rij per (inschrijving × teldatum), met
      BekostigingsrelevanteBPV-velden geprefixed als ``BPV_``.
    - ``Diploma`` — één rij per diploma.
    - ``Signaal`` — één rij per signaal (van Teldatum of Diploma);
      kolom ``Bron`` geeft de herkomst aan.

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

    schema = load_schema("tbgi")
    root = ET.parse(path).getroot()

    inschrijving_rows: list[dict] = []
    teldatum_rows: list[dict] = []
    diploma_rows: list[dict] = []
    signaal_rows: list[dict] = []

    for isg in root.findall("Inschrijving"):
        brin = _elem_text(isg, "BRIN")
        invnr = _elem_text(isg, "Inschrijvingvolgnummer")

        inschrijving_rows.append(
            {
                "BRIN": brin,
                "Burgerservicenummer": _elem_text(isg, "Burgerservicenummer"),
                "Onderwijsnummer": _elem_text(isg, "Onderwijsnummer"),
                "Inschrijvingvolgnummer": invnr,
                "DatumInschrijving": _elem_text(isg, "DatumInschrijving"),
                "DatumUitschrijvingGepland": _elem_text(
                    isg, "DatumUitschrijvingGepland"
                ),
                "DatumUitschrijvingWerkelijk": (
                    _elem_text(isg, "DatumUitschrijvingWerkelijk")
                ),
                "NiveauHoogstBekostigdeDiploma": (
                    _elem_text(isg, "NiveauHoogstBekostigdeDiploma")
                ),
            }
        )

        for td in isg.findall("Teldatum"):
            bpv = td.find("BekostigingsrelevanteBPV")
            teldatum_rows.append(
                {
                    "BRIN": brin,
                    "Inschrijvingvolgnummer": invnr,
                    "Teldatum": _elem_text(td, "Teldatum"),
                    "DatumTijdBepalingBekostigingsgrondslagen": _elem_text(
                        td, "DatumTijdBepalingBekostigingsgrondslagen"
                    ),
                    "StatusBepalingBekostigingsstatus": _elem_text(
                        td, "StatusBepalingBekostigingsstatus"
                    ),
                    "LeeftijdOpEenAugustusStudiejaar": _elem_text(
                        td, "LeeftijdOpEenAugustusStudiejaar"
                    ),
                    "Opleidingcode": _elem_text(td, "Opleidingcode"),
                    "Niveau": _elem_text(td, "Niveau"),
                    "Leertraject": _elem_text(td, "Leertraject"),
                    "Leerroutefase": _elem_text(td, "Leerroutefase"),
                    "IndicatieBekostigbaar": _elem_text(td, "IndicatieBekostigbaar"),
                    "Bekostigingsstatus": _elem_text(td, "Bekostigingsstatus"),
                    "InschrijvingVoorCorrectiefactor": _elem_text(
                        td, "InschrijvingVoorCorrectiefactor"
                    ),
                    "BBLBOLFactor": _elem_text(td, "BBLBOLFactor"),
                    "PrijsfactorMBO": _elem_text(td, "PrijsfactorMBO"),
                    "AantalBekostigdeVerblijfsjarenMBO": _elem_text(
                        td, "AantalBekostigdeVerblijfsjarenMBO"
                    ),
                    "Verblijfsjaarfactor": _elem_text(td, "Verblijfsjaarfactor"),
                    "BijdrageInschrijvingAanDeelnemerswaarde": _elem_text(
                        td, "BijdrageInschrijvingAanDeelnemerswaarde"
                    ),
                    "BPV_Inschrijvingvolgnummer": _elem_text(
                        bpv, "Inschrijvingvolgnummer"
                    ),
                    "BPV_Volgnummer": _elem_text(bpv, "Volgnummer"),
                    "BPV_Afsluitdatum": _elem_text(bpv, "Afsluitdatum"),
                    "BPV_DatumBegin": _elem_text(bpv, "DatumBegin"),
                    "BPV_DatumEindGepland": _elem_text(bpv, "DatumEindGepland"),
                    "BPV_DatumEindWerkelijk": _elem_text(bpv, "DatumEindWerkelijk"),
                    "BPV_Opleidingcode": _elem_text(bpv, "Opleidingcode"),
                }
            )

            for sig in td.findall("Signaal"):
                param = sig.find("Parameter")
                signaal_rows.append(
                    {
                        "Bron": "Inschrijving",
                        "BRIN": brin,
                        "Inschrijvingvolgnummer": invnr,
                        "Teldatum": _elem_text(td, "Teldatum"),
                        "Resultaatvolgnummer": None,
                        "Signaalvolgnummer": _elem_text(sig, "Signaalvolgnummer"),
                        "Signaalcode": _elem_text(sig, "Signaalcode"),
                        "Signaalomschrijving": _elem_text(sig, "Signaalomschrijving"),
                        "Parametervolgnummer": _elem_text(param, "Parametervolgnummer"),
                        "Parameternaam": _elem_text(param, "Parameternaam"),
                        "Parameterwaarde": _elem_text(param, "Parameterwaarde"),
                    }
                )

    for dip in root.findall("Diploma"):
        brin = _elem_text(dip, "BRIN")
        resvnr = _elem_text(dip, "Resultaatvolgnummer")

        diploma_rows.append(
            {
                "BRIN": brin,
                "Burgerservicenummer": _elem_text(dip, "Burgerservicenummer"),
                "Onderwijsnummer": _elem_text(dip, "Onderwijsnummer"),
                "Resultaatvolgnummer": resvnr,
                "Opleidingcode": _elem_text(dip, "Opleidingcode"),
                "Inschrijvingvolgnummer": _elem_text(dip, "Inschrijvingvolgnummer"),
                "DatumBehaald": _elem_text(dip, "DatumBehaald"),
                "Niveau": _elem_text(dip, "Niveau"),
                "IndicatieSpecialistendiploma": (
                    _elem_text(dip, "IndicatieSpecialistendiploma")
                ),
                "NiveauHoogstBekostigdeDiploma": (
                    _elem_text(dip, "NiveauHoogstBekostigdeDiploma")
                ),
                "IndicatieHoogstBekostigdeDiplomaIsSpecialist": _elem_text(
                    dip, "IndicatieHoogstBekostigdeDiplomaIsSpecialist"
                ),
                "DatumTijdBepalingBekostigingsgrondslagen": _elem_text(
                    dip, "DatumTijdBepalingBekostigingsgrondslagen"
                ),
                "StatusBepalingBekostigingsstatus": _elem_text(
                    dip, "StatusBepalingBekostigingsstatus"
                ),
                "Bekostigingsstatus": _elem_text(dip, "Bekostigingsstatus"),
                "BijdrageDiplomawaarde": _elem_text(dip, "BijdrageDiplomawaarde"),
            }
        )

        for sig in dip.findall("Signaal"):
            param = sig.find("Parameter")
            signaal_rows.append(
                {
                    "Bron": "Diploma",
                    "BRIN": brin,
                    "Inschrijvingvolgnummer": None,
                    "Teldatum": None,
                    "Resultaatvolgnummer": resvnr,
                    "Signaalvolgnummer": _elem_text(sig, "Signaalvolgnummer"),
                    "Signaalcode": _elem_text(sig, "Signaalcode"),
                    "Signaalomschrijving": _elem_text(sig, "Signaalomschrijving"),
                    "Parametervolgnummer": _elem_text(param, "Parametervolgnummer"),
                    "Parameternaam": _elem_text(param, "Parameternaam"),
                    "Parameterwaarde": _elem_text(param, "Parameterwaarde"),
                }
            )

    result: dict[str, pl.DataFrame] = {}
    tables = {
        "Inschrijving": inschrijving_rows,
        "Teldatum": teldatum_rows,
        "Diploma": diploma_rows,
        "Signaal": signaal_rows,
    }
    for tabel, rows in tables.items():
        fields = schema[tabel]["fields"]
        if rows:
            df = pl.DataFrame(rows).select(fields)
        else:
            df = pl.DataFrame({f: pl.Series([], dtype=pl.Utf8) for f in fields})
        # xsi:nil-elementen leveren pl.Null-kolommen op; cast naar Utf8 zodat
        # decode_frames ze uniform als string kan verwerken.
        null_cols = [c for c in df.columns if df[c].dtype == pl.Null]
        if null_cols:
            df = df.with_columns(pl.col(c).cast(pl.Utf8) for c in null_cols)
        result[tabel] = df

    return result
