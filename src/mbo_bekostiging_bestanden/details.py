"""Detailtabellen (BPV, KZD/AMO, GEO, bekostiging) en hun aggregaten per periode.

Elke detailtabel draagt ``_inschrijving_periode_id``: de periode waarin de rij
valt (zie :func:`koppel_aan_periode`), joinbaar zonder fan-out.
"""

import polars as pl

from mbo_bekostiging_bestanden.contracts import (
    BRON,
    BRON_BID,
    BRON_BII,
    BRON_TBGI,
    JOIN_INSCHRIJVING,
    JOIN_INSTELLING_INSCHRIJVING,
    PERIODE_ID,
)
from mbo_bekostiging_bestanden.koppelingen import Koppelingen
from mbo_bekostiging_bestanden.perioden import koppel_periode_id
from mbo_bekostiging_bestanden.stack import heeft_records
from mbo_bekostiging_bestanden.waardenlijsten import kzd_behaald

# Een GRONDSLAG-BID mist inschrijving, opleiding en behaaldatum; die staan op
# het DIP-record van hetzelfde diploma (PvE §17.5). Namen zoals TBG-i (#208).
_JOIN_DIPLOMA = ["levering", "BRIN", "_persoon_id", "Resultaatvolgnummer"]
_BID_VAN_DIP = {
    "Inschrijvingvolgnummer": "Inschrijvingvolgnummer",
    "Opleidingcode": "Opleidingcode",
    "DatumResultaat": "DatumBehaald",
}
# Per detailtabel de datum die bepaalt in welke ISP-periode een rij valt.
_PERIODE_REFERENTIEDATUM = {
    "detail_bpv": "DatumBegin",
    "detail_kzd_amo": "DatumResultaat",
    "detail_bekostiging": "Teldatum",
    "detail_bekostiging_diploma": "DatumBehaald",
    "detail_geo": "DatumResultaat",
}
# Koppelsleutels naar de inschrijvingsperiode, in voorkeursvolgorde (#112).
# Bekostiging (TBGI) komt altijd uit een andere levering dan de RO-perioden;
# lukt koppelen binnen de eigen levering niet, dan — alleen als er een passende
# inschrijving is — via instelling, persoon en inschrijving.
_PERIODE_KOPPELSLEUTELS = {
    "detail_bekostiging": (JOIN_INSCHRIJVING, JOIN_INSTELLING_INSCHRIJVING),
    "detail_bekostiging_diploma": (JOIN_INSCHRIJVING, JOIN_INSTELLING_INSCHRIJVING),
}
# GEO-velden in de pivot op inschrijvingen → korte naam in ``GEO_{code}_{veld}``.
_GEO_PIVOT_VELDEN = {
    "Eindcijfer": "Eindcijfer",
    "CijferIE": "CijferIE",
    "CijferCE": "CijferCE",
    "VrijstellingGeneriekExamenonderdeel": "Vrijstelling",
}


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
    df = df.with_columns(
        pl.when(pl.col("Inschrijvingvolgnummer") == "")
        .then(None)
        .otherwise(pl.col("Inschrijvingvolgnummer"))
        .alias("Inschrijvingvolgnummer")
    )

    if dip is None or dip.is_empty() or "ResultaatvolgnummerDiploma" not in df.columns:
        return df

    dip_sleutel = dip.select(
        ["levering", "_persoon_id", "Resultaatvolgnummer", "Inschrijvingvolgnummer"]
    ).rename(
        {
            "Resultaatvolgnummer": "_dip_vnr",
            "Inschrijvingvolgnummer": "_isg_via_dip",
        }
    )
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


