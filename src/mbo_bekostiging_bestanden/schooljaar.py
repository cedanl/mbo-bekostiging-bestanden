"""Schooljaar-grain: één rij per persoon × BRIN × inschrijving × schooljaar (#164).

Schooljaar ``t`` loopt van 1-8-t t/m 31-7-(t+1); de peildatum is 1-10-t.
``fact_inschrijving`` heeft de grain van een ISP-periode en blijft de bron
voor reconstructie. Jaargebonden vlaggen (actief, hoofdinschrijving, telling,
bekostigd, JR, DR) horen bij één schooljaar en staan daarom hier.

Regels:

- Een periode telt in elk schooljaar waarvan zij de peildatum dekt (#193).
  Het einde is ``_periode_einde`` (zie
  :func:`~mbo_bekostiging_bestanden.transform._voeg_periode_einde_toe`),
  begrensd door de peildatum van de levering: een levering zegt niets over
  1-oktobers na haar eigen peildatum. Zonder einde en zonder peildatum telt
  alleen het eerste schooljaar.
- Hoofdinschrijving: één per persoon × BRIN × schooljaar, over leveringen heen
  (na canonicalisatie, #174): hoogste niveau, dan laagste CREBO, dan meest
  recente ``DatumBegin``, dan inschrijvingvolgnummer.
- TBGI levert inschrijvingen, geen ISP-perioden: een TBGI-inschrijving telt
  alleen in de schooljaren waarvoor zij een 1-oktober-``Teldatum`` heeft (#197).
  ``DatumInschrijving`` zegt niets over welke peildata de levering waarneemt,
  en een inschrijving zonder teldatum komt volgens PvE §16 niet in aanmerking.
- JR: gediplomeerd als ``DIP_DatumResultaat`` in het schooljaar zelf valt (#194).
- DR: uitstromer als de persoon van de hoofdinschrijving in ``t`` in ``t+1``
  bij geen enkele instelling in de dataset staat ingeschreven (#118), **en**
  ``t+1`` waarneembaar is (de peildatum 1-10-(t+1) ligt vóór de laatste
  peildatum van een levering van de eigen BRIN). Een overstap naar een
  instelling buiten de dataset blijft uitstroom (``quality.json`` →
  ``dr_scope``).
- Entree (#306): een niveau-1-hoofdinschrijving in ``t`` die Entree verlaat,
  met ``t+1`` waarneembaar. Doorstroom = in ``t+1`` niveau >= 2, bij welke
  instelling in de dataset ook; uitstroom = in ``t+1`` nergens meer
  ingeschreven. Wie in Entree blijft, valt buiten de populatie.
"""

import polars as pl

from mbo_bekostiging_bestanden.transform import (
    _PERIODE_EINDE,
    _STUDIEJAAR_EIND_DAG,
    _STUDIEJAAR_EIND_MONTH,
    _STUDIEJAAR_START_DAG,
    _STUDIEJAAR_START_MONTH,
    _TELDATUM_DAG,
    _TELDATUM_MONTH,
    BRON,
    BRON_TBGI,
    _niveau_numeriek,
    _voeg_periode_einde_toe,
)

FEIT = "fact_inschrijving_schooljaar"
SCHOOLJAAR = "Schooljaar"
PEILDATUM = "Peildatum"
GRAIN = ["BRIN", "_persoon_id", "Inschrijvingvolgnummer", SCHOOLJAAR]
# Per groep precies één hoofdinschrijving (invariant, gecontroleerd in quality).
HOOFDINSCHRIJVING_GROEP = ["BRIN", "_persoon_id", SCHOOLJAAR]
HOOFDINSCHRIJVING = "_hoofdinschrijving"
# DR en Entree zoeken de persoon in t+1 over alle instellingen in de dataset (#118).
VOLGEND_JAAR_GROEP = ["_persoon_id"]
_PEILGRENS = "_peilgrens"
_TELDATUM = "Teldatum"
PEILGRENS = "Peilgrens"
PEILGRENS_BRON = "Peilgrens_bron"
LAATSTE_PEILDATUM = "Laatste_peildatum"
_TBGI_SLEUTEL = ("levering", "BRIN", "_persoon_id", "Inschrijvingvolgnummer")
# TBG-i legt deze per teldatum vast; ze gelden voor dat schooljaar (PvE §16.5.2).
_TELDATUM_ATTRIBUTEN = (
    "Opleidingcode",
    "Niveau",
    "Leertraject",
    "IndicatieBekostigbaar",
)
# Peildatum van een levering, in voorkeursvolgorde (VLP-velden).
_PEILGRENS_KOLOMMEN = ("DatumEindePeriode", "DatumAanmaak")
_JR_DR_MIN_NIVEAU = 2
_ENTREE_NIVEAU = 1
_BEKOSTIGBAAR = "J"
_KOLOMMEN = [
    "levering",
    "BRIN",
    "_persoon_id",
    "Inschrijvingvolgnummer",
    SCHOOLJAAR,
    PEILDATUM,
    "_inschrijving_periode_id",
    "DatumBegin",
    "Opleidingcode",
    "Niveau",
    "Leertraject",
    HOOFDINSCHRIJVING,
    "_telling",
    "_bekostigd",
    "_gediplomeerd_in_jaar",
    "_jr_noemer",
    "_jr_teller",
    "_dr_noemer",
    "_dr_teller",
    "_entree_noemer",
    "_entree_doorstroom",
    "_entree_uitstroom",
]


