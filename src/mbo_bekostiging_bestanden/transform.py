"""Interne analysetabellen vanuit gestapelde genormaliseerde records.

Zeven output-tabellen (nul informatieverlies):
  inschrijvingen      ISP-grain, alles flat + dynamische GEO-pivot +
                      BPV/KZD/AMO geaggregeerd
  detail_bpv          BPV volledig uitgesplitst, joinbaar op
                      (levering, _persoon_id, Inschrijvingvolgnummer)
  detail_kzd_amo      KZD en AMO volledig, kolom _bron geeft herkomst aan
  detail_bekostiging  BII (GRONDSLAG) + TBGI-Teldatum per
                      inschrijving × teldatum
  detail_bekostiging_diploma  TBGI-Diploma per inschrijving × diploma
  detail_geo          GEO in long format, grain: inschrijving × onderdeel
  meta_leveringen     VLP + SLR per bronbestand

Berekende vlaggen op inschrijvingen:
  Bekostiging   _actief_1_oktober, _bekostigd_eerste_1okt,
                _gediplomeerd_in_jaar, _ingeschreven_jaar_later,
                _deelnemer_niet_bekostigd_eerste_1okt
  Selectie      _hoogste_niveau, _laagste_CREBO, _hoofdinschrijving
  Tellingen     _telling (= actief_1_okt ∧ hoofdinschrijving)
  Rendement     _jr_noemer, _jr_teller (bouwstenen voor Jaarresultaat)
  Entree        _entree_uitstroom, _entree_doorstroom (MBO-1 specifiek)
  Afgeleid      Niveau_gecombineerd, _tellingen_aanwezig
"""

import functools
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.enrich import enrich_inschrijvingen

_METADATA = Path(__file__).parent / "metadata"


@functools.cache
def _laad_crebo_niveau() -> pl.DataFrame:
    """Laad CREBO-tabel en geef mapping Opleidingcode → Niveau (MBO-n)."""
    return (
        pl.read_csv(_METADATA / "crebo.csv", infer_schema_length=0)
        .select(["code", "niveau"])
        .filter(pl.col("niveau").is_not_null())
        .with_columns(
            (_CREBO_PREFIX + pl.col("niveau")).alias("_crebo_niveau"),
        )
        .select(
            pl.col("code").alias("Opleidingcode"),
            pl.col("_crebo_niveau"),
        )
        .unique(subset=["Opleidingcode"], keep="first", maintain_order=True)
    )


# Kolommen die een persoonsidentificatie bevatten (prioriteitsvolgorde).
_PERSOON_COLS = ["PseudoNummer", "Burgerservicenummer", "Onderwijsnummer"]

_JOIN_PERSOON = ["levering", "_persoon_id"]
_JOIN_INSCHRIJVING = ["levering", "_persoon_id", "Inschrijvingvolgnummer"]

# Domeinconstanten (DUO-bekostigingsregels).
_TELDATUM_MONTH = 10  # telling op 1 oktober
_TELDATUM_DAG = 1
_STUDIEJAAR_START_MONTH = 8  # studiejaar loopt 1 aug – 31 jul
_STUDIEJAAR_START_DAG = 1
_STUDIEJAAR_EIND_MONTH = 7
_STUDIEJAAR_EIND_DAG = 31
_CREBO_PREFIX = "MBO-"
_RESULTAAT_BEHAALD = "BEHAALD"


# ---------------------------------------------------------------------------
# Interne helpers
# ---------------------------------------------------------------------------


def _add_persoon_id(df: pl.DataFrame) -> pl.DataFrame:
    """Voeg ``_persoon_id`` toe: coalesce van PseudoNummer / BSN / ONr."""
    beschikbaar = [c for c in _PERSOON_COLS if c in df.columns]
    if not beschikbaar:
        return df.with_columns(pl.lit(None, dtype=pl.Utf8).alias("_persoon_id"))
    return df.with_columns(
        pl.coalesce([pl.col(c) for c in beschikbaar]).alias("_persoon_id")
    )


