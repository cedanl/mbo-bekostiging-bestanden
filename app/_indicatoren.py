"""Indicatorlogica voor de standaard Studiesucces (onderwijsresultaten).

Implementatie van de regels uit "Definitie indicatoren en toelichting
bestanden onderwijsresultaten voor het bekostigd MBO" (31 mei 2024):

- Normen voor voldoende en hoog per opleidingsniveau (tabel 1 en 2),
  gelezen uit ``metadata/normen.toml``.
- Berekend oordeel per opleiding (tabel 3), inclusief omgang met
  ontbrekende indicatoren en te kleine noemers (minimaal 12).
- Populatieregels: alleen leerwegen bol/dt-bol/bbl/ex (ov en od
  buiten beschouwing) en niveau >= 2 (bijlage 3).
- Entree-uitstroom/doorstroom in vier categorieën (hoofdstuk 5).

Deze module is bewust onafhankelijk van Streamlit, zodat de logica
unit-testbaar is. Ze staat in ``app/`` (niet in de kernpackage): het is
presentatielogica voor het dashboard, door niemand anders geïmporteerd (#253).
"""

from __future__ import annotations

import functools
import tomllib

import polars as pl

from mbo_bekostiging_bestanden.filters import peildatum, schooljaar_van
from mbo_bekostiging_bestanden.metadata import SCHEMA_DIR

_METADATA = SCHEMA_DIR

# Leerwegen die in de indicator-populatie vallen (bijlage 3). Alleen
# 'ov' en 'od' blijven expliciet buiten beschouwing.
_POPULATIE_UITSLUIT_LEERWEGEN = {"ov", "od"}

# Minimale omvang van de noemer voordat een indicator beoordeeld kan worden.
_MIN_NOEMER = 12

# Noemer- en tellervlag per indicator in fact_inschrijving_schooljaar (#136).
_RENDEMENT_VLAGGEN = {
    "jr": ("_jr_noemer", "_jr_teller"),
    "dr": ("_dr_noemer", "_dr_teller"),
}
_RENDEMENT_GROEP = ["Schooljaar", "Niveau"]
# JR en DR worden vanaf niveau 2 beoordeeld; niveau 1 heeft entree-indicatoren.
_RENDEMENT_MIN_NIVEAU = 2

# Een inschrijving: persoon × instelling × volgnummer (PvE §16.5.1).
_INSCHRIJVING = ["BRIN", "_persoon_id", "Inschrijvingvolgnummer"]

# Korte indicatornamen → sleutels in normen.toml.
_INDICATOR_SLEUTELS = {
    "jr": "jaarresultaat",
    "dr": "diplomaresultaat",
    "sr": "startersresultaat",
}


# ---------------------------------------------------------------------------
# Normen
# ---------------------------------------------------------------------------


@functools.cache
def _laad_normen() -> dict[str, dict[int, dict[str, int | None]]]:
    """Lees normen.toml: indicator → niveau → {voldoende, hoog}."""
    pad = _METADATA / "normen.toml"
    with pad.open("rb") as f:
        ruw = tomllib.load(f)
    normen: dict[str, dict[int, dict[str, int | None]]] = {}
    for indicator, per_soort in ruw.items():
        normen[indicator] = {}
        niveaus = {
            int(niveau_str)
            for per_niveau in per_soort.values()
            for niveau_str in per_niveau
        }
        for niveau in sorted(niveaus):
            normen[indicator][niveau] = {
                soort: per_niveau.get(str(niveau))
                for soort, per_niveau in per_soort.items()
            }
    return normen


def norm_voor(indicator: str, niveau: int, soort: str) -> int | None:
    """Geef de norm voor een indicator op een niveau, of ``None``.

    ``indicator`` is ``"jr"``/``"dr"``/``"sr"``, ``soort`` is
    ``"voldoende"`` of ``"hoog"``.
    """
    sleutel = _INDICATOR_SLEUTELS.get(indicator, indicator)
    return _laad_normen().get(sleutel, {}).get(niveau, {}).get(soort)