def _peildatum(jaar: pl.Expr) -> pl.Expr:
    return pl.date(jaar, _TELDATUM_MONTH, _TELDATUM_DAG)


def _eerste_peiljaar(datum: pl.Expr) -> pl.Expr:
    """Schooljaar van de eerste peildatum op of na ``datum``."""
    jaar = datum.dt.year()
    return pl.when(datum <= _peildatum(jaar)).then(jaar).otherwise(jaar + 1)


def _laatste_peiljaar(datum: pl.Expr) -> pl.Expr:
    """Schooljaar van de laatste peildatum op of vóór ``datum``."""
    jaar = datum.dt.year()
    return pl.when(datum >= _peildatum(jaar)).then(jaar).otherwise(jaar - 1)


def observatievenster(
    leveringen: pl.DataFrame, teldata: pl.DataFrame | None = None
) -> pl.DataFrame:
    """Welke peildata een levering kan waarnemen (#211).

    De grens is de peildatum van de levering (VLP ``DatumEindePeriode``, anders
    ``DatumAanmaak``); zonder VLP (TBG-i) de laatste ``Teldatum``. Een levering
    zegt niets over 1-oktobers daarna.

    Returns:
        ``levering``, ``Peilgrens``, ``Peilgrens_bron`` (kolom waaruit de grens
        komt) en ``Laatste_peildatum`` (laatste 1 oktober op of vóór de grens).
    """
    kandidaten = [c for c in _PEILGRENS_KOLOMMEN if c in leveringen.columns]
    venster = leveringen.select("levering", *kandidaten).unique("levering")
    if teldata is not None and _TELDATUM in teldata.columns:
        laatste_teldatum = teldata.group_by("levering").agg(pl.col(_TELDATUM).max())
        venster = venster.join(laatste_teldatum, on="levering", how="left")
        kandidaten.append(_TELDATUM)
    if not kandidaten:
        return venster.with_columns(
            pl.lit(None, dtype=pl.Date).alias(PEILGRENS),
            pl.lit(None, dtype=pl.Utf8).alias(PEILGRENS_BRON),
            pl.lit(None, dtype=pl.Date).alias(LAATSTE_PEILDATUM),
        )
    bron = pl.lit(None, dtype=pl.Utf8)
    for kolom in reversed(kandidaten):
        bron = pl.when(pl.col(kolom).is_not_null()).then(pl.lit(kolom)).otherwise(bron)
    grens = pl.coalesce([pl.col(c) for c in kandidaten])
    return venster.select(
        "levering",
        grens.alias(PEILGRENS),
        bron.alias(PEILGRENS_BRON),
        _peildatum(_laatste_peiljaar(grens)).alias(LAATSTE_PEILDATUM),
    )


def _peilgrens_per_levering(leveringen: pl.DataFrame) -> pl.DataFrame:
    """``levering`` → peildatum van de levering (null als onbekend)."""
    return observatievenster(leveringen).select(
        "levering", pl.col(PEILGRENS).alias(_PEILGRENS)
    )


def _per_schooljaar(perioden: pl.DataFrame) -> pl.DataFrame:
    """Explodeer elke periode naar de schooljaren waarvan zij de peildatum dekt."""
    einde = pl.min_horizontal(_PERIODE_EINDE, _PEILGRENS)
    eerste = _eerste_peiljaar(pl.col("DatumBegin"))
    laatste = pl.when(einde.is_null()).then(eerste).otherwise(_laatste_peiljaar(einde))
    return (
        perioden.drop_nulls("DatumBegin")
        .with_columns(pl.int_ranges(eerste, laatste + 1).alias(SCHOOLJAAR))
        .explode(SCHOOLJAAR, empty_as_null=False)
        .drop_nulls(SCHOOLJAAR)
        .with_columns(
            pl.col(SCHOOLJAAR).cast(pl.Int32),
            _peildatum(pl.col(SCHOOLJAAR)).alias(PEILDATUM),
        )
    )


