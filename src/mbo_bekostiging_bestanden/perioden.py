"""Inschrijvingsperioden: sleutel, begin, einde, studiejaar en koppeling.

Een ISP-periode (of een TBGI-inschrijving zonder ISP) krijgt een stabiele
``_inschrijving_periode_id``; elk detailfeit wijst er via
:func:`koppel_periode_id` zonder fan-out naartoe.
"""

import hashlib

import polars as pl

from mbo_bekostiging_bestanden.contracts import (
    JOIN_INSCHRIJVING,
    KOPPELSTATUS,
    KOPPELSTATUS_BINNEN,
    KOPPELSTATUS_GEEN_INSCHRIJVING,
    PERIODE_ID,
    STUDIEJAAR_START_MAAND,
)

# Begindatum van een inschrijvingsperiode, in voorkeursvolgorde: de ISP-periode
# (RO/GRONDSLAG), anders de TBGI-inschrijving als geheel (TBGI-only: geen ISP).
_PERIODE_BEGIN_KOLOMMEN = ("DatumBegin", "DatumInschrijving")
# Eén inschrijving binnen een levering: haar ISP-perioden sluiten op elkaar aan.
# Een periode loopt t/m DatumEind (GRONDSLAG), anders tot de volgende (#144).
_PERIODE_INSCHRIJVING = ("levering", "BRIN", "_persoon_id", "Inschrijvingvolgnummer")
PERIODE_EINDE = "_periode_einde"


def _hash_periode_key(
    levering: str, persoon_id: str, inschrijving_nr: str, datum_begin: str
) -> str:
    """Stabiele sleutel voor een ISP-periode: SHA-256 (hex) van de brongegevens.

    Reproduceerbaar en onafhankelijk van rijvolgorde; de volledige 256-bit
    digest maakt collisions praktisch uitgesloten, zonder aparte controle.

    Let op: een ongekeyde content-hash (geen HMAC, geen geheim). Het dient als
    stabiele FK-sleutel, niet als pseudonimisering van persoonsgegevens —
    daarvoor is ``_persoon_id`` (``identiteit.py``) bedoeld.
    """
    key_str = f"{levering}|{persoon_id}|{inschrijving_nr}|{datum_begin}"
    return hashlib.sha256(key_str.encode()).hexdigest()


def periode_begin_kolom(df: pl.DataFrame) -> str | None:
    """Kolom met de begindatum van een inschrijvingsperiode, of ``None``."""
    return next((c for c in _PERIODE_BEGIN_KOLOMMEN if c in df.columns), None)


def _periode_begin(df: pl.DataFrame) -> pl.Expr:
    """Begindatum van de periode; leeg als geen begindatumkolom bestaat.

    Een lege begin geldt als onbekend (zoals een lege ``DatumBegin``): de
    sleutel blijft uniek zolang een inschrijving één periode heeft.
    """
    begin = periode_begin_kolom(df)
    return pl.col(begin) if begin else pl.lit(None, dtype=pl.Date)


def _als_datum(df: pl.DataFrame, kolom: str) -> pl.Expr:
    """``kolom`` als ``Date``; leeg als de kolom ontbreekt.

    Tekst wordt expliciet geparsed: de String→Date-cast is deprecated in Polars.
    """
    if kolom not in df.columns:
        return pl.lit(None, dtype=pl.Date)
    if df.schema[kolom] == pl.String:
        return pl.col(kolom).str.to_date()
    return pl.col(kolom).cast(pl.Date)


def voeg_periode_id_toe(df: pl.DataFrame) -> pl.DataFrame:
    """Voeg de stabiele surrogaatsleutel per inschrijvingsperiode toe.

    (levering, _persoon_id, Inschrijvingvolgnummer) kan meerdere ISP-perioden
    hebben; de begindatum (zie :func:`periode_begin_kolom`) maakt de sleutel
    uniek.  Zonder ISP (TBGI-only) is de inschrijving zelf de periode.
    """
    sleutel = [*JOIN_INSCHRIJVING, "_periode_begin"]
    return df.with_columns(
        pl.struct(*JOIN_INSCHRIJVING, _periode_begin(df).alias("_periode_begin"))
        .map_elements(
            lambda rij: _hash_periode_key(*(rij[k] for k in sleutel)),
            return_dtype=pl.Utf8,
        )
        .alias(PERIODE_ID)
    )


