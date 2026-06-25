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
"""

import polars as pl

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

    return obt


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
    inschrijving = _add_persoon_id(stacked["Inschrijving"])
    return _drop(inschrijving, "Recordsoort")


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
        "obt_inschrijvingen": (
            _bouw_obt_inschrijvingen(stacked)
            if heeft_isp
            else _bouw_tbgi_inschrijvingen(stacked)
        ),
        "detail_bpv": _bouw_detail_bpv(stacked),
        "detail_kzd_amo": _bouw_detail_kzd_amo(stacked),
        "detail_bekostiging": _bouw_detail_bekostiging(stacked),
        "meta_leveringen": _bouw_meta_leveringen(stacked),
    }