def geo_pivot(
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

    geo = _resolve_inschrijving(geo, dip)
    index = [*JOIN_INSCHRIJVING]
    agg = geo.group_by([*index, "CodeGeneriekExamenonderdeel"]).agg(
        pl.col("Eindcijfer").max(),
        pl.col("CijferIE").max(),
        pl.col("CijferCE").max(),
        pl.col("VrijstellingGeneriekExamenonderdeel").first(),
    )
    pivot = agg.pivot(
        on="CodeGeneriekExamenonderdeel",
        index=index,
        values=list(_GEO_PIVOT_VELDEN),
        aggregate_function="first",
    )
    hernoem = {
        col: f"GEO_{col.removeprefix(f'{veld}_')}_{kort}"
        for col in pivot.columns
        for veld, kort in _GEO_PIVOT_VELDEN.items()
        if col.startswith(f"{veld}_")
    }
    return pivot.rename(hernoem)


def _per_periode(
    detail: pl.DataFrame,
    perioden: pl.DataFrame,
    tabel: str,
    *aggregaten: pl.Expr,
) -> pl.DataFrame:
    """Aggregeer detailrijen per ISP-periode (zelfde toewijzing als de detail-feiten).

    Rijen zonder bijbehorende periode tellen niet mee.
    """
    return (
        koppel_periode_id(detail, perioden, _PERIODE_REFERENTIEDATUM[tabel])
        .drop_nulls(PERIODE_ID)
        .group_by(PERIODE_ID)
        .agg(*aggregaten)
    )


def bpv_aggregaat(bpv: pl.DataFrame, perioden: pl.DataFrame) -> pl.DataFrame:
    """Aggregeer BPV per ISP-periode: tellers en datumbereik."""
    return _per_periode(
        bpv,
        perioden,
        "detail_bpv",
        pl.len().alias("BPV_Aantal"),
        pl.col("Omvang").cast(pl.Float64, strict=False).sum().alias("BPV_TotaalOmvang"),
        pl.col("DatumBegin").min().alias("BPV_DatumBeginEerste"),
        pl.col("DatumEindWerkelijk").max().alias("BPV_DatumEindLaatste"),
    )


def kzd_aggregaat(
    kzd: pl.DataFrame,
    perioden: pl.DataFrame,
    dip: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Aggregeer KZD per ISP-periode: totaal en behaald."""
    return _per_periode(
        _resolve_inschrijving(kzd, dip),
        perioden,
        "detail_kzd_amo",
        pl.len().alias("KZD_Aantal"),
        kzd_behaald(pl.col("Resultaat"))
        .sum()
        .cast(pl.Int64)
        .alias("KZD_AantalBehaald"),
    )


def amo_aggregaat(
    amo: pl.DataFrame,
    perioden: pl.DataFrame,
    dip: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Aggregeer AMO per ISP-periode: teller."""
    return _per_periode(
        _resolve_inschrijving(amo, dip),
        perioden,
        "detail_kzd_amo",
        pl.len().alias("AMO_Aantal"),
    )


def _bouw_detail_bpv(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """BPV volledig uitgesplitst, ``_persoon_id`` direct na ``levering``."""
    if not heeft_records(stacked, "BPV"):
        return pl.DataFrame()
    df = stacked["BPV"].drop("Recordsoort", strict=False)
    overig = [c for c in df.columns if c not in ["levering", "_persoon_id"]]
    return df.select(["levering", "_persoon_id", *overig])


def _bouw_detail_kzd_amo(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """KZD en AMO volledig; kolom ``_bron`` geeft herkomst aan.

    KZD-rijen krijgen ``Behaald`` (bool, null bij onbekend resultaat).
    """
    frames: list[pl.DataFrame] = []
    for bron in ("KZD", "AMO"):
        if heeft_records(stacked, bron):
            df = _resolve_inschrijving(stacked[bron], stacked.get("DIP"))
            df = df.drop("Recordsoort", strict=False).with_columns(
                pl.lit(bron).alias("_bron")
            )
            if bron == "KZD":
                df = df.with_columns(kzd_behaald(pl.col("Resultaat")).alias("Behaald"))
            frames.append(df)
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _bouw_detail_bekostiging(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """BII (GRONDSLAG) + TBGI-Teldatum; één rij per inschrijving × teldatum."""
    frames: list[pl.DataFrame] = []

    if heeft_records(stacked, BRON_BII):
        bii = stacked[BRON_BII].drop("Recordsoort", strict=False)
        frames.append(bii.with_columns(pl.lit(BRON_BII).alias(BRON)))

    if heeft_records(stacked, "Teldatum"):
        # _persoon_id staat al op de rij (read_tbgi erft BSN/ONr, decode
        # pseudonimiseert); het volgnummer alleen is niet uniek genoeg om de
        # persoon via de Inschrijving-tabel terug te zoeken.
        td = stacked["Teldatum"]
        frames.append(td.with_columns(pl.lit(BRON_TBGI).alias(BRON)))

    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _bid_met_dip(
    stacked: dict[str, pl.DataFrame], koppelingen: Koppelingen
) -> pl.DataFrame:
    """GRONDSLAG-BID met inschrijving, opleiding en behaaldatum van zijn DIP.

    Zonder DIP blijven die leeg: de rij wordt dan een onverklaarde wees (#258).
    """
    bid = stacked[BRON_BID].drop("Recordsoort", strict=False)
    if not heeft_records(stacked, "DIP"):
        return bid
    van_dip = stacked["DIP"].select(
        *_JOIN_DIPLOMA, *(pl.col(k).alias(v) for k, v in _BID_VAN_DIP.items())
    )
    return koppelingen.links(bid, van_dip, on=_JOIN_DIPLOMA, naam="BID.DIP")


def _bouw_detail_bekostiging_diploma(
    stacked: dict[str, pl.DataFrame], koppelingen: Koppelingen
) -> pl.DataFrame:
    """BID (GRONDSLAG) + TBGI-Diploma; één rij per inschrijving × diploma.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, Resultaatvolgnummer).
    """
    frames: list[pl.DataFrame] = []

    if heeft_records(stacked, BRON_BID):
        frames.append(
            _bid_met_dip(stacked, koppelingen).with_columns(
                pl.lit(BRON_BID).alias(BRON)
            )
        )

    if heeft_records(stacked, "Diploma"):
        diploma = stacked["Diploma"]
        frames.append(diploma.with_columns(pl.lit(BRON_TBGI).alias(BRON)))

    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def _bouw_detail_geo(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """GEO in long format.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, CodeGeneriekExamenonderdeel).

    Behoudt DatumResultaat, VrijstellingIE/CE en Onderwijsaanbieder die
    in de GEO-pivot van inschrijvingen verloren gaan.
    """
    if not heeft_records(stacked, "GEO"):
        return pl.DataFrame()
    geo = _resolve_inschrijving(stacked["GEO"], stacked.get("DIP"))
    geo = geo.drop("Recordsoort", strict=False)
    overig = [c for c in geo.columns if c not in ["levering", "_persoon_id"]]
    return geo.select(["levering", "_persoon_id", *overig])


def bouw_details(
    stacked: dict[str, pl.DataFrame], koppelingen: Koppelingen
) -> dict[str, pl.DataFrame]:
    """Alle detailtabellen, nog zonder periodekoppeling (zie
    :func:`koppel_aan_periode`); een ontbrekend recordtype geeft een lege tabel.
    """
    return {
        "detail_bpv": _bouw_detail_bpv(stacked),
        "detail_kzd_amo": _bouw_detail_kzd_amo(stacked),
        "detail_bekostiging": _bouw_detail_bekostiging(stacked),
        "detail_bekostiging_diploma": _bouw_detail_bekostiging_diploma(
            stacked, koppelingen
        ),
        "detail_geo": _bouw_detail_geo(stacked),
    }


def koppel_aan_periode(
    tabel: str, detail: pl.DataFrame, inschrijvingen: pl.DataFrame
) -> pl.DataFrame:
    """Koppel detailtabel ``tabel`` aan haar periode, met haar referentiedatum
    en koppelsleutels (inclusief terugval)."""
    return koppel_periode_id(
        detail,
        inschrijvingen,
        _PERIODE_REFERENTIEDATUM[tabel],
        _PERIODE_KOPPELSLEUTELS.get(tabel, (JOIN_INSCHRIJVING,)),
    )
