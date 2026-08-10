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
unit-testbaar is.
"""

from __future__ import annotations

import functools
import tomllib
from pathlib import Path

import polars as pl

_METADATA = Path(__file__).parent / "metadata"

# Leerwegen die in de indicator-populatie vallen (bijlage 3). Alleen
# 'ov' en 'od' blijven expliciet buiten beschouwing.
_POPULATIE_UITSLUIT_LEERWEGEN = {"ov", "od"}

# Minimale omvang van de noemer voordat een indicator beoordeeld kan worden.
_MIN_NOEMER = 12

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


def normen_per_niveau(indicator: str) -> dict[int, dict[str, int | None]]:
    """Alle normen voor een indicator, geïndexeerd op niveau."""
    sleutel = _INDICATOR_SLEUTELS.get(indicator, indicator)
    return _laad_normen().get(sleutel, {})


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


_ENTREE_CATEGORIEEN = [
    "Doorstroom met diploma",
    "Doorstroom zonder diploma",
    "Uitstroom met diploma",
    "Uitstroom zonder diploma",
]


def entree_indicatoren(df: pl.DataFrame) -> pl.DataFrame:
    """Entree-uitstroom/doorstroom in vier categorieën (hoofdstuk 5).

    Categorieën per niveau-1-inschrijving, uitgesplitst naar het
    behalen van een diploma binnen het cursusjaar:
    doorstroom met/zonder diploma en uitstroom met/zonder diploma.
    De vier aandelen tellen samen op tot 100% van de niveau-1-populatie.
    """
    vereist = {"Niveau", "_entree_doorstroom", "_entree_uitstroom"}
    if not vereist.issubset(df.columns):
        return pl.DataFrame(
            schema={
                "Categorie": pl.Utf8,
                "Aantal": pl.Int64,
                "Aandeel (%)": pl.Float64,
            }
        )

    entree = df.filter(_niveau_num(pl.col("Niveau")) == 1)

    if entree.is_empty():
        return pl.DataFrame(
            schema={
                "Categorie": pl.Utf8,
                "Aantal": pl.Int64,
                "Aandeel (%)": pl.Float64,
            }
        )

    gediplomeerd = pl.col("_gediplomeerd_in_jaar").fill_null(False)
    doorstroom = pl.col("_entree_doorstroom").fill_null(False)
    uitstroom = pl.col("_entree_uitstroom").fill_null(False)

    cats = (
        entree.with_columns(
            pl.when(doorstroom & gediplomeerd)
            .then(pl.lit("Doorstroom met diploma"))
            .when(doorstroom & ~gediplomeerd)
            .then(pl.lit("Doorstroom zonder diploma"))
            .when(uitstroom & gediplomeerd)
            .then(pl.lit("Uitstroom met diploma"))
            .otherwise(pl.lit("Uitstroom zonder diploma"))
            .alias("Categorie")
        )
        .group_by("Categorie")
        .agg(pl.len().alias("Aantal"))
    )

    totaal = cats["Aantal"].sum()
    return (
        cats.with_columns(
            (pl.col("Aantal") / totaal * 100).round(1).alias("Aandeel (%)")
        )
        .sort("Categorie")
        .select(["Categorie", "Aantal", "Aandeel (%)"])
    )


def entree_totaal(df: pl.DataFrame) -> int:
    """Aantal niveau-1-inschrijvingen (noemer voor de Entree-indicatoren)."""
    if "Niveau" not in df.columns:
        return 0
    return int(df.filter(_niveau_num(pl.col("Niveau")) == 1).height)