# ---------------------------------------------------------------------------
# Populatieregels
# ---------------------------------------------------------------------------


def _niveau_num(col: pl.Expr) -> pl.Expr:
    """Numeriek niveau uit ``"MBO-2"`` → ``2``."""
    return col.str.extract(r"(\d+)$").cast(pl.Int32, strict=False)


def populatie_regele_filter(
    df: pl.DataFrame,
    min_niveau: int = 2,
) -> pl.DataFrame:
    """Filter de inschrijvingen op de indicator-populatie (bijlage 3).

    Behoudt alleen leerwegen anders dan 'ov'/'od' en niveaus vanaf
    ``min_niveau``.  Kolommen die ontbreken worden genegeerd.
    """
    if "Leertraject" in df.columns:
        leerweg = pl.col("Leertraject").str.to_lowercase()
        df = df.filter(
            leerweg.is_not_null() & ~leerweg.is_in(_POPULATIE_UITSLUIT_LEERWEGEN)
        )

    if "Niveau" in df.columns:
        niveau = _niveau_num(pl.col("Niveau"))
        df = df.filter(niveau.is_not_null() & (niveau >= min_niveau))

    return df


def _normen(indicator: str) -> pl.DataFrame:
    """Normen voor voldoende en hoog per numeriek niveau."""
    per_niveau = _laad_normen().get(_INDICATOR_SLEUTELS.get(indicator, indicator), {})
    return pl.DataFrame(
        {
            "_niveau": list(per_niveau),
            "Norm voldoende": [n.get("voldoende") for n in per_niveau.values()],
            "Norm hoog": [n.get("hoog") for n in per_niveau.values()],
        },
        schema={"_niveau": pl.Int32, "Norm voldoende": pl.Int64, "Norm hoog": pl.Int64},
    )


def rendement(jaren: pl.DataFrame, indicator: str) -> pl.DataFrame:
    """JR of DR per schooljaar en niveau uit ``fact_inschrijving_schooljaar``.

    Noemer en teller zijn de vlaggen die de ETL per schooljaar berekent
    (``_jr_noemer``/``_jr_teller``, ``_dr_noemer``/``_dr_teller``); hier wordt
    niets herberekend. Alleen de indicator-populatie (bijlage 3) telt mee.

    Returns:
        ``Schooljaar``, ``Niveau``, ``Noemer``, ``Teller``, ``Percentage``,
        ``Norm voldoende``, ``Norm hoog`` en ``Voldoet`` (aan de voldoende-norm).
    """
    noemer, teller = _RENDEMENT_VLAGGEN[indicator]
    in_noemer = pl.col(noemer).fill_null(False)
    return (
        populatie_regele_filter(jaren, min_niveau=_RENDEMENT_MIN_NIVEAU)
        .filter(in_noemer)
        .group_by(_RENDEMENT_GROEP)
        .agg(
            in_noemer.sum().alias("Noemer"),
            (in_noemer & pl.col(teller).fill_null(False)).sum().alias("Teller"),
        )
        .with_columns(
            (pl.col("Teller") / pl.col("Noemer") * 100).round(1).alias("Percentage"),
            _niveau_num(pl.col("Niveau")).alias("_niveau"),
        )
        .join(_normen(indicator), on="_niveau", how="left")
        .with_columns(
            (pl.col("Percentage") >= pl.col("Norm voldoende")).alias("Voldoet")
        )
        .drop("_niveau")
        .sort(_RENDEMENT_GROEP)
    )


# ---------------------------------------------------------------------------
# Berekend oordeel (tabel 3)
# ---------------------------------------------------------------------------


def indicator_voldoet(
    waarde: float | None,
    noemer: int | None,
    norm: int | None,
    *,
    mag_niet_uiterste: bool = False,
) -> bool | None:
    """Bepaal of een indicator aan de norm voldoet.

    Returns:
        ``True`` als de indicator voldoet, ``False`` als deze niet voldoet,
        ``None`` als de indicator niet beoordeeld kan worden (onbekende
        waarde, noemer < 12, of 0/100 bij ``mag_niet_uiterste``).
    """
    if waarde is None or noemer is None or norm is None:
        return None
    if noemer < _MIN_NOEMER:
        return None
    if mag_niet_uiterste and waarde in (0.0, 100.0):
        return None
    return waarde >= norm


