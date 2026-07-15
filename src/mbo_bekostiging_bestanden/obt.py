"""OBT (One Big Table) bouwen vanuit gestapelde genormaliseerde records.

Vijf output-tabellen (nul informatieverlies):
  obt_inschrijvingen  ISP-grain, alles flat + dynamische GEO-pivot +
                      BPV/KZD/AMO geaggregeerd
  detail_bpv          BPV volledig uitgesplitst, joinbaar op
                      (levering, _persoon_id, Inschrijvingvolgnummer)
  detail_kzd_amo      KZD en AMO volledig, kolom _bron geeft herkomst aan
  detail_bekostiging  BII (GRONDSLAG) + TBGI-Teldatum per
                      inschrijving × teldatum
  meta_leveringen     VLP + SLR per bronbestand

Berekende vlaggen op obt_inschrijvingen:
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

from mbo_bekostiging_bestanden.enrich import enrich_obt

_METADATA = Path(__file__).parent / "metadata"


@functools.cache
def _laad_crebo_niveau() -> pl.DataFrame:
    """Laad CREBO-tabel en geef mapping Opleidingcode → Niveau (MBO-n)."""
    return (
        pl.read_csv(_METADATA / "crebo.csv", infer_schema_length=0)
        .select(["code", "niveau"])
        .filter(pl.col("niveau").is_not_null())
        .with_columns(
            ("MBO-" + pl.col("niveau")).alias("_crebo_niveau"),
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

    dip_sleutel = _add_persoon_id(dip).select(
        ["levering", "_persoon_id", "Resultaatvolgnummer", "Inschrijvingvolgnummer"]
    ).rename({
        "Resultaatvolgnummer": "_dip_vnr",
        "Inschrijvingvolgnummer": "_isg_via_dip",
    })

    if "ResultaatvolgnummerDiploma" not in df.columns:
        return df

    df = df.join(
        dip_sleutel,
        left_on=["levering", "_persoon_id", "ResultaatvolgnummerDiploma"],
        right_on=["levering", "_persoon_id", "_dip_vnr"],
        how="left",
    )
    return df.with_columns(
        pl.coalesce(["Inschrijvingvolgnummer", "_isg_via_dip"])
        .alias("Inschrijvingvolgnummer")
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
            "Eindcijfer", "CijferIE", "CijferCE",
            "VrijstellingGeneriekExamenonderdeel",
        ]:
            prefix = f"{veld}_"
            if col.startswith(prefix):
                code = col[len(prefix):]
                is_vrijstelling = veld == "VrijstellingGeneriekExamenonderdeel"
                kort_veld = "Vrijstelling" if is_vrijstelling else veld
                hernoem[col] = f"GEO_{code}_{kort_veld}"
    return pivot.rename(hernoem)


def _vul_niveau_aan(obt: pl.DataFrame) -> pl.DataFrame:
    """Vul ontbrekend Niveau aan via de CREBO-tabel (Opleidingcode → MBO-n)."""
    if "Niveau" not in obt.columns or "Opleidingcode" not in obt.columns:
        return obt
    if obt["Niveau"].null_count() == 0:
        return obt
    crebo = _laad_crebo_niveau()
    obt = obt.join(crebo, on="Opleidingcode", how="left")
    obt = obt.with_columns(
        pl.coalesce(["Niveau", "_crebo_niveau"]).alias("Niveau"),
    )
    return obt.drop("_crebo_niveau")


def _voeg_bekostigingsvlaggen_toe(obt: pl.DataFrame) -> pl.DataFrame:
    if "Studiejaar" not in obt.columns:
        return obt.with_columns(
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
    oct_1 = pl.date(studiejaar, 10, 1)

    if "DatumInschrijving" in obt.columns:
        datum_in = pl.col("DatumInschrijving")
        datum_uit = (
            pl.col("DatumUitschrijvingWerkelijk")
            if "DatumUitschrijvingWerkelijk" in obt.columns
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
        ingeschreven_later = (
            pl.lit(None, dtype=pl.Boolean).alias("_ingeschreven_jaar_later")
        )

    obt = obt.with_columns(actief, ingeschreven_later)

    bekostigd = (
        pl.col("_actief_1_oktober") & (pl.col("IndicatieBekostigbaar") == "J")
        if "IndicatieBekostigbaar" in obt.columns
        else pl.col("_actief_1_oktober") & pl.lit(False)
    ).alias("_bekostigd_eerste_1okt")

    if "DIP_DatumResultaat" in obt.columns:
        jaar_begin = pl.date(studiejaar - 1, 8, 1)
        jaar_eind = pl.date(studiejaar, 7, 31)
        dip_datum = pl.col("DIP_DatumResultaat")
        gediplomeerd = (
            dip_datum.is_not_null()
            & (dip_datum >= jaar_begin)
            & (dip_datum <= jaar_eind)
        ).fill_null(False).alias("_gediplomeerd_in_jaar")
    else:
        gediplomeerd = pl.lit(False, dtype=pl.Boolean).alias("_gediplomeerd_in_jaar")

    obt = obt.with_columns(bekostigd, gediplomeerd)

    obt = obt.with_columns(
        (pl.col("_actief_1_oktober") & ~pl.col("_bekostigd_eerste_1okt"))
        .alias("_deelnemer_niet_bekostigd_eerste_1okt")
    )

    studiejaar_serie = obt["Studiejaar"].cast(pl.Int32).drop_nulls()
    if studiejaar_serie.is_empty():
        return obt.with_columns(
            pl.lit(None, dtype=pl.Int64).alias("Opbrengstjaar_uitsplitsing"),
            pl.lit(None, dtype=pl.Boolean).alias("_driejaars_teljaar"),
            pl.lit(None, dtype=pl.Utf8).alias("Opbrengstjaar_3jaars_voortschrijdend"),
            pl.lit(None, dtype=pl.Int64).alias("_num_opbrengstjaar_3jr"),
        )

    max_jaar = studiejaar_serie.sort(descending=True).item(0)
    opbrengstjaar_label = f"{max_jaar - 2}-{max_jaar}"
    return obt.with_columns(
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


def _voeg_sr_vlaggen_toe(obt: pl.DataFrame) -> pl.DataFrame:
    """Selectie/rendement-vlaggen: hoogste niveau, laagste CREBO, hoofdinschrijving.

    De tiebreak voor ``_hoofdinschrijving`` partitioneert op ``levering`` zodat
    elke levering onafhankelijk precies één hoofdinschrijving per persoon × studiejaar
    krijgt.  Bij gestapelde analyses filtert de afnemer doorgaans op één levering.
    """
    vereist = {"_persoon_id", "Studiejaar", "Niveau", "Opleidingcode"}
    if not vereist.issubset(obt.columns):
        return obt.with_columns(
            pl.lit(None, dtype=pl.Boolean).alias("_hoogste_niveau"),
            pl.lit(None, dtype=pl.Boolean).alias("_laagste_CREBO"),
            pl.lit(None, dtype=pl.Boolean).alias("_hoofdinschrijving"),
        )

    obt = obt.with_columns(_niveau_numeriek(pl.col("Niveau")).alias("_niveau_num"))

    max_niveau = obt.group_by(["_persoon_id", "Studiejaar"]).agg(
        pl.col("_niveau_num").max().alias("_max_niveau_num")
    )
    obt = obt.join(max_niveau, on=["_persoon_id", "Studiejaar"], how="left")
    obt = obt.with_columns(
        (pl.col("_niveau_num") == pl.col("_max_niveau_num")).alias("_hoogste_niveau")
    ).drop("_max_niveau_num")

    min_crebo = (
        obt.filter(pl.col("_hoogste_niveau"))
        .group_by(["_persoon_id", "Studiejaar"])
        .agg(pl.col("Opleidingcode").min().alias("_min_crebo"))
    )
    obt = obt.join(min_crebo, on=["_persoon_id", "Studiejaar"], how="left")
    obt = obt.with_columns(
        (
            pl.col("_hoogste_niveau")
            & (pl.col("Opleidingcode") == pl.col("_min_crebo"))
        ).alias("_laagste_CREBO")
    ).drop("_min_crebo")

    hoofd_expr = pl.col("_hoogste_niveau") & pl.col("_laagste_CREBO")

    # Tiebreak: bij meerdere ISP-rijen met zelfde Niveau+CREBO,
    # kies de meest recente periode (DatumBegin desc).
    partition = [c for c in ("levering", "_persoon_id", "Studiejaar")
                 if c in obt.columns]
    if "DatumBegin" in obt.columns and partition:
        obt = obt.with_columns(hoofd_expr.alias("_kandidaat_hoofd"))
        obt = obt.with_columns(
            pl.when(pl.col("_kandidaat_hoofd"))
            .then(
                pl.col("DatumBegin")
                .rank("ordinal", descending=True)
                .over(partition)
            )
            .otherwise(None)
            .alias("_hoofd_rank")
        )
        obt = obt.with_columns(
            (pl.col("_kandidaat_hoofd") & (pl.col("_hoofd_rank") == 1))
            .alias("_hoofdinschrijving")
        ).drop("_kandidaat_hoofd", "_hoofd_rank")
    else:
        obt = obt.with_columns(hoofd_expr.alias("_hoofdinschrijving"))

    return obt.drop("_niveau_num")


def _voeg_telling_en_jr_vlaggen_toe(obt: pl.DataFrame) -> pl.DataFrame:
    """Voeg ``_telling`` en JR-bouwstenen toe.

    ``_telling``: deduplicatievlag voor tellingen — actief op 1 oktober én
    hoofdinschrijving.  ``_jr_noemer``/``_jr_teller``: bouwstenen voor het
    Jaarresultaat (sum/sum door downstream).
    """
    heeft_actief = "_actief_1_oktober" in obt.columns
    heeft_hoofd = "_hoofdinschrijving" in obt.columns

    if heeft_actief and heeft_hoofd:
        obt = obt.with_columns(
            (
                pl.col("_actief_1_oktober").fill_null(False)
                & pl.col("_hoofdinschrijving").fill_null(False)
            ).alias("_telling")
        )
    else:
        obt = obt.with_columns(pl.lit(False).alias("_telling"))

    heeft_gediplomeerd = "_gediplomeerd_in_jaar" in obt.columns
    heeft_ingeschreven = "_ingeschreven_jaar_later" in obt.columns

    obt = obt.with_columns(pl.col("_telling").alias("_jr_noemer"))

    if heeft_gediplomeerd and heeft_ingeschreven:
        obt = obt.with_columns(
            (
                pl.col("_jr_noemer")
                & (
                    pl.col("_gediplomeerd_in_jaar").fill_null(False)
                    | pl.col("_ingeschreven_jaar_later").fill_null(False)
                )
            ).alias("_jr_teller")
        )
    else:
        obt = obt.with_columns(pl.lit(False).alias("_jr_teller"))

    return obt


def _voeg_entree_vlaggen_toe(obt: pl.DataFrame) -> pl.DataFrame:
    """Voeg ``_entree_uitstroom`` en ``_entree_doorstroom`` toe.

    Alleen relevant voor MBO-1 (Entree) inschrijvingen.
    Doorstroom = dezelfde persoon heeft een ISP op MBO-2+ niveau.
    """
    vereist = {"Niveau", "_persoon_id"}
    if not vereist.issubset(obt.columns):
        return obt.with_columns(
            pl.lit(None, dtype=pl.Boolean).alias("_entree_uitstroom"),
            pl.lit(None, dtype=pl.Boolean).alias("_entree_doorstroom"),
        )

    is_entree = _niveau_numeriek(pl.col("Niveau")) == 1

    heeft_uitschrijving = (
        "DatumUitschrijvingWerkelijk" in obt.columns
        and "DatumUitschrijvingGepland" in obt.columns
    )
    if heeft_uitschrijving:
        obt = obt.with_columns(
            (
                is_entree
                & pl.col("DatumUitschrijvingWerkelijk").is_not_null()
            )
            .fill_null(False)
            .alias("_entree_uitstroom")
        )
    else:
        obt = obt.with_columns(
            pl.lit(False).alias("_entree_uitstroom")
        )

    join_cols = ["_persoon_id"]
    if "BRIN" in obt.columns:
        join_cols.append("BRIN")
    hoger_niveau = (
        obt.filter(_niveau_numeriek(pl.col("Niveau")) >= 2)
        .select(join_cols)
        .unique()
        .with_columns(pl.lit(True).alias("_heeft_hoger"))
    )
    obt = obt.join(hoger_niveau, on=join_cols, how="left")
    obt = obt.with_columns(
        (is_entree & pl.col("_heeft_hoger").fill_null(False))
        .fill_null(False)
        .alias("_entree_doorstroom")
    ).drop("_heeft_hoger")

    return obt


def _voeg_afgeleide_velden_toe(obt: pl.DataFrame) -> pl.DataFrame:
    """Voeg afgeleide gemaksvelden toe.

    ``Niveau_gecombineerd``: ``"MBO-4 BOL"`` — concat van Niveau en Leertraject.
    ``_tellingen_aanwezig``: hoe vaak deze persoon × inschrijving voorkomt
    over leveringen (datakwaliteit / deduplicatie).
    """
    if "Niveau" in obt.columns and "Leertraject" in obt.columns:
        obt = obt.with_columns(
            pl.concat_str(
                [pl.col("Niveau"), pl.col("Leertraject")],
                separator=" ",
                ignore_nulls=False,
            ).alias("Niveau_gecombineerd")
        )

    if "_persoon_id" in obt.columns and "Inschrijvingvolgnummer" in obt.columns:
        tellingen = obt.group_by(
            ["_persoon_id", "Inschrijvingvolgnummer"]
        ).agg(pl.len().alias("_tellingen_aanwezig"))
        obt = obt.join(
            tellingen,
            on=["_persoon_id", "Inschrijvingvolgnummer"],
            how="left",
        )

    return obt


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
    behaald = pl.col("Resultaat").str.to_uppercase().str.contains("BEHAALD")
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


def _bouw_obt_inschrijvingen(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """ISP-grain OBT: alle record-types samengevoegd tot één platte tabel."""

    # ── Basis: ISP ───────────────────────────────────────────────────────────
    obt = _add_persoon_id(stacked["ISP"])
    obt = _drop(obt, "Recordsoort")

    # ── PER: persoonskenmerken ────────────────────────────────────────────────
    per = _add_persoon_id(stacked["PER"])
    per = _drop(per, "Recordsoort", *_PERSOON_COLS)
    obt = _join_left(obt, per, on=_JOIN_PERSOON)

    # ── ISG: inschrijvingsdatums en reden uitschrijving ───────────────────────
    isg = _add_persoon_id(stacked["ISG"])
    isg_kolommen = [
        c for c in ["DatumInschrijving", "DatumUitschrijvingGepland",
                    "DatumUitschrijvingWerkelijk", "RedenUitschrijving"]
        if c in isg.columns
    ]
    obt = _join_left(
        obt,
        isg.select([*_JOIN_INSCHRIJVING, *isg_kolommen]),
        on=_JOIN_INSCHRIJVING,
    )

    # ── VLP: bestandsmetadata; BRIN invullen voor RO-rijen ───────────────────
    vlp = _drop(stacked["VLP"], "Recordsoort")
    vlp_extra = [c for c in vlp.columns if c not in ["levering", "BRIN"]]
    obt = _join_left(
        obt,
        vlp.select(["levering", "BRIN", *vlp_extra]),
        on=["levering"],
        suffix="_vlp",
    )
    # RO-ISP heeft geen BRIN: vul op uit VLP
    if "BRIN_vlp" in obt.columns:
        obt = obt.with_columns(
            pl.coalesce(["BRIN", "BRIN_vlp"]).alias("BRIN")
        ).drop("BRIN_vlp")

    # ── ISE: extra ondersteuning (0-1 per inschrijving) ──────────────────────
    if "ISE" in stacked and not stacked["ISE"].is_empty():
        ise = _add_persoon_id(stacked["ISE"])
        ise_extra = [c for c in ise.columns
                     if c not in [*_JOIN_INSCHRIJVING, *_PERSOON_COLS, "Recordsoort"]]
        ise_sel = ise.select([*_JOIN_INSCHRIJVING, *ise_extra]).rename(
            {c: f"ISE_{c}" for c in ise_extra}
        )
        obt = _join_left(obt, ise_sel, on=_JOIN_INSCHRIJVING)

    # ── DIP: diploma (0-1 per inschrijving in MBO) ───────────────────────────
    if "DIP" in stacked and not stacked["DIP"].is_empty():
        dip = _add_persoon_id(stacked["DIP"])
        dip_extra = [c for c in dip.columns
                     if c not in [*_JOIN_INSCHRIJVING, *_PERSOON_COLS,
                                  "Recordsoort", "_onbekend", "BRIN"]]
        dip_sel = dip.select([*_JOIN_INSCHRIJVING, *dip_extra]).rename(
            {c: f"DIP_{c}" for c in dip_extra}
        )
        obt = _join_left(obt, dip_sel, on=_JOIN_INSCHRIJVING)

    # ── DIP wordt ook gebruikt als fallback voor GEO/KZD/AMO Inschrijvingvolgnummer
    dip_raw = stacked.get("DIP")

    # ── GEO: examenresultaten (dynamisch gepivoteerd) ─────────────────────────
    if "GEO" in stacked and not stacked["GEO"].is_empty():
        geo_pivot = _geo_pivot(stacked["GEO"], dip=dip_raw)
        if geo_pivot is not None:
            obt = _join_left(obt, geo_pivot, on=_JOIN_INSCHRIJVING)

    # ── BPV aggregaat ─────────────────────────────────────────────────────────
    if "BPV" in stacked and not stacked["BPV"].is_empty():
        obt = _join_left(obt, _bpv_aggregaat(stacked["BPV"]), on=_JOIN_INSCHRIJVING)

    # ── KZD aggregaat ─────────────────────────────────────────────────────────
    if "KZD" in stacked and not stacked["KZD"].is_empty():
        obt = _join_left(
            obt, _kzd_aggregaat(stacked["KZD"], dip=dip_raw), on=_JOIN_INSCHRIJVING
        )

    # ── AMO aggregaat ─────────────────────────────────────────────────────────
    if "AMO" in stacked and not stacked["AMO"].is_empty():
        obt = _join_left(
            obt, _amo_aggregaat(stacked["AMO"], dip=dip_raw), on=_JOIN_INSCHRIJVING
        )

    obt = _vul_niveau_aan(obt)
    obt = _voeg_bekostigingsvlaggen_toe(obt)
    obt = _voeg_sr_vlaggen_toe(obt)
    obt = _voeg_telling_en_jr_vlaggen_toe(obt)
    obt = _voeg_entree_vlaggen_toe(obt)
    return _voeg_afgeleide_velden_toe(obt)


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
                ["levering", "BRIN", "Inschrijvingvolgnummer",
                 "Burgerservicenummer", "Onderwijsnummer"]
            )
            td = td.join(inschrijving_sleutel,
                         on=["levering", "BRIN", "Inschrijvingvolgnummer"],
                         how="left")
        td = _add_persoon_id(td)
        td = td.with_columns(pl.lit("TBGI").alias("_bron"))
        frames.append(td)

    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _bouw_tbgi_inschrijvingen(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Inschrijving-grain voor TBGI-only input (geen ISP beschikbaar).

    Gebruikt TBGI Inschrijving als vervanging voor ISP; verrijkt met Teldatum
    aggregaat zodat de grain bruikbaar is voor analyse.
    """
    obt = _add_persoon_id(stacked["Inschrijving"])
    obt = _drop(obt, "Recordsoort")
    obt = _vul_niveau_aan(obt)
    obt = _voeg_bekostigingsvlaggen_toe(obt)
    obt = _voeg_sr_vlaggen_toe(obt)
    obt = _voeg_telling_en_jr_vlaggen_toe(obt)
    obt = _voeg_entree_vlaggen_toe(obt)
    return _voeg_afgeleide_velden_toe(obt)


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
# Publieke API
# ---------------------------------------------------------------------------