def _drop(df: pl.DataFrame, *kolommen: str) -> pl.DataFrame:
    """Verwijder kolommen als ze bestaan, negeer ontbrekende."""
    return df.drop([c for c in kolommen if c in df.columns])


def _join_left(
    left: pl.DataFrame,
    right: pl.DataFrame,
    on: list[str],
    suffix: str = "_r",
) -> pl.DataFrame:
    """LEFT JOIN; duplicaten in ``right`` worden op ``on`` gededupliceeerd."""
    right_uniq = right.unique(subset=on, keep="first", maintain_order=True)
    return left.join(right_uniq, on=on, how="left", suffix=suffix)


def _resolve_inschrijving(
    df: pl.DataFrame,
    dip: pl.DataFrame | None,
) -> pl.DataFrame:
    """Vul lege ``Inschrijvingvolgnummer`` op via DIP.

    GEO, KZD en AMO koppelen soms alleen via ``ResultaatvolgnummerDiploma``
    (in GRONDSLAG en sommige RO-formaten); ``Inschrijvingvolgnummer`` staat
    dan leeg.  Door te joinen op DIP.Resultaatvolgnummer halen we het
    ``Inschrijvingvolgnummer`` op.
    """
    # Normaliseer lege string naar null
    df = df.with_columns(
        pl.when(pl.col("Inschrijvingvolgnummer") == "")
        .then(None)
        .otherwise(pl.col("Inschrijvingvolgnummer"))
        .alias("Inschrijvingvolgnummer")
    )

    if dip is None or dip.is_empty():
        return df

    dip_sleutel = (
        _add_persoon_id(dip)
        .select(
            ["levering", "_persoon_id", "Resultaatvolgnummer", "Inschrijvingvolgnummer"]
        )
        .rename(
            {
                "Resultaatvolgnummer": "_dip_vnr",
                "Inschrijvingvolgnummer": "_isg_via_dip",
            }
        )
    )

    if "ResultaatvolgnummerDiploma" not in df.columns:
        return df

    df = df.join(
        dip_sleutel,
        left_on=["levering", "_persoon_id", "ResultaatvolgnummerDiploma"],
        right_on=["levering", "_persoon_id", "_dip_vnr"],
        how="left",
    )
    return df.with_columns(
        pl.coalesce(["Inschrijvingvolgnummer", "_isg_via_dip"]).alias(
            "Inschrijvingvolgnummer"
        )
    ).drop("_isg_via_dip")


def _geo_pivot(
    geo: pl.DataFrame,
    dip: pl.DataFrame | None = None,
) -> pl.DataFrame | None:
    """Pivoteer GEO op CodeGeneriekExamenonderdeel → platte kolommen per code.

    Kolomnaamgeving: ``GEO_{code}_{veld}``
    (bijv. ``GEO_3005_Eindcijfer``, ``GEO_3005_CijferIE``).
    Retourneert ``None`` als de invoer leeg is.
    """
    if geo.is_empty():
        return None

    geo = _add_persoon_id(geo)
    geo = _resolve_inschrijving(geo, dip)

    # Neem per (levering, persoon, inschrijving, code) de laatste/hoogste waarde.
    agg = geo.group_by(
        [
            "levering",
            "_persoon_id",
            "Inschrijvingvolgnummer",
            "CodeGeneriekExamenonderdeel",
        ]
    ).agg(
        pl.col("Eindcijfer").max(),
        pl.col("CijferIE").max(),
        pl.col("CijferCE").max(),
        pl.col("VrijstellingGeneriekExamenonderdeel").first(),
    )

    pivot = agg.pivot(
        on="CodeGeneriekExamenonderdeel",
        index=["levering", "_persoon_id", "Inschrijvingvolgnummer"],
        values=[
            "Eindcijfer",
            "CijferIE",
            "CijferCE",
            "VrijstellingGeneriekExamenonderdeel",
        ],
        aggregate_function="first",
    )

    # Hernoem: "Eindcijfer_3005" → "GEO_3005_Eindcijfer"
    hernoem: dict[str, str] = {}
    for col in pivot.columns:
        for veld in [
            "Eindcijfer",
            "CijferIE",
            "CijferCE",
            "VrijstellingGeneriekExamenonderdeel",
        ]:
            prefix = f"{veld}_"
            if col.startswith(prefix):
                code = col[len(prefix) :]
                is_vrijstelling = veld == "VrijstellingGeneriekExamenonderdeel"
                kort_veld = "Vrijstelling" if is_vrijstelling else veld
                hernoem[col] = f"GEO_{code}_{kort_veld}"
    return pivot.rename(hernoem)