def voeg_periode_einde_toe(df: pl.DataFrame) -> pl.DataFrame:
    """Voeg ``_periode_einde`` (inclusief) toe aan ISP-rijen.

    ``_periode_einde`` is het minimum van:
    - DatumUitschrijvingWerkelijk (een uitgeschreven inschrijving kan na die
      datum nooit actief zijn, ongeacht DatumEind of volgende periode, #163)
    - DatumEind (als de bron die levert, bijv. GRONDSLAG)
    - dag vóór volgende DatumBegin (RO periode-sequencing)

    Zonder ``DatumBegin`` of zonder inschrijvingssleutel blijft ``df``
    ongewijzigd: de inschrijving is dan zelf de periode (TBGI-only).
    """
    sleutel = [c for c in _PERIODE_INSCHRIJVING if c in df.columns]
    if "DatumBegin" not in df.columns or not {
        "_persoon_id",
        "Inschrijvingvolgnummer",
    }.issubset(sleutel):
        return df
    volgende = (
        df.select(*sleutel, "DatumBegin")
        .drop_nulls("DatumBegin")
        .unique()
        .sort([*sleutel, "DatumBegin"], nulls_last=True)
        .with_columns(
            pl.col("DatumBegin").shift(-1).over(sleutel).alias("_volgende_begin")
        )
    )
    df = df.join(
        volgende,
        on=[*sleutel, "DatumBegin"],
        how="left",
        nulls_equal=True,
        maintain_order="left",
    )
    tot_volgende = pl.col("_volgende_begin") - pl.duration(days=1)

    candidates = [tot_volgende]
    if "DatumEind" in df.columns:
        candidates.append("DatumEind")
    if "DatumUitschrijvingWerkelijk" in df.columns:
        candidates.append("DatumUitschrijvingWerkelijk")

    einde = pl.min_horizontal(*candidates) if len(candidates) > 1 else tot_volgende

    return df.with_columns(einde.alias(PERIODE_EINDE)).drop("_volgende_begin")


def leid_studiejaar_af(df: pl.DataFrame) -> pl.DataFrame:
    """Vul Studiejaar aan uit de periodebegin; voeg ook de herkomstvarianten toe.

    Studiejaar loopt van 1 augustus t/m 31 juli:
    maand >= 8 → jaar; maand < 8 → jaar - 1.

    - Studiejaar_periode: afgeleid uit de periodebegin (zie
      :func:`periode_begin_kolom`).
    - Studiejaar_levering: van het bronbestand (GRONDSLAG) of null.

    Behoudt ``Studiejaar`` voor afnemers van die kolom, aangevuld uit de datum
    waar de bron het niet levert.
    """
    datum_col = periode_begin_kolom(df)

    def _studiejaar_expr(col_naam: str) -> pl.Expr:
        return (
            pl.when(pl.col(col_naam).dt.month() >= STUDIEJAAR_START_MAAND)
            .then(pl.col(col_naam).dt.year())
            .otherwise(pl.col(col_naam).dt.year() - 1)
            .cast(pl.Int64)
        )

    if datum_col is not None:
        df = df.with_columns(_studiejaar_expr(datum_col).alias("Studiejaar_periode"))
    else:
        df = df.with_columns(pl.lit(None, dtype=pl.Int64).alias("Studiejaar_periode"))

    if "Studiejaar" in df.columns:
        df = df.with_columns(
            pl.col("Studiejaar").cast(pl.Int64).alias("Studiejaar_levering")
        )
    else:
        df = df.with_columns(pl.lit(None, dtype=pl.Int64).alias("Studiejaar_levering"))

    if "Studiejaar" not in df.columns:
        if datum_col is not None:
            df = df.with_columns(_studiejaar_expr(datum_col).alias("Studiejaar"))
        else:
            df = df.with_columns(pl.lit(None, dtype=pl.Int64).alias("Studiejaar"))
    elif df["Studiejaar"].null_count() > 0 and datum_col is not None:
        df = df.with_columns(
            pl.coalesce([pl.col("Studiejaar"), _studiejaar_expr(datum_col)]).alias(
                "Studiejaar"
            )
        )

    return df