def _bepaal_oordeel(
    statuses: list[bool | None],
) -> str:
    """Berekend oordeel o.b.v. per-indicator-status (tabel 3, §3.5).

    ``statuses``: de uitkomsten van :func:`indicator_voldoet`, in vaste
    volgorde JR, DR, SR.  ``None`` = indicator ontbreekt/onbeoordeelbaar.

    Het oordeel ``"hoog"`` wordt hier nooit bepaald — dat gebeurt in
    :func:`bereken_oordeel`, omdat daarvoor ook de hoge normen van JR/DR
    nodig zijn.

    Returns:
        ``"voldoende"``, ``"onvoldoende"`` of ``"niet_te_bepalen"``.
    """
    aanwezig = [s for s in statuses if s is not None]
    ontbrekend = len(statuses) - len(aanwezig)

    # Twee of meer indicatoren ontbreken → geen oordeel (§3.5).
    if ontbrekend >= 2:
        return "niet_te_bepalen"

    # Eén indicator ontbreekt → oordeel alleen als beide aanwezige
    # indicatoren dezelfde richting uitwijzen (§3.5).
    if ontbrekend == 1:
        if len(set(aanwezig)) != 1:
            return "niet_te_bepalen"
        return "voldoende" if aanwezig[0] else "onvoldoende"

    # Geen ontbrekend: ≥2 van de 3 voldoet → voldoende (tabel 3).
    if aanwezig.count(True) >= 2:
        return "voldoende"
    return "onvoldoende"


def bereken_oordeel(
    jr: dict[str, float | int | None] | None,
    dr: dict[str, float | int | None] | None,
    sr: dict[str, float | int | None] | None,
    niveau: int,
) -> tuple[str, list[bool | None], dict[str, int | None]]:
    """Berekend oordeel voor een opleiding × niveau.

    Args:
        jr/dr/sr: dict met ``waarde`` (percentage) en ``noemer``, of ``None``
            als de indicator geheel ontbreekt.
        niveau: opleidingsniveau (2, 3 of 4), bepaalt de norm.

    Returns:
        Tuple ``(oordeel, statuses, hoge_normen)`` met het oordeel
        (``"hoog"``/``"voldoende"``/``"onvoldoende"``/``"niet_te_bepalen"``),
        de per-indicator-status in volgorde JR/DR/SR, en de hoge normen
        per indicator.
    """
    normen_vold: dict[str, int | None] = {}
    for indicator in ("jr", "dr", "sr"):
        normen_vold[indicator] = norm_voor(indicator, niveau, "voldoende")
    hoge_normen: dict[str, int | None] = {
        "jr": norm_voor("jr", niveau, "hoog"),
        "dr": norm_voor("dr", niveau, "hoog"),
        "sr": norm_voor("sr", niveau, "hoog"),
    }

    def _status(
        indic: dict[str, float | int | None] | None,
        norm: int | None,
        mag_niet_uiterste: bool,
    ) -> bool | None:
        if indic is None:
            return None
        waarde = indic.get("waarde")
        noemer = indic.get("noemer")
        if waarde is None:
            return None
        return indicator_voldoet(
            float(waarde),
            int(noemer) if noemer is not None else None,
            norm,
            mag_niet_uiterste=mag_niet_uiterste,
        )

    statuses = [
        _status(jr, normen_vold["jr"], mag_niet_uiterste=True),
        _status(dr, normen_vold["dr"], mag_niet_uiterste=True),
        _status(sr, normen_vold["sr"], mag_niet_uiterste=False),
    ]

    # Hoog-oordeel: alle drie voldoende én (JR of DR) ≥ hoge norm.
    if all(s is True for s in statuses):
        _jr_w = jr.get("waarde") if jr else None
        jr_val = float(_jr_w) if isinstance(_jr_w, (int, float)) else None
        _dr_w = dr.get("waarde") if dr else None
        dr_val = float(_dr_w) if isinstance(_dr_w, (int, float)) else None
        jr_hoog = (
            hoge_normen["jr"] is not None
            and jr_val is not None
            and jr_val >= hoge_normen["jr"]
        )
        dr_hoog = (
            hoge_normen["dr"] is not None
            and dr_val is not None
            and dr_val >= hoge_normen["dr"]
        )
        if jr_hoog or dr_hoog:
            return "hoog", statuses, hoge_normen

    oordeel = _bepaal_oordeel(statuses)
    return oordeel, statuses, hoge_normen