def _vul_niveau_aan(df: pl.DataFrame) -> pl.DataFrame:
    """Vul ontbrekend Niveau aan via de CREBO-tabel (Opleidingcode → MBO-n)."""
    if "Niveau" not in df.columns or "Opleidingcode" not in df.columns:
        return df
    if df["Niveau"].null_count() == 0:
        return df
    crebo = _laad_crebo_niveau()
    df = df.join(crebo, on="Opleidingcode", how="left")
    df = df.with_columns(
        pl.coalesce(["Niveau", "_crebo_niveau"]).alias("Niveau"),
    )
    return df.drop("_crebo_niveau")


def _leid_studiejaar_af(df: pl.DataFrame) -> pl.DataFrame:
    """Vul ontbrekend Studiejaar af uit beschikbare datumvelden.

    Studiejaar loopt van 1 augustus t/m 31 juli:
    maand >= 8 → studiejaar = jaar; maand < 8 → studiejaar = jaar - 1.

    Bronspecifiek:
    - GRONDSLAG levert Studiejaar expliciet via VLP.
    - RO: afgeleid uit DatumBegin (ISP-periode).
    - TBGI: afgeleid uit DatumInschrijving als DatumBegin ontbreekt.

    Bestaande (niet-null) waarden worden niet overschreven.
    """
    datum_col = next(
        (c for c in ("DatumBegin", "DatumInschrijving") if c in df.columns),
        None,
    )

    def _studiejaar_expr(col_naam: str) -> pl.Expr:
        return (
            pl.when(pl.col(col_naam).dt.month() >= _STUDIEJAAR_START_MONTH)
            .then(pl.col(col_naam).dt.year())
            .otherwise(pl.col(col_naam).dt.year() - 1)
            .cast(pl.Int64)
        )

    if "Studiejaar" not in df.columns:
        if datum_col is None:
            return df
        return df.with_columns(_studiejaar_expr(datum_col).alias("Studiejaar"))

    if df["Studiejaar"].null_count() == 0:
        return df
    if datum_col is None:
        return df

    return df.with_columns(
        pl.coalesce([pl.col("Studiejaar"), _studiejaar_expr(datum_col)]).alias(
            "Studiejaar"
        )
    )


