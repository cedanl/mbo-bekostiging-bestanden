"""Jaargebonden vlaggen op periode-grain in ``fact_inschrijving`` (legacy).

Verouderd sinds ``fact_inschrijving_schooljaar`` (#164): ``schooljaar.py`` is
de bron van waarheid per schooljaar; deze kolommen staan in
``contracts.VEROUDERDE_KOLOMMEN`` en verdwijnen in v4.0.0 (#201).

  Bekostiging   _actief_1_oktober, _bekostigd_eerste_1okt,
                _gediplomeerd_in_jaar, _ingeschreven_jaar_later,
                _deelnemer_niet_bekostigd_eerste_1okt
  Selectie      _hoogste_niveau, _laagste_CREBO, _hoofdinschrijving
  Tellingen     _telling (= actief_1_okt ∧ hoofdinschrijving)
  Rendement     _jr_noemer, _jr_teller, _dr_noemer, _dr_teller
  Entree        _entree_uitstroom, _entree_doorstroom (MBO-1 specifiek)
"""

import polars as pl

from mbo_bekostiging_bestanden.contracts import (
    STUDIEJAAR_EIND_DAG,
    STUDIEJAAR_EIND_MAAND,
    STUDIEJAAR_START_DAG,
    STUDIEJAAR_START_MAAND,
    TELDATUM_DAG,
    TELDATUM_MAAND,
)
from mbo_bekostiging_bestanden.opleidingsniveau import niveau_numeriek
from mbo_bekostiging_bestanden.perioden import (
    PERIODE_EINDE,
    periode_begin_kolom,
    voeg_periode_einde_toe,
)

_SELECTIE_VLAGGEN = ("_hoogste_niveau", "_laagste_CREBO", "_hoofdinschrijving")


def voeg_periodevlaggen_toe(df: pl.DataFrame) -> pl.DataFrame:
    """Alle vlaggen hierboven, in afhankelijkheidsvolgorde."""
    df = _voeg_bekostigingsvlaggen_toe(df)
    df = _voeg_sr_vlaggen_toe(df)
    df = _voeg_telling_en_jr_vlaggen_toe(df)
    df = _voeg_dr_vlaggen_toe(df)
    return _voeg_entree_vlaggen_toe(df)


def _bepaal_actief_per_schooljaar(df: pl.DataFrame) -> pl.DataFrame:
    """Bepaal per (levering, BRIN, _persoon_id, schooljaar) welke ISP-periode
    actief is op 1-okt.

    Voor elke schooljaar waar een persoon periodes heeft, zoek de periode die
    1-oktober van dat schooljaar dekt. Markeer de periodes die minstens één
    peildatum dekken als `_actief_1_oktober = True`.

    Retourneert de originele df (geen duplicatie) met `_actief_1_oktober`,
    `_schooljaren_actief` (lijst van schooljaren die deze periode dekt) en
    `_ingeschreven_jaar_later` per rij.
    """
    if "Studiejaar" not in df.columns or "DatumBegin" not in df.columns:
        return df.with_columns(
            pl.lit(None, dtype=pl.Boolean).alias("_actief_1_oktober"),
            pl.lit(None, dtype=pl.Boolean).alias("_ingeschreven_jaar_later"),
            pl.lit(None, dtype=pl.List(pl.Int64)).alias("_schooljaren_actief"),
        )

    df = voeg_periode_einde_toe(df)
    sj_col = (
        "Studiejaar_periode" if "Studiejaar_periode" in df.columns else "Studiejaar"
    )
    persoon = ["levering", "BRIN", "_persoon_id"]
    periode = [*persoon, "Inschrijvingvolgnummer", "DatumBegin"]
    schooljaren = (
        df.select(*persoon, pl.col(sj_col).alias("_schooljaar_peildatum"))
        .drop_nulls("_schooljaar_peildatum")
        .unique()
    )

    if schooljaren.is_empty():
        return df.with_columns(
            pl.lit(False, dtype=pl.Boolean).alias("_actief_1_oktober"),
            pl.lit(False, dtype=pl.Boolean).alias("_ingeschreven_jaar_later"),
            pl.lit(None, dtype=pl.List(pl.Int64)).alias("_schooljaren_actief"),
        ).drop(PERIODE_EINDE, strict=False)

    # Elke periode tegen elk schooljaar van dezelfde persoon × BRIN × levering:
    # actief als de periode 1 oktober van dat jaar dekt. Vectoraal i.p.v. een
    # filter per schooljaar (#201: die lus kostte ~75% van build_star).
    peildatum = pl.date(pl.col("_schooljaar_peildatum"), TELDATUM_MAAND, TELDATUM_DAG)
    schooljaren_per_periode = (
        df.select(*periode, PERIODE_EINDE)
        .drop_nulls("DatumBegin")
        .join(schooljaren, on=persoon, how="inner")
        .filter(
            (pl.col("DatumBegin") <= peildatum)
            & (pl.col(PERIODE_EINDE).is_null() | (pl.col(PERIODE_EINDE) >= peildatum))
        )
        .group_by(periode)
        .agg(pl.col("_schooljaar_peildatum").sort().alias("_schooljaren_actief"))
    )

    if schooljaren_per_periode.is_empty():
        return df.with_columns(
            pl.lit(False, dtype=pl.Boolean).alias("_actief_1_oktober"),
            pl.lit(False, dtype=pl.Boolean).alias("_ingeschreven_jaar_later"),
            pl.lit(None, dtype=pl.List(pl.Int64)).alias("_schooljaren_actief"),
        ).drop(PERIODE_EINDE, strict=False)

    # Join terug naar originele df (één-op-één, geen duplicatie)
    df = df.join(schooljaren_per_periode, on=periode, how="left")

    # _actief_1_oktober = True als periode minstens één schooljaar dekt
    df = df.with_columns(
        _actief_1_oktober=pl.col("_schooljaren_actief").list.len().fill_null(0) > 0
    )

    # _ingeschreven_jaar_later: inschrijving begint na 1-okt van
    # EERSTE schooljaar dat deze periode dekt
    if "DatumInschrijving" in df.columns:
        df = df.with_columns(
            _ingeschreven_jaar_later=pl.when(
                pl.col("_schooljaren_actief").list.len() > 0
            )
            .then(
                pl.col("DatumInschrijving")
                > pl.date(
                    pl.col("_schooljaren_actief").list.first(),
                    TELDATUM_MAAND,
                    TELDATUM_DAG,
                )
            )
            .otherwise(pl.lit(False))
            .fill_null(False)
        )
    else:
        df = df.with_columns(
            pl.lit(False, dtype=pl.Boolean).alias("_ingeschreven_jaar_later")
        )

    return df.drop(PERIODE_EINDE, strict=False)


