"""Inlezen van ruwe bekostigingsbestanden."""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.metadata import (
    bestandsnaam_patroon,
    extra_kolommen,
    load_schema,
)
from mbo_bekostiging_bestanden.waardenlijsten import voldoet_aan_domein

_XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"
# Naam van de standaardlayout als het schema er geen noemt (``layout``).
_STANDAARD_LAYOUT = "standaard"

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
    if len(row) >= n:
        return row[:n]
    return row + [""] * (n - len(row))


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


@dataclass(frozen=True)
class _Layout:
    """Eén veldvolgorde van een recordtype (zie ``layout``/``varianten`` in het schema).

    ``kolommen`` zijn de posities die de layout vult: ``fields`` plus, bij de
    standaardlayout, de spiegelkolommen (:func:`extra_kolommen`).
    """

    naam: str
    fields: list[str]
    kolommen: list[str]
    optioneel: frozenset[str]
    uit_bestandsnaam: tuple[str, ...] = ()


def _layouts(recordschema: dict) -> list[_Layout]:
    """De standaardlayout, gevolgd door de varianten uit het schema (#236, #321)."""
    optioneel = frozenset(recordschema.get("optionele_achtervelden", []))
    standaard = _Layout(
        naam=recordschema.get("layout", _STANDAARD_LAYOUT),
        fields=recordschema["fields"],
        kolommen=[*recordschema["fields"], *extra_kolommen(recordschema)],
        optioneel=optioneel,
    )
    varianten = [
        _Layout(
            naam=naam,
            fields=variant["fields"],
            kolommen=variant["fields"],
            optioneel=optioneel,
            uit_bestandsnaam=tuple(variant.get("uit_bestandsnaam", [])),
        )
        for naam, variant in recordschema.get("varianten", {}).items()
    ]
    return [standaard, *varianten]


def _lengtefout(fields: list[str], layout: _Layout) -> str | None:
    """Fail-closed op de regellengte (#257, #281).

    Lege achtervelden vallen bij het inlezen weg (zie :func:`_lees_regels`),
    dus een ontbrekend veld is afwezig of leeg; alleen ``optionele_achtervelden``
    mogen dat zijn.
    """
    extra = fields[len(layout.kolommen) :]
    if any(extra):
        return f"heeft gevulde velden voorbij de schemabreedte: {extra}"
    ontbrekend = [v for v in layout.fields[len(fields) :] if v not in layout.optioneel]
    if ontbrekend:
        return f"mist verplichte velden aan het eind (afwezig of leeg): {ontbrekend}"
    return None


def _herkenningsfouten(
    regels: list[tuple[int, list[str]]], layout: _Layout, recordschema: dict
) -> list[list[str]]:
    """Per regel de ``herkenning``-velden die in ``layout`` buiten hun domein vallen."""
    velden = [v for v in recordschema.get("herkenning", []) if v in layout.fields]
    if not velden:
        return [[] for _ in regels]
    positie = {veld: layout.fields.index(veld) for veld in velden}
    waarden = pl.DataFrame(
        {
            veld: [_normalize_row(f, i + 1)[i] for _, f in regels]
            for veld, i in positie.items()
        },
        schema=dict.fromkeys(velden, pl.Utf8),
    )
    passend = waarden.select(
        voldoet_aan_domein(pl.col(veld), recordschema["domeinen"][veld])
        for veld in velden
    )
    return [
        [veld for veld, past in zip(velden, rij, strict=True) if not past]
        for rij in passend.iter_rows()
    ]


def _passingsfouten(
    regels: list[tuple[int, list[str]]], layout: _Layout, recordschema: dict
) -> list[str | None]:
    """Per regel waarom hij niet op ``layout`` past, of ``None``."""
    herkenning = _herkenningsfouten(regels, layout, recordschema)
    return [
        _lengtefout(fields, layout)
        or (f"waarden buiten hun domein in {buiten}" if buiten else None)
        for (_, fields), buiten in zip(regels, herkenning, strict=True)
    ]


def _kies_layout(
    path: Path, rt: str, regels: list[tuple[int, list[str]]], recordschema: dict
) -> _Layout:
    """De ene layout waarop alle regels van ``rt`` passen; anders ``ValueError``.

    Een regel die op geen of op meer dan één layout past, zou stil in verkeerde
    kolommen landen; dat is altijd een error. Gemengde layouts binnen één
    bestand ook: één levering komt uit één aanmaakproces.
    """
    layouts = _layouts(recordschema)
    fouten = {
        layout.naam: _passingsfouten(regels, layout, recordschema) for layout in layouts
    }
    gekozen: set[str] = set()
    for i, (regelnr, _) in enumerate(regels):
        passend = [naam for naam, per_regel in fouten.items() if per_regel[i] is None]
        if len(passend) == 1:
            gekozen.add(passend[0])
            continue
        plek = f"{path}: regel {regelnr} ({rt})"
        if len(layouts) == 1:
            raise ValueError(f"{plek} {fouten[layouts[0].naam][i]}")
        if not passend:
            details = "; ".join(
                f"{naam}: {per_regel[i]}" for naam, per_regel in fouten.items()
            )
            raise ValueError(f"{plek} past op geen enkele layout ({details})")
        raise ValueError(f"{plek} past op meer dan één layout: {passend}")
    if len(gekozen) > 1:
        raise ValueError(
            f"{path}: {rt} gebruikt meerdere layouts in één bestand: {sorted(gekozen)}"
        )
    return next(layout for layout in layouts if layout.naam in gekozen)