def _voeg_bekostigingsvlaggen_toe(df: pl.DataFrame) -> pl.DataFrame:
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

    studiejaar = pl.col("Studiejaar").cast(pl.Int32)
    oct_1 = pl.date(studiejaar, _TELDATUM_MONTH, _TELDATUM_DAG)

    if "DatumInschrijving" in df.columns:
        datum_in = pl.col("DatumInschrijving")
        datum_uit = (
            pl.col("DatumUitschrijvingWerkelijk")
            if "DatumUitschrijvingWerkelijk" in df.columns
            else pl.lit(None, dtype=pl.Date)
        )
        actief = (
            (datum_in <= oct_1) & (datum_uit.is_null() | (datum_uit > oct_1))
        ).alias("_actief_1_oktober")
        ingeschreven_later = (
            (datum_in > oct_1).fill_null(False).alias("_ingeschreven_jaar_later")
        )
    else:
        actief = pl.lit(None, dtype=pl.Boolean).alias("_actief_1_oktober")
        ingeschreven_later = pl.lit(None, dtype=pl.Boolean).alias(
            "_ingeschreven_jaar_later"
        )

    df = df.with_columns(actief, ingeschreven_later)

    bekostigd = (
        pl.col("_actief_1_oktober") & (pl.col("IndicatieBekostigbaar") == "J")
        if "IndicatieBekostigbaar" in df.columns
        else pl.col("_actief_1_oktober") & pl.lit(False)
    ).alias("_bekostigd_eerste_1okt")

    if "DIP_DatumResultaat" in df.columns:
        jaar_begin = pl.date(
            studiejaar - 1, _STUDIEJAAR_START_MONTH, _STUDIEJAAR_START_DAG
        )
        jaar_eind = pl.date(studiejaar, _STUDIEJAAR_EIND_MONTH, _STUDIEJAAR_EIND_DAG)
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


def _niveau_numeriek(col: pl.Expr) -> pl.Expr:
    """Extraheer het numerieke deel uit Niveau (bijv. ``"MBO-4"`` → ``4``)."""
    return col.str.extract(r"(\d+)$").cast(pl.Int32, strict=False)


def _voeg_sr_vlaggen_toe(df: pl.DataFrame) -> pl.DataFrame:
    """Selectie/rendement-vlaggen: hoogste niveau, laagste CREBO, hoofdinschrijving.

    De tiebreak voor ``_hoofdinschrijving`` partitioneert op ``levering`` zodat
    elke levering onafhankelijk precies één hoofdinschrijving per persoon × studiejaar
    krijgt.  Bij gestapelde analyses filtert de afnemer doorgaans op één levering.
    """
    vereist = {"_persoon_id", "Studiejaar", "Niveau", "Opleidingcode"}
    if not vereist.issubset(df.columns):
        return df.with_columns(
            pl.lit(None, dtype=pl.Boolean).alias("_hoogste_niveau"),
            pl.lit(None, dtype=pl.Boolean).alias("_laagste_CREBO"),
            pl.lit(None, dtype=pl.Boolean).alias("_hoofdinschrijving"),
        )

    df = df.with_columns(_niveau_numeriek(pl.col("Niveau")).alias("_niveau_num"))

    max_niveau = df.group_by(["_persoon_id", "Studiejaar"]).agg(
        pl.col("_niveau_num").max().alias("_max_niveau_num")
    )
    df = df.join(max_niveau, on=["_persoon_id", "Studiejaar"], how="left")
    df = df.with_columns(
        (pl.col("_niveau_num") == pl.col("_max_niveau_num")).alias("_hoogste_niveau")
    ).drop("_max_niveau_num")

    min_crebo = (
        df.filter(pl.col("_hoogste_niveau"))
        .group_by(["_persoon_id", "Studiejaar"])
        .agg(pl.col("Opleidingcode").min().alias("_min_crebo"))
    )
    df = df.join(min_crebo, on=["_persoon_id", "Studiejaar"], how="left")
    df = df.with_columns(
        (
            pl.col("_hoogste_niveau")
            & (pl.col("Opleidingcode") == pl.col("_min_crebo"))
        ).alias("_laagste_CREBO")
    ).drop("_min_crebo")

    hoofd_expr = pl.col("_hoogste_niveau") & pl.col("_laagste_CREBO")

    # Tiebreak: bij meerdere ISP-rijen met zelfde Niveau+CREBO,
    # kies de meest recente periode (DatumBegin desc).
    partition = [
        c for c in ("levering", "_persoon_id", "Studiejaar") if c in df.columns
    ]
    if "DatumBegin" in df.columns and partition:
        df = df.with_columns(hoofd_expr.alias("_kandidaat_hoofd"))
        df = df.with_columns(
            pl.when(pl.col("_kandidaat_hoofd"))
            .then(pl.col("DatumBegin").rank("ordinal", descending=True).over(partition))
            .otherwise(None)
            .alias("_hoofd_rank")
        )
        df = df.with_columns(
            (pl.col("_kandidaat_hoofd") & (pl.col("_hoofd_rank") == 1)).alias(
                "_hoofdinschrijving"
            )
        ).drop("_kandidaat_hoofd", "_hoofd_rank")
    else:
        df = df.with_columns(hoofd_expr.alias("_hoofdinschrijving"))

    return df.drop("_niveau_num")


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
        (_niveau_numeriek(pl.col("Niveau")) >= 2).fill_null(False)
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

    is_entree = _niveau_numeriek(pl.col("Niveau")) == 1

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
        df.filter(_niveau_numeriek(pl.col("Niveau")) >= 2)
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