def _voeg_bekostigingsvlaggen_toe(df: pl.DataFrame) -> pl.DataFrame:
    """Voeg bekostigingsvlaggen toe: actief 1-okt, bekostigd, gediplomeerd,
    ingeschreven later.

    De `_actief_1_oktober` wordt bepaald per schooljaar via as-of join
    (zie :func:`_bepaal_actief_per_schooljaar`).
    """
    if "Studiejaar" not in df.columns:
        return df.with_columns(
            pl.lit(None, dtype=pl.Boolean).alias("_actief_1_oktober"),
            pl.lit(None, dtype=pl.Boolean).alias("_bekostigd_eerste_1okt"),
            pl.lit(False, dtype=pl.Boolean).alias("_gediplomeerd_in_jaar"),
            pl.lit(None, dtype=pl.Boolean).alias("_ingeschreven_jaar_later"),
            pl.lit(None, dtype=pl.Boolean).alias(
                "_deelnemer_niet_bekostigd_eerste_1okt"
            ),
            pl.lit(None, dtype=pl.Int64).alias("Opbrengstjaar_uitsplitsing"),
            pl.lit(None, dtype=pl.Boolean).alias("_driejaars_teljaar"),
            pl.lit(None, dtype=pl.Utf8).alias("Opbrengstjaar_3jaars_voortschrijdend"),
            pl.lit(None, dtype=pl.Int64).alias("_num_opbrengstjaar_3jr"),
        )

    df = _bepaal_actief_per_schooljaar(df)

    # _bekostigd_eerste_1okt: actief én bekostigbaar
    bekostigd = (
        pl.col("_actief_1_oktober") & (pl.col("IndicatieBekostigbaar") == "J")
        if "IndicatieBekostigbaar" in df.columns
        else pl.col("_actief_1_oktober") & pl.lit(False)
    ).alias("_bekostigd_eerste_1okt")

    # _gediplomeerd_in_jaar: diploma in het schooljaar van de periode
    sj_col = (
        "Studiejaar_periode" if "Studiejaar_periode" in df.columns else "Studiejaar"
    )
    if "DIP_DatumResultaat" in df.columns and sj_col in df.columns:
        jaar_begin = pl.date(
            pl.col(sj_col) - 1, STUDIEJAAR_START_MAAND, STUDIEJAAR_START_DAG
        )
        jaar_eind = pl.date(pl.col(sj_col), STUDIEJAAR_EIND_MAAND, STUDIEJAAR_EIND_DAG)
        dip_datum = pl.col("DIP_DatumResultaat")
        gediplomeerd = (
            (
                dip_datum.is_not_null()
                & (dip_datum >= jaar_begin)
                & (dip_datum <= jaar_eind)
            )
            .fill_null(False)
            .alias("_gediplomeerd_in_jaar")
        )
    else:
        gediplomeerd = pl.lit(False, dtype=pl.Boolean).alias("_gediplomeerd_in_jaar")

    df = df.with_columns(bekostigd, gediplomeerd)

    df = df.with_columns(
        (pl.col("_actief_1_oktober") & ~pl.col("_bekostigd_eerste_1okt")).alias(
            "_deelnemer_niet_bekostigd_eerste_1okt"
        )
    )

    # Opbrengstjaar-velden volgen het leveringsstudiejaar en zijn daardoor
    # run-afhankelijk; ze verdwijnen met de legacy-vlaggen (#201).
    studiejaar_serie = df["Studiejaar"].cast(pl.Int32).drop_nulls()
    if studiejaar_serie.is_empty():
        return df.with_columns(
            pl.lit(None, dtype=pl.Int64).alias("Opbrengstjaar_uitsplitsing"),
            pl.lit(None, dtype=pl.Boolean).alias("_driejaars_teljaar"),
            pl.lit(None, dtype=pl.Utf8).alias("Opbrengstjaar_3jaars_voortschrijdend"),
            pl.lit(None, dtype=pl.Int64).alias("_num_opbrengstjaar_3jr"),
        )

    max_jaar = studiejaar_serie.sort(descending=True).item(0)
    opbrengstjaar_label = f"{max_jaar - 2}-{max_jaar}"
    return df.with_columns(
        pl.col("Studiejaar").cast(pl.Int64).alias("Opbrengstjaar_uitsplitsing"),
        (pl.col("Studiejaar") >= (max_jaar - 2)).alias("_driejaars_teljaar"),
        pl.lit(opbrengstjaar_label, dtype=pl.Utf8).alias(
            "Opbrengstjaar_3jaars_voortschrijdend"
        ),
        pl.col("Studiejaar")
        .rank("dense", descending=False)
        .cast(pl.Int64)
        .alias("_num_opbrengstjaar_3jr"),
    )


