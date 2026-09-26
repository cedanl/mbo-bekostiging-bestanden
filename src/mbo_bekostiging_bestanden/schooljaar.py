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
- JR: gediplomeerd als ``DIP_DatumResultaat`` in het schooljaar zelf valt (#194).
- DR: uitstromer als de hoofdinschrijving in ``t`` bij dezelfde BRIN geen
  inschrijving in ``t+1`` heeft, **en** ``t+1`` waarneembaar is (de peildatum
  1-10-(t+1) ligt vóór de laatste peildatum van een levering van die BRIN).
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
    _niveau_numeriek,
    _periode_begin_kolom,
    _voeg_periode_einde_toe,
)

SCHOOLJAAR = "Schooljaar"
PEILDATUM = "Peildatum"
GRAIN = ["BRIN", "_persoon_id", "Inschrijvingvolgnummer", SCHOOLJAAR]
_GROEP = ["BRIN", "_persoon_id", SCHOOLJAAR]
_PEILGRENS = "_peilgrens"
# Peildatum van een levering, in voorkeursvolgorde (VLP-velden).
_PEILGRENS_KOLOMMEN = ("DatumEindePeriode", "DatumAanmaak")
_JR_DR_MIN_NIVEAU = 2
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
    "Leertraject",
    "_hoofdinschrijving",
    "_telling",
    "_bekostigd",
    "_gediplomeerd_in_jaar",
    "_jr_noemer",
    "_jr_teller",
    "_dr_noemer",
    "_dr_teller",
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


def _peilgrens_per_levering(leveringen: pl.DataFrame) -> pl.DataFrame:
    """``levering`` → peildatum van de levering (null als onbekend)."""
    kolommen = [pl.col(c) for c in _PEILGRENS_KOLOMMEN if c in leveringen.columns]
    grens = pl.coalesce(kolommen) if kolommen else pl.lit(None, dtype=pl.Date)
    return leveringen.select("levering", grens.alias(_PEILGRENS)).unique("levering")


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
        .over(_GROEP)
    )
    return (
        df.with_row_index(rij)
        .with_columns(
            ((pl.col(rij) == gekozen) & niveau.is_not_null()).alias(
                "_hoofdinschrijving"
            )
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
        pl.col("_hoofdinschrijving").alias("_telling"),
        (pl.col("IndicatieBekostigbaar") == _BEKOSTIGBAAR)
        .fill_null(False)
        .alias("_bekostigd"),
        gediplomeerd.alias("_gediplomeerd_in_jaar"),
    ).with_columns(
        pl.col("_telling").alias("_jr_noemer"),
        (pl.col("_telling") & pl.col("_gediplomeerd_in_jaar")).alias("_jr_teller"),
    )


def _voeg_dr_toe(df: pl.DataFrame) -> pl.DataFrame:
    volgend_jaar_actief = (
        df.select("BRIN", "_persoon_id", (pl.col(SCHOOLJAAR) - 1).alias(SCHOOLJAAR))
        .unique()
        .with_columns(pl.lit(True).alias("_actief_volgend_jaar"))
    )
    laatste_peilgrens = df.group_by("BRIN").agg(
        pl.col(_PEILGRENS).max().alias("_laatste_peilgrens")
    )
    waarneembaar = (
        _peildatum(pl.col(SCHOOLJAAR) + 1) <= pl.col("_laatste_peilgrens")
    ).fill_null(False)
    niveau_ok = (_niveau_numeriek(pl.col("Niveau")) >= _JR_DR_MIN_NIVEAU).fill_null(
        False
    )
    return (
        df.join(volgend_jaar_actief, on=_GROEP, how="left")
        .join(laatste_peilgrens, on="BRIN", how="left")
        .with_columns(
            (
                pl.col("_hoofdinschrijving")
                & niveau_ok
                & waarneembaar
                & pl.col("_actief_volgend_jaar").is_null()
            ).alias("_dr_noemer")
        )
        .with_columns(
            # Diploma zonder formeel zesjaarsvenster: benadering, zie #119.
            (pl.col("_dr_noemer") & pl.col("DIP_DatumResultaat").is_not_null()).alias(
                "_dr_teller"
            )
        )
    )


def bouw_inschrijving_schooljaar(
    inschrijvingen: pl.DataFrame, leveringen: pl.DataFrame
) -> pl.DataFrame:
    """Bouw ``fact_inschrijving_schooljaar`` uit canonieke ISP-perioden.

    Args:
        inschrijvingen: Analysetabel op periode-grain (na canonicalisatie), met
                        ``DatumBegin``, ``Niveau``, ``Opleidingcode``,
                        ``IndicatieBekostigbaar`` en ``DIP_DatumResultaat``.
        leveringen:     ``meta_leveringen`` (peildatum per levering).

    Returns:
        Eén rij per ``GRAIN``; leeg (met vast schema) zonder peildatum-dekking.
    """
    begin = _periode_begin_kolom(inschrijvingen)
    if begin is None:
        return pl.DataFrame(schema=_KOLOMMEN)
    # TBGI-only: de inschrijving zelf is de periode (begin = DatumInschrijving).
    perioden = _voeg_periode_einde_toe(
        inschrijvingen.with_columns(pl.col(begin).alias("DatumBegin"))
    )
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
    df = _voeg_dr_toe(
        _voeg_jr_toe(_voeg_hoofdinschrijving_toe(_per_schooljaar(perioden)))
    )
    return df.select(_KOLOMMEN).sort(GRAIN)