def _voeg_afgeleide_velden_toe(df: pl.DataFrame) -> pl.DataFrame:
    """Voeg afgeleide gemaksvelden toe.

    ``Niveau_gecombineerd``: ``"MBO-4 BOL"`` — concat van Niveau en Leertraject.
    ``_tellingen_aanwezig``: hoe vaak deze persoon × inschrijving voorkomt
    over leveringen (datakwaliteit / deduplicatie).
    """
    if "Niveau" in df.columns and "Leertraject" in df.columns:
        df = df.with_columns(
            pl.concat_str(
                [pl.col("Niveau"), pl.col("Leertraject")],
                separator=" ",
                ignore_nulls=False,
            ).alias("Niveau_gecombineerd")
        )

    if "_persoon_id" in df.columns and "Inschrijvingvolgnummer" in df.columns:
        tellingen = df.group_by(["_persoon_id", "Inschrijvingvolgnummer"]).agg(
            pl.len().alias("_tellingen_aanwezig")
        )
        df = df.join(
            tellingen,
            on=["_persoon_id", "Inschrijvingvolgnummer"],
            how="left",
        )

    return df


def _bpv_aggregaat(bpv: pl.DataFrame) -> pl.DataFrame:
    """Aggregeer BPV per inschrijving: tellers en datumbereik."""
    bpv = _add_persoon_id(bpv)
    return bpv.group_by(_JOIN_INSCHRIJVING).agg(
        pl.len().alias("BPV_Aantal"),
        pl.col("Omvang").cast(pl.Float64, strict=False).sum().alias("BPV_TotaalOmvang"),
        pl.col("DatumBegin").min().alias("BPV_DatumBeginEerste"),
        pl.col("DatumEindWerkelijk").max().alias("BPV_DatumEindLaatste"),
    )