def _voeg_sr_vlaggen_toe(df: pl.DataFrame) -> pl.DataFrame:
    """Selectie/rendement-vlaggen: hoogste niveau, laagste CREBO, hoofdinschrijving.

    Alle drie de vlaggen gelden binnen dezelfde groep: persoon × schooljaar (peildatum),
    per levering en per instelling (``BRIN``) als die kolommen bestaan.  DUO
    telt één hoofdinschrijving per student per instelling op de peildatum;
    per levering zodat gestapelde leveringen elkaar niet beïnvloeden.

    Alleen perioden die op 1 oktober actief zijn doen mee (#144): DUO kiest de
    hoofdinschrijving op de peildatum.  Een onbekende actief-status sluit niet
    uit.  ``_hoofdinschrijving`` is precies één kandidaat (hoogste niveau én
    laagste CREBO) per groep met een actieve periode; bij gelijke kandidaten
    wint de meest recente periode (zie ``perioden.periode_begin_kolom``).
    """
    vereist = {"_persoon_id", "Niveau", "Opleidingcode", "_actief_1_oktober"}
    if not vereist.issubset(df.columns):
        return df.with_columns(
            pl.lit(None, dtype=pl.Boolean).alias(c) for c in _SELECTIE_VLAGGEN
        )

    if "_schooljaren_actief" not in df.columns or "_actief_1_oktober" not in df.columns:
        return df.with_columns(
            pl.lit(None, dtype=pl.Boolean).alias(c) for c in _SELECTIE_VLAGGEN
        )

    actieve = df.filter(pl.col("_actief_1_oktober").fill_null(False))
    if actieve.is_empty():
        return df.with_columns(
            pl.lit(False, dtype=pl.Boolean).alias(c) for c in _SELECTIE_VLAGGEN
        )

    actieve_exploded = actieve.explode(
        "_schooljaren_actief", empty_as_null=True
    ).rename({"_schooljaren_actief": "_schooljaar_peildatum"})

    groep_cols = [
        c
        for c in ["levering", "BRIN", "_persoon_id", "_schooljaar_peildatum"]
        if c in actieve_exploded.columns
    ]
    niveau = niveau_numeriek(pl.col("Niveau"))

    # Hoogste niveau onder actieve periodes per groep
    hoogste = niveau == niveau.max().over(groep_cols)
    laagste_crebo = hoogste & (
        pl.col("Opleidingcode")
        == pl.col("Opleidingcode").filter(hoogste).min().over(groep_cols)
    )
    actieve_exploded = actieve_exploded.with_columns(
        hoogste.alias("_hoogste_niveau"), laagste_crebo.alias("_laagste_CREBO")
    )

    kandidaat = pl.col("_laagste_CREBO").fill_null(False)
    begin = periode_begin_kolom(actieve_exploded)
    volgorde = [kandidaat, *([pl.col(begin)] if begin else [])]
    rij = "_rij"
    gekozen = (
        pl.col(rij)
        .sort_by(volgorde, descending=True, nulls_last=True)
        .first()
        .over(groep_cols)
    )
    actieve_exploded = (
        actieve_exploded.with_row_index(rij)
        .with_columns(
            (kandidaat & (pl.col(rij) == gekozen)).alias("_hoofdinschrijving")
        )
        .drop(rij)
    )

    # Een periode is hoofdinschrijving als ze dat voor één van haar schooljaren is.
    hoofd_per_periode = (
        actieve_exploded.filter(pl.col("_hoofdinschrijving"))
        .select(
            ["levering", "BRIN", "_persoon_id", "Inschrijvingvolgnummer", "DatumBegin"]
        )
        .unique()
        .with_columns(pl.lit(True).alias("_is_hoofd"))
    )

    df = (
        df.join(
            hoofd_per_periode,
            on=[
                "levering",
                "BRIN",
                "_persoon_id",
                "Inschrijvingvolgnummer",
                "DatumBegin",
            ],
            how="left",
        )
        .with_columns(pl.col("_is_hoofd").fill_null(False).alias("_hoofdinschrijving"))
        .drop("_is_hoofd")
    )

    # Niet per schooljaar maar over alle perioden van persoon × BRIN × levering,
    # ook de niet-actieve.
    niveau_all = niveau_numeriek(pl.col("Niveau"))
    groep_all = [c for c in ["levering", "BRIN", "_persoon_id"] if c in df.columns]
    if groep_all:
        hoogste_all = niveau_all == niveau_all.max().over(groep_all)
        laagste_crebo_all = hoogste_all & (
            pl.col("Opleidingcode")
            == pl.col("Opleidingcode").filter(hoogste_all).min().over(groep_all)
        )
        df = df.with_columns(
            hoogste_all.alias("_hoogste_niveau"),
            laagste_crebo_all.alias("_laagste_CREBO"),
        )

    return df