def build_obt(stacked: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Bouw vijf OBT-output-tabellen vanuit gestapelde genormaliseerde records.

    Args:
        stacked: Output van :func:`~mbo_bekostiging_bestanden.stack.stack_prepared`,
                 dict van tabelnaam → DataFrame.

    Returns:
        Dict met vijf sleutels:
        ``obt_inschrijvingen``, ``detail_bpv``, ``detail_kzd_amo``,
        ``detail_bekostiging``, ``meta_leveringen``.
    """
    heeft_isp = "ISP" in stacked and not stacked["ISP"].is_empty()
    heeft_inschrijving = (
        "Inschrijving" in stacked and not stacked["Inschrijving"].is_empty()
    )

    if not heeft_isp and not heeft_inschrijving:
        raise ValueError(
            "Gestapelde data bevat geen ISP- of Inschrijving-records; "
            "OBT kan niet worden gebouwd."
        )

    return {
        "obt_inschrijvingen": enrich_obt(
            _bouw_obt_inschrijvingen(stacked)
            if heeft_isp
            else _bouw_tbgi_inschrijvingen(stacked)
        ),
        "detail_bpv": _bouw_detail_bpv(stacked),
        "detail_kzd_amo": _bouw_detail_kzd_amo(stacked),
        "detail_bekostiging": _bouw_detail_bekostiging(stacked),
        "meta_leveringen": _bouw_meta_leveringen(stacked),
    }