def _koppel_via(
    detail: pl.DataFrame,
    inschrijvingen: pl.DataFrame,
    datum_kolom: str,
    sleutel: list[str],
) -> pl.DataFrame:
    """Koppel via één sleutel; zie :func:`koppel_periode_id`.

    Zonder ``levering`` in ``sleutel`` kan dezelfde periode in meerdere
    leveringen voorkomen; dan wint de levering die alfabetisch als laatste komt
    (leveringsnamen eindigen op hun datums), zodat er nooit fan-out ontstaat.
    """
    if not set(sleutel) <= set(detail.columns) & set(inschrijvingen.columns):
        return detail.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias(PERIODE_ID),
            pl.lit(KOPPELSTATUS_GEEN_INSCHRIJVING).alias(KOPPELSTATUS),
        )

    perioden = (
        inschrijvingen.select(
            *sleutel,
            pl.col("levering").alias("_levering"),
            _periode_begin(inschrijvingen).alias("_periode_begin"),
            PERIODE_ID,
        )
        .sort("_levering")
        .unique(subset=[*sleutel, "_periode_begin"], keep="last")
        .drop("_levering")
    )
    eerste = (
        perioden.sort("_periode_begin", nulls_last=True)
        .unique(subset=sleutel, keep="first")
        .select([*sleutel, pl.col(PERIODE_ID).alias("_eerste_periode")])
    )

    rij = "_rij"
    datum = _als_datum(detail, datum_kolom)
    links = detail.with_row_index(rij).with_columns(datum.alias("_referentie"))
    gedateerd = links.drop_nulls("_referentie").sort("_referentie")
    binnen = gedateerd.join_asof(
        perioden.drop_nulls("_periode_begin").sort("_periode_begin"),
        left_on="_referentie",
        right_on="_periode_begin",
        by=sleutel,
        strategy="backward",
        check_sortedness=False,  # beide kanten zijn hierboven gesorteerd
    ).select(rij, PERIODE_ID)

    status = (
        pl.when(pl.col("_eerste_periode").is_null())
        .then(pl.lit(KOPPELSTATUS_GEEN_INSCHRIJVING))
        .when(pl.col(PERIODE_ID).is_not_null())
        .then(pl.lit(KOPPELSTATUS_BINNEN))
        .when(pl.lit(datum_kolom not in detail.columns))
        .then(pl.lit("geen_datumkolom"))
        .when(pl.col("_referentie").is_null())
        .then(pl.lit("datum_leeg"))
        .otherwise(pl.lit("voor_eerste_periode"))
    )
    return (
        links.join(binnen, on=rij, how="left")
        .join(eerste, on=sleutel, how="left")
        .with_columns(
            status.alias(KOPPELSTATUS),
            pl.coalesce(PERIODE_ID, "_eerste_periode").alias(PERIODE_ID),
        )
        .sort(rij)
        .drop(rij, "_referentie", "_eerste_periode")
    )


def koppel_periode_id(
    detail: pl.DataFrame,
    inschrijvingen: pl.DataFrame,
    datum_kolom: str,
    sleutels: tuple[list[str], ...] = (JOIN_INSCHRIJVING,),
) -> pl.DataFrame:
    """Voeg ``_inschrijving_periode_id`` en de ``KOPPELSTATUS`` toe per detailrij.

    Een detailrij hoort bij de periode van dezelfde inschrijving met de laatste
    begindatum (zie :func:`periode_begin_kolom`) op of vóór ``datum_kolom``.
    Valt de datum vóór de eerste periode, of ontbreekt hij, dan wordt de eerste
    periode gekozen; de status zegt welk geval (#121).

    ``sleutels`` staan in voorkeursvolgorde: de eerste sleutel die voor een rij
    een periode oplevert wint, met de koppelstatus van die sleutel; de volgende
    zijn de terugval (#112). Lukt geen enkele, dan een lege sleutel met status
    ``geen_inschrijving``. Rijvolgorde en rijtal blijven behouden.
    """
    if detail.is_empty() or PERIODE_ID not in inschrijvingen.columns:
        return detail
    perioden: list[pl.Series] = []
    statussen: list[pl.Series] = []
    for sleutel in sleutels:
        gekoppeld = _koppel_via(detail, inschrijvingen, datum_kolom, sleutel)
        perioden.append(gekoppeld[PERIODE_ID])
        statussen.append(
            gekoppeld.select(
                pl.when(pl.col(PERIODE_ID).is_not_null()).then(KOPPELSTATUS)
            ).to_series()
        )
    return detail.with_columns(
        pl.coalesce(perioden).alias(PERIODE_ID),
        pl.coalesce(*statussen, pl.lit(KOPPELSTATUS_GEEN_INSCHRIJVING)).alias(
            KOPPELSTATUS
        ),
    )