def _voeg_telling_en_jr_vlaggen_toe(df: pl.DataFrame) -> pl.DataFrame:
    """Voeg ``_telling`` en JR-bouwstenen toe.

    ``_telling``: deduplicatievlag voor tellingen — actief op 1 oktober én
    hoofdinschrijving.  ``_jr_noemer``/``_jr_teller``: bouwstenen voor het
    Jaarresultaat (sum/sum door downstream).
    """
    heeft_actief = "_actief_1_oktober" in df.columns
    heeft_hoofd = "_hoofdinschrijving" in df.columns

    if heeft_actief and heeft_hoofd:
        df = df.with_columns(
            (
                pl.col("_actief_1_oktober").fill_null(False)
                & pl.col("_hoofdinschrijving").fill_null(False)
            ).alias("_telling")
        )
    else:
        df = df.with_columns(pl.lit(False).alias("_telling"))

    heeft_gediplomeerd = "_gediplomeerd_in_jaar" in df.columns

    df = df.with_columns(pl.col("_telling").alias("_jr_noemer"))

    if heeft_gediplomeerd:
        df = df.with_columns(
            (
                pl.col("_jr_noemer") & pl.col("_gediplomeerd_in_jaar").fill_null(False)
            ).alias("_jr_teller")
        )
    else:
        df = df.with_columns(pl.lit(False).alias("_jr_teller"))

    return df