def _voeg_hoofdinschrijving_toe(df: pl.DataFrame) -> pl.DataFrame:
    """Precies één hoofdinschrijving per persoon × BRIN × schooljaar.

    Een inschrijving zonder bekend niveau is nooit hoofdinschrijving (#130).
    """
    niveau = _niveau_numeriek(pl.col("Niveau"))
    rij = "_rij"
    gekozen = (
        pl.col(rij)
        .sort_by(
            [niveau, pl.col("Opleidingcode"), "DatumBegin", "Inschrijvingvolgnummer"],
            descending=[True, False, True, True],
            nulls_last=True,
        )
        .first()
        .over(HOOFDINSCHRIJVING_GROEP)
    )
    return (
        df.with_row_index(rij)
        .with_columns(
            ((pl.col(rij) == gekozen) & niveau.is_not_null()).alias(HOOFDINSCHRIJVING)
        )
        .drop(rij)
    )


def _in_schooljaar(datum: pl.Expr) -> pl.Expr:
    """Waar als ``datum`` in schooljaar ``t`` valt: 1-8-t t/m 31-7-(t+1)."""
    jaar = pl.col(SCHOOLJAAR)
    begin = pl.date(jaar, _STUDIEJAAR_START_MONTH, _STUDIEJAAR_START_DAG)
    eind = pl.date(jaar + 1, _STUDIEJAAR_EIND_MONTH, _STUDIEJAAR_EIND_DAG)
    return (datum >= begin) & (datum <= eind)


def _voeg_jr_toe(df: pl.DataFrame) -> pl.DataFrame:
    gediplomeerd = _in_schooljaar(pl.col("DIP_DatumResultaat")).fill_null(False)
    return df.with_columns(
        pl.col(HOOFDINSCHRIJVING).alias("_telling"),
        (pl.col("IndicatieBekostigbaar") == _BEKOSTIGBAAR)
        .fill_null(False)
        .alias("_bekostigd"),
        gediplomeerd.alias("_gediplomeerd_in_jaar"),
    ).with_columns(
        pl.col("_telling").alias("_jr_noemer"),
        (pl.col("_telling") & pl.col("_gediplomeerd_in_jaar")).alias("_jr_teller"),
    )


def _voeg_volgend_jaar_toe(df: pl.DataFrame) -> pl.DataFrame:
    """Wat de dataset in ``t+1`` van deze persoon ziet, en of dat waarneembaar is.

    ``_actief_volgend_jaar``: een inschrijving in ``t+1`` bij welke instelling in
    de dataset ook, want uitstroom is instelling-onafhankelijk (#118);
    ``_niveau_volgend_jaar``: het hoogste niveau daarvan (null zonder niveau).
    Waarneembaar blijft per eigen BRIN: een waarneming elders telt alleen
    blijvers, dus zou een onwaarneembaar jaar naar doorstroom scheeftrekken.
    """
    volgend_jaar = df.group_by(
        *VOLGEND_JAAR_GROEP, (pl.col(SCHOOLJAAR) - 1).alias(SCHOOLJAAR)
    ).agg(
        pl.lit(True).alias("_actief_volgend_jaar"),
        _niveau_numeriek(pl.col("Niveau")).max().alias("_niveau_volgend_jaar"),
    )
    laatste_peilgrens = df.group_by("BRIN").agg(
        pl.col(_PEILGRENS).max().alias("_laatste_peilgrens")
    )
    return (
        df.join(volgend_jaar, on=[*VOLGEND_JAAR_GROEP, SCHOOLJAAR], how="left")
        .join(laatste_peilgrens, on="BRIN", how="left")
        .with_columns(
            pl.col("_actief_volgend_jaar").fill_null(False),
            (_peildatum(pl.col(SCHOOLJAAR) + 1) <= pl.col("_laatste_peilgrens"))
            .fill_null(False)
            .alias("_waarneembaar_volgend_jaar"),
        )
    )


def _voeg_dr_toe(df: pl.DataFrame) -> pl.DataFrame:
    niveau_ok = (_niveau_numeriek(pl.col("Niveau")) >= _JR_DR_MIN_NIVEAU).fill_null(
        False
    )
    return df.with_columns(
        (
            pl.col(HOOFDINSCHRIJVING)
            & niveau_ok
            & pl.col("_waarneembaar_volgend_jaar")
            & ~pl.col("_actief_volgend_jaar")
        ).alias("_dr_noemer")
    ).with_columns(
        # Diploma zonder formeel zesjaarsvenster: benadering, zie #119.
        (pl.col("_dr_noemer") & pl.col("DIP_DatumResultaat").is_not_null()).alias(
            "_dr_teller"
        )
    )