def _kzd_aggregaat(
    kzd: pl.DataFrame,
    dip: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Aggregeer KZD per inschrijving: totaal en behaald."""
    kzd = _add_persoon_id(kzd)
    kzd = _resolve_inschrijving(kzd, dip)
    behaald = pl.col("Resultaat").str.to_uppercase().str.contains(_RESULTAAT_BEHAALD)
    return kzd.group_by(_JOIN_INSCHRIJVING).agg(
        pl.len().alias("KZD_Aantal"),
        behaald.sum().cast(pl.Int64).alias("KZD_AantalBehaald"),
    )


def _amo_aggregaat(
    amo: pl.DataFrame,
    dip: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Aggregeer AMO per inschrijving: teller."""
    amo = _add_persoon_id(amo)
    amo = _resolve_inschrijving(amo, dip)
    return amo.group_by(_JOIN_INSCHRIJVING).agg(pl.len().alias("AMO_Aantal"))


# ---------------------------------------------------------------------------
# Bouw-functies per output-tabel
# ---------------------------------------------------------------------------


def _bouw_inschrijvingen(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """ISP-grain: alle record-types samengevoegd tot één platte analysetabel."""

    # ── Basis: ISP ───────────────────────────────────────────────────────────
    df = _add_persoon_id(stacked["ISP"])
    df = _drop(df, "Recordsoort")

    # ── PER: persoonskenmerken ────────────────────────────────────────────────
    per = _add_persoon_id(stacked["PER"])
    per = _drop(per, "Recordsoort", *_PERSOON_COLS)
    df = _join_left(df, per, on=_JOIN_PERSOON)

    # ── ISG: inschrijvingsdatums en reden uitschrijving ───────────────────────
    isg = _add_persoon_id(stacked["ISG"])
    isg_kolommen = [
        c
        for c in [
            "DatumInschrijving",
            "DatumUitschrijvingGepland",
            "DatumUitschrijvingWerkelijk",
            "RedenUitschrijving",
        ]
        if c in isg.columns
    ]
    df = _join_left(
        df,
        isg.select([*_JOIN_INSCHRIJVING, *isg_kolommen]),
        on=_JOIN_INSCHRIJVING,
    )

    # ── VLP: bestandsmetadata; BRIN invullen voor RO-rijen ───────────────────
    vlp = _drop(stacked["VLP"], "Recordsoort")
    vlp_extra = [c for c in vlp.columns if c not in ["levering", "BRIN"]]
    df = _join_left(
        df,
        vlp.select(["levering", "BRIN", *vlp_extra]),
        on=["levering"],
        suffix="_vlp",
    )
    # RO-ISP heeft geen BRIN: vul op uit VLP
    if "BRIN_vlp" in df.columns:
        df = df.with_columns(pl.coalesce(["BRIN", "BRIN_vlp"]).alias("BRIN")).drop(
            "BRIN_vlp"
        )

    # ── ISE: extra ondersteuning (0-1 per inschrijving) ──────────────────────
    if "ISE" in stacked and not stacked["ISE"].is_empty():
        ise = _add_persoon_id(stacked["ISE"])
        ise_extra = [
            c
            for c in ise.columns
            if c not in [*_JOIN_INSCHRIJVING, *_PERSOON_COLS, "Recordsoort"]
        ]
        ise_sel = ise.select([*_JOIN_INSCHRIJVING, *ise_extra]).rename(
            {c: f"ISE_{c}" for c in ise_extra}
        )
        df = _join_left(df, ise_sel, on=_JOIN_INSCHRIJVING)

    # ── DIP: diploma (0-1 per inschrijving in MBO) ───────────────────────────
    if "DIP" in stacked and not stacked["DIP"].is_empty():
        dip = _add_persoon_id(stacked["DIP"])
        dip_extra = [
            c
            for c in dip.columns
            if c
            not in [
                *_JOIN_INSCHRIJVING,
                *_PERSOON_COLS,
                "Recordsoort",
                "_onbekend",
                "BRIN",
            ]
        ]
        dip_sel = dip.select([*_JOIN_INSCHRIJVING, *dip_extra]).rename(
            {c: f"DIP_{c}" for c in dip_extra}
        )
        df = _join_left(df, dip_sel, on=_JOIN_INSCHRIJVING)

    # ── DIP wordt ook gebruikt als fallback voor GEO/KZD/AMO Inschrijvingvolgnummer
    dip_raw = stacked.get("DIP")

    # ── GEO: examenresultaten (dynamisch gepivoteerd) ─────────────────────────
    if "GEO" in stacked and not stacked["GEO"].is_empty():
        geo_pivot = _geo_pivot(stacked["GEO"], dip=dip_raw)
        if geo_pivot is not None:
            df = _join_left(df, geo_pivot, on=_JOIN_INSCHRIJVING)

    # ── BPV aggregaat ─────────────────────────────────────────────────────────
    if "BPV" in stacked and not stacked["BPV"].is_empty():
        df = _join_left(df, _bpv_aggregaat(stacked["BPV"]), on=_JOIN_INSCHRIJVING)

    # ── KZD aggregaat ─────────────────────────────────────────────────────────
    if "KZD" in stacked and not stacked["KZD"].is_empty():
        df = _join_left(
            df, _kzd_aggregaat(stacked["KZD"], dip=dip_raw), on=_JOIN_INSCHRIJVING
        )

    # ── AMO aggregaat ─────────────────────────────────────────────────────────
    if "AMO" in stacked and not stacked["AMO"].is_empty():
        df = _join_left(
            df, _amo_aggregaat(stacked["AMO"], dip=dip_raw), on=_JOIN_INSCHRIJVING
        )

    df = _leid_studiejaar_af(df)
    df = _vul_niveau_aan(df)
    df = _voeg_bekostigingsvlaggen_toe(df)
    df = _voeg_sr_vlaggen_toe(df)
    df = _voeg_telling_en_jr_vlaggen_toe(df)
    df = _voeg_dr_vlaggen_toe(df)
    df = _voeg_entree_vlaggen_toe(df)
    return _voeg_afgeleide_velden_toe(df)


def _bouw_detail_bpv(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """BPV volledig uitgesplitst.

    Joinbaar via (levering, _persoon_id, Inschrijvingvolgnummer).
    """
    if "BPV" not in stacked or stacked["BPV"].is_empty():
        return pl.DataFrame()
    df = _add_persoon_id(stacked["BPV"])
    df = _drop(df, "Recordsoort")
    # _persoon_id direct na levering plaatsen
    overig = [c for c in df.columns if c not in ["levering", "_persoon_id"]]
    return df.select(["levering", "_persoon_id", *overig])


def _bouw_detail_kzd_amo(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """KZD en AMO volledig; kolom ``_bron`` geeft herkomst aan."""
    frames: list[pl.DataFrame] = []
    dip_raw = stacked.get("DIP")
    for bron in ("KZD", "AMO"):
        if bron in stacked and not stacked[bron].is_empty():
            df = _add_persoon_id(stacked[bron])
            df = _resolve_inschrijving(df, dip_raw)
            df = _drop(df, "Recordsoort")
            df = df.with_columns(pl.lit(bron).alias("_bron"))
            frames.append(df)
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _bouw_detail_bekostiging(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """BII (GRONDSLAG) + TBGI-Teldatum; één rij per inschrijving × teldatum."""
    frames: list[pl.DataFrame] = []

    if "BII" in stacked and not stacked["BII"].is_empty():
        bii = _add_persoon_id(stacked["BII"])
        bii = _drop(bii, "Recordsoort")
        bii = bii.with_columns(pl.lit("BII").alias("_bron"))
        frames.append(bii)

    if "Teldatum" in stacked and not stacked["Teldatum"].is_empty():
        td = stacked["Teldatum"].clone()
        # Voeg _persoon_id toe via de TBGI Inschrijving-tabel (heeft BSN)
        if "Inschrijving" in stacked and not stacked["Inschrijving"].is_empty():
            inschrijving_sleutel = stacked["Inschrijving"].select(
                [
                    "levering",
                    "BRIN",
                    "Inschrijvingvolgnummer",
                    "Burgerservicenummer",
                    "Onderwijsnummer",
                ]
            )
            td = td.join(
                inschrijving_sleutel,
                on=["levering", "BRIN", "Inschrijvingvolgnummer"],
                how="left",
            )
        td = _add_persoon_id(td)
        td = td.with_columns(pl.lit("TBGI").alias("_bron"))
        frames.append(td)

    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _bouw_detail_bekostiging_diploma(
    stacked: dict[str, pl.DataFrame],
) -> pl.DataFrame:
    """TBGI-Diploma bekostigingsbijdragen; één rij per inschrijving × diploma.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, Resultaatvolgnummer).
    """
    if "Diploma" not in stacked or stacked["Diploma"].is_empty():
        return pl.DataFrame()
    dip = stacked["Diploma"].clone()
    dip = _add_persoon_id(dip)
    dip = _drop(dip, *_PERSOON_COLS)
    return dip


def _bouw_detail_geo(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """GEO in long format.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, CodeGeneriekExamenonderdeel).

    Behoudt DatumResultaat, VrijstellingIE/CE en Onderwijsaanbieder die
    in de GEO-pivot van inschrijvingen verloren gaan.
    Joinbaar met fact_inschrijving via de eerste drie sleutelkolommen.
    """
    if "GEO" not in stacked or stacked["GEO"].is_empty():
        return pl.DataFrame()
    geo = _add_persoon_id(stacked["GEO"])
    geo = _resolve_inschrijving(geo, stacked.get("DIP"))
    geo = _drop(geo, "Recordsoort", *_PERSOON_COLS)
    overig = [c for c in geo.columns if c not in ["levering", "_persoon_id"]]
    return geo.select(["levering", "_persoon_id", *overig])


def _bouw_tbgi_inschrijvingen(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Inschrijving-grain voor TBGI-only input (geen ISP beschikbaar).

    Gebruikt TBGI Inschrijving als vervanging voor ISP; verrijkt met Teldatum
    aggregaat zodat de grain bruikbaar is voor analyse.
    """
    df = _add_persoon_id(stacked["Inschrijving"])
    df = _drop(df, "Recordsoort")
    df = _leid_studiejaar_af(df)
    df = _vul_niveau_aan(df)
    df = _voeg_bekostigingsvlaggen_toe(df)
    df = _voeg_sr_vlaggen_toe(df)
    df = _voeg_telling_en_jr_vlaggen_toe(df)
    df = _voeg_dr_vlaggen_toe(df)
    df = _voeg_entree_vlaggen_toe(df)
    return _voeg_afgeleide_velden_toe(df)


def _bouw_meta_leveringen(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """VLP + SLR per bronbestand; één rij per levering."""
    vlp = _drop(stacked.get("VLP", pl.DataFrame()), "Recordsoort")
    slr = _drop(stacked.get("SLR", pl.DataFrame()), "Recordsoort")

    if vlp.is_empty() and slr.is_empty():
        return pl.DataFrame()
    if vlp.is_empty():
        return slr
    if slr.is_empty():
        return vlp
    return vlp.join(slr, on="levering", how="left")


# ---------------------------------------------------------------------------
# Interne aggregaat-API (voor star.py)
# ---------------------------------------------------------------------------


def _bouw_analysetabellen(stacked: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Bouw zeven analysetabellen vanuit gestapelde genormaliseerde records.

    Args:
        stacked: Output van :func:`~mbo_bekostiging_bestanden.stack.stack_prepared`,
                 dict van tabelnaam → DataFrame.

    Returns:
        Dict met zeven sleutels:
        ``inschrijvingen``, ``detail_bpv``, ``detail_kzd_amo``,
        ``detail_bekostiging``, ``detail_bekostiging_diploma``,
        ``detail_geo``, ``meta_leveringen``.
    """
    heeft_isp = "ISP" in stacked and not stacked["ISP"].is_empty()
    heeft_inschrijving = (
        "Inschrijving" in stacked and not stacked["Inschrijving"].is_empty()
    )

    if not heeft_isp and not heeft_inschrijving:
        raise ValueError(
            "Gestapelde data bevat geen ISP- of Inschrijving-records; "
            "analysetabellen kunnen niet worden gebouwd."
        )

    return {
        "inschrijvingen": enrich_inschrijvingen(
            _bouw_inschrijvingen(stacked)
            if heeft_isp
            else _bouw_tbgi_inschrijvingen(stacked)
        ),
        "detail_bpv": _bouw_detail_bpv(stacked),
        "detail_kzd_amo": _bouw_detail_kzd_amo(stacked),
        "detail_bekostiging": _bouw_detail_bekostiging(stacked),
        "detail_bekostiging_diploma": _bouw_detail_bekostiging_diploma(stacked),
        "detail_geo": _bouw_detail_geo(stacked),
        "meta_leveringen": _bouw_meta_leveringen(stacked),
    }