def _voeg_dr_vlaggen_toe(df: pl.DataFrame) -> pl.DataFrame:
    """DR-bouwstenen: uitstromers en gediplomeerde uitstromers (§3.1).

    Uitstromer = actief op 1-10-t én geen actieve inschrijving bij hetzelfde
    BRIN in studiejaar t+1.  Bij gestapelde leveringen (meerdere studiejaren)
    wordt over alle leveringen heen gekeken.

    ``_dr_noemer``: hoofdinschrijving, actief 1-10, niveau ≥ 2, uitstromer.
    ``_dr_teller``: ``_dr_noemer`` met diploma (DIP_DatumResultaat aanwezig).

    Beperking: de 6-jaars terugblik voor diploma's is benaderd via
    aanwezigheid van ``DIP_DatumResultaat``; ``DIP_Niveau`` wordt niet
    expliciet gecontroleerd omdat dit een join op de CREBO-koppeltabel vereist.
    """
    benodigde = {
        "_persoon_id",
        "BRIN",
        "Studiejaar",
        "_actief_1_oktober",
        "_hoofdinschrijving",
    }
    if not benodigde.issubset(df.columns):
        return df.with_columns(
            pl.lit(None, dtype=pl.Boolean).alias("_dr_noemer"),
            pl.lit(None, dtype=pl.Boolean).alias("_dr_teller"),
        )

    actief = (
        df.filter(pl.col("_actief_1_oktober").fill_null(False))
        .select(["_persoon_id", "BRIN", "Studiejaar"])
        .unique()
    )

    # Lookup: (persoon_id, BRIN, t) → actief in t+1?
    # Shift Studiejaar -1 zodat de join werkt op het huidige studiejaar t.
    volgend_lookup = actief.with_columns(
        (pl.col("Studiejaar") - 1).alias("Studiejaar")
    ).with_columns(pl.lit(True).alias("_actief_volgend_jaar"))
    df = df.join(volgend_lookup, on=["_persoon_id", "BRIN", "Studiejaar"], how="left")
    df = df.with_columns(pl.col("_actief_volgend_jaar").fill_null(False))

    niveau_ge_2 = (
        (niveau_numeriek(pl.col("Niveau")) >= 2).fill_null(False)
        if "Niveau" in df.columns
        else pl.lit(True)
    )
    df = df.with_columns(
        (
            pl.col("_actief_1_oktober").fill_null(False)
            & pl.col("_hoofdinschrijving").fill_null(False)
            & ~pl.col("_actief_volgend_jaar")
            & niveau_ge_2
        ).alias("_dr_noemer")
    )

    if "DIP_DatumResultaat" in df.columns:
        df = df.with_columns(
            (pl.col("_dr_noemer") & pl.col("DIP_DatumResultaat").is_not_null()).alias(
                "_dr_teller"
            )
        )
    else:
        df = df.with_columns(pl.lit(False, dtype=pl.Boolean).alias("_dr_teller"))

    return df.drop("_actief_volgend_jaar")


def _voeg_entree_vlaggen_toe(df: pl.DataFrame) -> pl.DataFrame:
    """Voeg ``_entree_uitstroom`` en ``_entree_doorstroom`` toe.

    Alleen relevant voor MBO-1 (Entree) inschrijvingen.
    Doorstroom = dezelfde persoon heeft een ISP op MBO-2+ niveau.
    """
    vereist = {"Niveau", "_persoon_id"}
    if not vereist.issubset(df.columns):
        return df.with_columns(
            pl.lit(None, dtype=pl.Boolean).alias("_entree_uitstroom"),
            pl.lit(None, dtype=pl.Boolean).alias("_entree_doorstroom"),
        )

    is_entree = niveau_numeriek(pl.col("Niveau")) == 1

    heeft_uitschrijving = (
        "DatumUitschrijvingWerkelijk" in df.columns
        and "DatumUitschrijvingGepland" in df.columns
    )
    if heeft_uitschrijving:
        df = df.with_columns(
            (is_entree & pl.col("DatumUitschrijvingWerkelijk").is_not_null())
            .fill_null(False)
            .alias("_entree_uitstroom")
        )
    else:
        df = df.with_columns(pl.lit(False).alias("_entree_uitstroom"))

    join_cols = ["_persoon_id"]
    if "BRIN" in df.columns:
        join_cols.append("BRIN")
    hoger_niveau = (
        df.filter(niveau_numeriek(pl.col("Niveau")) >= 2)
        .select(join_cols)
        .unique()
        .with_columns(pl.lit(True).alias("_heeft_hoger"))
    )
    df = df.join(hoger_niveau, on=join_cols, how="left")
    df = df.with_columns(
        (is_entree & pl.col("_heeft_hoger").fill_null(False))
        .fill_null(False)
        .alias("_entree_doorstroom")
    ).drop("_heeft_hoger")

    return df