def _uit_bestandsnaam(
    path: Path, schema_name: str, velden: tuple[str, ...]
) -> dict[str, str]:
    """Waarden die een layout niet in de regel heeft, wel in de bestandsnaam (#236)."""
    if not velden:
        return {}
    patroon = bestandsnaam_patroon(schema_name)
    match = re.match(patroon, path.name) if patroon else None
    gevonden = match.groupdict() if match else {}
    if any(not gevonden.get(veld) for veld in velden):
        raise ValueError(
            f"{path}: de layout haalt {list(velden)} uit de bestandsnaam, maar "
            f"{path.name!r} volgt het patroon {patroon!r} niet"
        )
    return {veld: gevonden[veld] for veld in velden}


def _naar_frame(
    regels: list[tuple[int, list[str]]],
    layout: _Layout,
    standaard: _Layout,
    aanvulling: dict[str, str],
) -> pl.DataFrame:
    """Regels in ``layout`` als frame met de kolommen van de standaardlayout."""
    rijen = [_normalize_row(f, len(layout.kolommen)) for _, f in regels]
    positie = {kolom: i for i, kolom in enumerate(layout.kolommen)}
    return pl.DataFrame(
        {
            kolom: [r[positie[kolom]] for r in rijen]
            if kolom in positie
            else [aanvulling.get(kolom, "")] * len(rijen)
            for kolom in standaard.kolommen
        },
        schema=dict.fromkeys(standaard.kolommen, pl.Utf8),
    )


def _parseer(
    path: Path, schema_name: str
) -> tuple[dict[str, pl.DataFrame], dict[str, dict]]:
    """Frames per recordtype en, per recordtype met varianten, de gekozen layout."""
    schema = load_schema(schema_name)
    regels_per_type: dict[str, list[tuple[int, list[str]]]] = {rt: [] for rt in schema}
    for regelnr, fields in enumerate(_lees_regels(path), start=1):
        rt = fields[0]
        if rt not in regels_per_type:
            raise ValueError(
                f"{path}: regel {regelnr} heeft een onbekend recordtype {rt!r}"
            )
        regels_per_type[rt].append((regelnr, fields))

    frames: dict[str, pl.DataFrame] = {}
    varianten: dict[str, dict] = {}
    for rt, regels in regels_per_type.items():
        if not regels:
            continue
        layout = _kies_layout(path, rt, regels, schema[rt])
        aanvulling = _uit_bestandsnaam(path, schema_name, layout.uit_bestandsnaam)
        frames[rt] = _naar_frame(regels, layout, _layouts(schema[rt])[0], aanvulling)
        if "varianten" in schema[rt]:
            varianten[rt] = {"variant": layout.naam}
            if aanvulling:
                varianten[rt]["uit_bestandsnaam"] = aanvulling
    return frames, varianten


def read_multi_record_csv(
    path: str | Path,
    schema_name: str,
) -> dict[str, pl.DataFrame]:
    """Lees een multi-record CSV-bestand in en splits per recordtype.

    Geschikt voor elk DUO-bestandstype dat de multi-record CSV-structuur
    gebruikt (RO, GRONDSLAG IP MBO, …). Kolomnamen komen uit het opgegeven
    schema-TOML. Fail-closed (#257, #281): een onbekend recordtype, een
    gevuld veld voorbij de schemabreedte (incl. gedeclareerde spiegelvelden)
    of een ontbrekend verplicht achterveld is een teken dat het bestand niet
    is wat het zegt te zijn, en breekt de ingest in plaats van stil te worden
    genegeerd, afgeknipt of aangevuld. Alleen de ``optionele_achtervelden``
    van een recordtype mogen aan het eind ontbreken; die worden leeg aangevuld.

    Een recordtype met ``varianten`` (#236, #321) wordt per regel aan één
    layout toegewezen; welke staat in :func:`layoutvarianten`. De kolomset is
    altijd die van de standaardlayout.

    Args:
        path:        Pad naar het bronbestand.
        schema_name: Naam van het schema (bijv. ``"ro"`` of ``"grondslag"``).

    Returns:
        Dict met recordtype-code als sleutel en een DataFrame als waarde.

    Raises:
        FileNotFoundError: Als het bronbestand of schema niet bestaat.
        ValueError: Als het bestand leeg is, een regel een onbekend
            recordtype heeft, een gevuld veld voorbij de schemabreedte of een
            ontbrekend verplicht achterveld heeft, of niet eenduidig op één
            layout past.
    """
    return _parseer(Path(path), schema_name)[0]