def _voeg_entree_toe(df: pl.DataFrame) -> pl.DataFrame:
    """Entree-populatie en haar uitkomst in ``t+1`` (#306)."""
    is_entree = (_niveau_numeriek(pl.col("Niveau")) == _ENTREE_NIVEAU).fill_null(False)
    doorstroom = (pl.col("_niveau_volgend_jaar") > _ENTREE_NIVEAU).fill_null(False)
    uitstroom = ~pl.col("_actief_volgend_jaar")
    return df.with_columns(
        (
            pl.col(HOOFDINSCHRIJVING)
            & is_entree
            & pl.col("_waarneembaar_volgend_jaar")
            & (doorstroom | uitstroom)
        ).alias("_entree_noemer")
    ).with_columns(
        (pl.col("_entree_noemer") & doorstroom).alias("_entree_doorstroom"),
        (pl.col("_entree_noemer") & uitstroom).alias("_entree_uitstroom"),
    )


def _tbgi_waarnemingen(
    inschrijvingen: pl.DataFrame, teldata: pl.DataFrame
) -> pl.DataFrame:
    """TBGI-inschrijving × 1-oktober-teldatum, als periode van één dag.

    Opleiding, niveau, leertraject en bekostigbaarheid komen van de teldatum:
    TBG-i legt ze per teldatum vast, niet per inschrijving.
    """
    if _TELDATUM not in teldata.columns:
        return inschrijvingen.clear().with_columns(
            pl.lit(None, dtype=pl.Date).alias("DatumBegin"),
            pl.lit(None, dtype=pl.Date).alias(_PERIODE_EINDE),
        )
    sleutel = [c for c in _TBGI_SLEUTEL if c in inschrijvingen.columns]
    attributen = [c for c in _TELDATUM_ATTRIBUTEN if c in teldata.columns]
    teldatum = pl.col(_TELDATUM)
    peilmomenten = (
        teldata.filter(
            (teldatum.dt.month() == _TELDATUM_MONTH)
            & (teldatum.dt.day() == _TELDATUM_DAG)
        )
        .select(*sleutel, _TELDATUM, *attributen)
        .unique()
    )
    return (
        inschrijvingen.drop(attributen, strict=False)
        .join(peilmomenten, on=sleutel, how="inner")
        .with_columns(teldatum.alias("DatumBegin"), teldatum.alias(_PERIODE_EINDE))
        .drop(_TELDATUM)
    )


def bouw_inschrijving_schooljaar(
    inschrijvingen: pl.DataFrame,
    leveringen: pl.DataFrame,
    teldata: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Bouw ``fact_inschrijving_schooljaar`` uit canonieke ISP-perioden.

    Args:
        inschrijvingen: Analysetabel op periode-grain (na canonicalisatie), met
                        ``DatumBegin``, ``Niveau``, ``Opleidingcode``,
                        ``IndicatieBekostigbaar`` en ``DIP_DatumResultaat``.
                        Rijen met ``Bron == "TBGI"`` zijn inschrijvingen
                        zonder ISP-periode.
        leveringen:     ``meta_leveringen`` (peildatum per levering).
        teldata:        Rijen met ``Teldatum`` per inschrijving
                        (``detail_bekostiging``); bepalen de schooljaren van
                        TBGI-inschrijvingen.

    Returns:
        Eén rij per ``GRAIN``; leeg (met vast schema) zonder peildatum-dekking.
    """
    tbgi_rij = (
        pl.col(BRON) == BRON_TBGI if BRON in inschrijvingen.columns else pl.lit(False)
    )
    delen = []
    isp = inschrijvingen.filter(~tbgi_rij)
    if "DatumBegin" in isp.columns and not isp.is_empty():
        delen.append(_voeg_periode_einde_toe(isp))
    tbgi = inschrijvingen.filter(tbgi_rij)
    if not tbgi.is_empty():
        delen.append(
            _tbgi_waarnemingen(tbgi, teldata if teldata is not None else pl.DataFrame())
        )
    if not delen:
        return pl.DataFrame(schema=_KOLOMMEN)
    perioden = pl.concat(delen, how="diagonal_relaxed")
    if _PERIODE_EINDE not in perioden.columns:
        perioden = perioden.with_columns(
            pl.lit(None, dtype=pl.Date).alias(_PERIODE_EINDE)
        )
    perioden = perioden.join(
        _peilgrens_per_levering(leveringen), on="levering", how="left"
    )
    for kolom in ("Niveau", "Opleidingcode", "Leertraject", "IndicatieBekostigbaar"):
        if kolom not in perioden.columns:
            perioden = perioden.with_columns(pl.lit(None, dtype=pl.Utf8).alias(kolom))
    if "DIP_DatumResultaat" not in perioden.columns:
        perioden = perioden.with_columns(
            pl.lit(None, dtype=pl.Date).alias("DIP_DatumResultaat")
        )
    df = _voeg_volgend_jaar_toe(
        _voeg_jr_toe(_voeg_hoofdinschrijving_toe(_per_schooljaar(perioden)))
    )
    df = _voeg_entree_toe(_voeg_dr_toe(df))
    return df.select(_KOLOMMEN).sort(GRAIN)