# ---------------------------------------------------------------------------
# Entree-indicatoren (hoofdstuk 5)
# ---------------------------------------------------------------------------


_ENTREE_NOEMER = "_entree_noemer"
_ENTREE_SCHEMA = {"Categorie": pl.Utf8, "Aantal": pl.Int64, "Aandeel (%)": pl.Float64}


def entree_indicatoren(jaren: pl.DataFrame) -> pl.DataFrame:
    """Entree-uitstroom/doorstroom in vier categorieën (hoofdstuk 5).

    ``jaren`` is ``fact_inschrijving_schooljaar``: de populatie
    (``_entree_noemer``) zijn de entree-hoofdinschrijvingen die Entree na het
    schooljaar verlaten (#306). Uitgesplitst naar doorstroom/uitstroom en een
    diploma in dat schooljaar; de vier aandelen tellen op tot 100%.
    """
    vereist = {
        _ENTREE_NOEMER,
        "_entree_doorstroom",
        "_gediplomeerd_in_jaar",
    }
    if not vereist.issubset(jaren.columns):
        return pl.DataFrame(schema=_ENTREE_SCHEMA)
    entree = jaren.filter(pl.col(_ENTREE_NOEMER))
    if entree.is_empty():
        return pl.DataFrame(schema=_ENTREE_SCHEMA)

    gediplomeerd = pl.col("_gediplomeerd_in_jaar").fill_null(False)
    richting = (
        pl.when(pl.col("_entree_doorstroom"))
        .then(pl.lit("Doorstroom"))
        .otherwise(pl.lit("Uitstroom"))
    )
    diploma = (
        pl.when(gediplomeerd)
        .then(pl.lit(" met diploma"))
        .otherwise(pl.lit(" zonder diploma"))
    )
    cats = (
        entree.with_columns((richting + diploma).alias("Categorie"))
        .group_by("Categorie")
        .agg(pl.len().cast(pl.Int64).alias("Aantal"))
    )
    return (
        cats.with_columns(
            (pl.col("Aantal") / pl.col("Aantal").sum() * 100)
            .round(1)
            .alias("Aandeel (%)")
        )
        .sort("Categorie")
        .select(list(_ENTREE_SCHEMA))
    )


def entree_totaal(jaren: pl.DataFrame) -> int:
    """Omvang van de Entree-populatie (noemer van :func:`entree_indicatoren`)."""
    if _ENTREE_NOEMER not in jaren.columns:
        return 0
    return int(jaren[_ENTREE_NOEMER].sum())


def ingeschreven_na_peildatum(perioden: pl.DataFrame, schooljaren: list[int]) -> int:
    """Inschrijvingen die in een van ``schooljaren`` ná 1 oktober begonnen.

    Die tellen dat schooljaar niet mee op de peildatum. Uit ``DatumInschrijving``
    en per inschrijving één keer, dus onafhankelijk van haar aantal perioden;
    vervangt de legacy-periodevlag ``_ingeschreven_jaar_later`` (#201).
    """
    if not {"DatumInschrijving", *_INSCHRIJVING} <= set(perioden.columns):
        return 0
    datum = pl.col("DatumInschrijving").cast(pl.Date, strict=False)
    schooljaar = schooljaar_van(datum)
    return (
        perioden.filter(schooljaar.is_in(schooljaren) & (datum > peildatum(schooljaar)))
        .select(_INSCHRIJVING)
        .unique()
        .height
    )