def layoutvarianten(path: str | Path, schema_name: str) -> dict[str, dict]:
    """Per recordtype met varianten: de gekozen layout, voor ``quality.json``.

    ``{"VLP": {"variant": "officieel", "uit_bestandsnaam": {"BRIN": "97XX"}}}``:
    waarden uit de bestandsnaam zijn een provenance-beslissing, geen stille
    aanname (#236).
    """
    return _parseer(Path(path), schema_name)[1]


def inventariseer_regels(path: str | Path, schema_name: str) -> dict:
    """Tel per spiegelpositie de regels die afwijken van het veld dat ze herhalen.

    Onbekende recordtypes en velden voorbij de schemabreedte breken
    :func:`read_multi_record_csv` sinds #257 fail-closed; ze kunnen in een
    bestand dat de pipeline haalt niet voorkomen en staan daarom niet in dit
    rapport (#292). Een waardeverschil op een spiegelpositie is geen
    schemaoverschrijding en komt wél door de ingest heen (#120).

    Returns:
        ``spiegel_afwijkingen``: recordtype → kolom (:func:`extra_kolommen`)
        → aantal regels waarin die positie níet gelijk is aan het veld dat ze
        lijkt te herhalen.
    """
    schema = load_schema(schema_name)
    spiegel: dict[str, dict[str, int]] = {}
    for fields in _lees_regels(Path(path)):
        rt = fields[0]
        if rt not in schema:
            continue
        kolommen = schema[rt]["fields"]
        rij = dict(zip(kolommen, _normalize_row(fields, len(kolommen)), strict=True))
        extra = fields[len(kolommen) :]
        for (kolom, veld), waarde in zip(
            extra_kolommen(schema[rt]).items(), extra, strict=False
        ):
            if waarde != rij[veld]:
                per_kolom = spiegel.setdefault(rt, {})
                per_kolom[kolom] = per_kolom.get(kolom, 0) + 1
    return {"spiegel_afwijkingen": dict(sorted(spiegel.items()))}


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


def _tbgi_structuur(velden: dict[str, list[str]]) -> dict[str, dict[str, str | None]]:
    """Toegestane kind-tags per XML-groep uit het schema: tag → kindgroep of None.

    Alleen de eigen velden van een groep staan als kind in de XML; wat een
    kind-rij van zijn ouder erft (``_TBGI_INSCHRIJVING_CONTEXT``) staat op de ouder.
    """

    def eigen(tabel: str, context: tuple[str, ...]) -> dict[str, str | None]:
        return {_TBGI_TAG.get(v, v): None for v in velden[tabel] if v not in context}

    teldatum_context = (*_TBGI_INSCHRIJVING_CONTEXT, "Teldatum")
    signaal = {v: None for v in velden["Signaal"] if v.startswith("Signaal")}
    return {
        "Bekostigingsgrondslagen": {
            "Inschrijving": "Inschrijving",
            "Diploma": "Diploma",
        },
        "Inschrijving": {v: None for v in velden["Inschrijving"]}
        | {"Teldatum": "Teldatum"},
        "Teldatum": eigen("Teldatum", _TBGI_INSCHRIJVING_CONTEXT)
        | {_TBGI_BPV: _TBGI_BPV, "Signaal": "Signaal"},
        _TBGI_BPV: eigen(_TBGI_BPV, teldatum_context),
        "Diploma": {v: None for v in velden["Diploma"]} | {"Signaal": "Signaal"},
        "Signaal": signaal | {"Parameter": "Parameter"},
        "Parameter": {v: None for v in velden["Signaal"] if v.startswith("Parameter")},
    }


def _tel_onbekende_elementen(
    elem: ET.Element,
    groep: str,
    structuur: dict[str, dict[str, str | None]],
    gevonden: dict[str, dict[str, int]],
) -> None:
    for kind in elem:
        kindgroep = structuur[groep].get(kind.tag, False)
        if kindgroep is False:
            per_tag = gevonden.setdefault(groep, {})
            per_tag[kind.tag] = per_tag.get(kind.tag, 0) + 1
        elif kindgroep:
            _tel_onbekende_elementen(kind, kindgroep, structuur, gevonden)


def inventariseer_xml_elementen(path: str | Path, schema_name: str = "tbgi") -> dict:
    """Tel XML-elementen die het schema niet kent, per groep en tagnaam.

    ``read_tbgi`` leest alleen de schemavelden; een element dat DUO toevoegt
    verdween zonder spoor (#324). Het bestand breekt niet: DUO mag XML
    uitbreiden, dus dit blijft een warning in ``quality.json``.

    Returns:
        ``onbekende_xml_elementen``: groep → tagnaam → aantal.
    """
    velden = {tabel: spec["fields"] for tabel, spec in load_schema(schema_name).items()}
    root = ET.parse(path).getroot()
    gevonden: dict[str, dict[str, int]] = {}
    _tel_onbekende_elementen(
        root, "Bekostigingsgrondslagen", _tbgi_structuur(velden), gevonden
    )
    return {
        "onbekende_xml_elementen": {
            groep: dict(sorted(tags.items()))
            for groep, tags in sorted(gevonden.items())
        }
    }


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
