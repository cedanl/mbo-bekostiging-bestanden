"""Centrale inschrijvingstabel: ISP-perioden, aangevuld met TBGI-inschrijvingen.

Eén rij per ISP-periode (RO/GRONDSLAG) of per TBGI-inschrijving zonder ISP
(#196), plat gemaakt met alle recordtypes per inschrijving: PER, ISG, VLP,
ISE, DIP, een dynamische GEO-pivot en BPV/KZD/AMO geaggregeerd per periode.
"""

import polars as pl

from mbo_bekostiging_bestanden.contracts import (
    BRON,
    BRON_TBGI,
    JOIN_INSCHRIJVING,
    JOIN_INSTELLING_INSCHRIJVING,
    JOIN_PERSOON,
    PERIODE_ID,
)
from mbo_bekostiging_bestanden.details import (
    amo_aggregaat,
    bpv_aggregaat,
    geo_pivot,
    kzd_aggregaat,
)
from mbo_bekostiging_bestanden.identiteit import PERSOON_COLS, voeg_persoon_id_toe
from mbo_bekostiging_bestanden.koppelingen import Koppelingen
from mbo_bekostiging_bestanden.metadata import alle_extra_kolommen
from mbo_bekostiging_bestanden.opleidingsniveau import vul_niveau_aan
from mbo_bekostiging_bestanden.perioden import leid_studiejaar_af, voeg_periode_id_toe
from mbo_bekostiging_bestanden.stack import heeft_records

_ISG_KOLOMMEN = (
    "DatumInschrijving",
    "DatumUitschrijvingGepland",
    "DatumUitschrijvingWerkelijk",
    "RedenUitschrijving",
)
# Kolommen die bij ISE/DIP niet als ``<recordtype>_<kolom>`` meekomen.
_NIET_OVERNEMEN = (*JOIN_INSCHRIJVING, *PERSOON_COLS, "Recordsoort")


def isp_met_instelling(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """ISP met ``_persoon_id`` en ``BRIN``; RO-ISP krijgt BRIN uit het VLP-record."""
    isp = voeg_persoon_id_toe(stacked["ISP"]).drop("Recordsoort", strict=False)
    vlp = stacked.get("VLP", pl.DataFrame())
    if "BRIN" not in vlp.columns:
        return isp
    isp = isp.join(
        vlp.select("levering", pl.col("BRIN").alias("_brin_vlp")).unique("levering"),
        on="levering",
        how="left",
    )
    brin = ["BRIN", "_brin_vlp"] if "BRIN" in isp.columns else ["_brin_vlp"]
    return isp.with_columns(pl.coalesce(brin).alias("BRIN")).drop("_brin_vlp")


def _met_prefix(records: pl.DataFrame, prefix: str, *uitsluiten: str) -> pl.DataFrame:
    """Inschrijvingssleutel plus de overige kolommen als ``<prefix>_<kolom>``."""
    records = voeg_persoon_id_toe(records)
    extra = [c for c in records.columns if c not in {*_NIET_OVERNEMEN, *uitsluiten}]
    return records.select([*JOIN_INSCHRIJVING, *extra]).rename(
        {c: f"{prefix}_{c}" for c in extra}
    )


def _koppel_persoon_en_levering(
    df: pl.DataFrame, stacked: dict[str, pl.DataFrame], koppelingen: Koppelingen
) -> pl.DataFrame:
    """PER (persoonskenmerken), ISG (inschrijvingsdatums) en VLP (bestand)."""
    # Posities buiten het PvE horen bij de brondata, niet bij het model (#260).
    per = voeg_persoon_id_toe(stacked["PER"]).drop(
        "Recordsoort", *PERSOON_COLS, *alle_extra_kolommen(), strict=False
    )
    df = koppelingen.links(df, per, on=JOIN_PERSOON, naam="PER")

    isg = voeg_persoon_id_toe(stacked["ISG"])
    isg_kolommen = [c for c in _ISG_KOLOMMEN if c in isg.columns]
    df = koppelingen.links(
        df,
        isg.select([*JOIN_INSCHRIJVING, *isg_kolommen]),
        on=JOIN_INSCHRIJVING,
        naam="ISG",
    )

    # BRIN staat al op de ISP (isp_met_instelling).
    vlp = stacked["VLP"].drop("Recordsoort", "BRIN", strict=False)
    return koppelingen.links(df, vlp, on=["levering"], naam="VLP", suffix="_vlp")


def _koppel_ise_en_dip(
    df: pl.DataFrame, stacked: dict[str, pl.DataFrame], koppelingen: Koppelingen
) -> pl.DataFrame:
    """ISE (extra ondersteuning) en DIP (diploma): elk 0-1 per inschrijving."""
    if heeft_records(stacked, "ISE"):
        df = koppelingen.links(
            df, _met_prefix(stacked["ISE"], "ISE"), on=JOIN_INSCHRIJVING, naam="ISE"
        )
    if heeft_records(stacked, "DIP"):
        dip = _met_prefix(stacked["DIP"], "DIP", "_onbekend", "BRIN")
        df = koppelingen.links(df, dip, on=JOIN_INSCHRIJVING, naam="DIP")
    return df


def _koppel_resultaten(
    df: pl.DataFrame,
    stacked: dict[str, pl.DataFrame],
    perioden: pl.DataFrame,
    koppelingen: Koppelingen,
) -> pl.DataFrame:
    """GEO gepivoteerd per inschrijving; BPV/KZD/AMO geaggregeerd per periode.

    Per periode, zodat een inschrijving met meerdere perioden haar aantallen
    niet herhaalt (#105). DIP vult het ontbrekende ``Inschrijvingvolgnummer``
    van GEO/KZD/AMO aan.
    """
    dip = stacked.get("DIP")

    if heeft_records(stacked, "GEO"):
        pivot = geo_pivot(stacked["GEO"], dip=dip)
        if pivot is not None:
            df = koppelingen.links(df, pivot, on=JOIN_INSCHRIJVING, naam="GEO")

    aggregaten = {
        "BPV": lambda bpv: bpv_aggregaat(bpv, perioden),
        "KZD": lambda kzd: kzd_aggregaat(kzd, perioden, dip=dip),
        "AMO": lambda amo: amo_aggregaat(amo, perioden, dip=dip),
    }
    for recordtype, aggregaat in aggregaten.items():
        if heeft_records(stacked, recordtype):
            df = df.join(aggregaat(stacked[recordtype]), on=PERIODE_ID, how="left")
    return df


def _voeg_afgeleide_velden_toe(df: pl.DataFrame) -> pl.DataFrame:
    """``Niveau_gecombineerd``: ``"MBO-4 BOL"`` — concat van Niveau en Leertraject."""
    if "Niveau" in df.columns and "Leertraject" in df.columns:
        df = df.with_columns(
            pl.concat_str(
                [pl.col("Niveau"), pl.col("Leertraject")],
                separator=" ",
                ignore_nulls=False,
            ).alias("Niveau_gecombineerd")
        )
    return df


def _verrijk(df: pl.DataFrame) -> pl.DataFrame:
    """Studiejaar, niveau en afgeleide velden; ISP en TBGI gelijk.

    Jaargebonden vlaggen horen hier niet: die staan alleen op de schooljaar-grain
    (``schooljaar.py``, #201).
    """
    df = leid_studiejaar_af(df)
    df = vul_niveau_aan(df)
    return _voeg_afgeleide_velden_toe(df)


def bouw_inschrijvingen(
    stacked: dict[str, pl.DataFrame], isp: pl.DataFrame, koppelingen: Koppelingen
) -> pl.DataFrame:
    """ISP-grain: alle record-types samengevoegd tot één platte analysetabel.

    Args:
        stacked:     Gestapelde genormaliseerde records.
        isp:         Canonieke ISP-rijen uit :func:`isp_met_instelling`; ISG,
                     DIP, BPV e.d. worden alleen aan deze inschrijvingen gekoppeld.
        koppelingen: Voert de links-joins uit en houdt meervoudige matches bij.
    """
    df = voeg_periode_id_toe(isp)
    perioden = df.select([*JOIN_INSCHRIJVING, "DatumBegin", PERIODE_ID])
    df = _koppel_persoon_en_levering(df, stacked, koppelingen)
    df = _koppel_ise_en_dip(df, stacked, koppelingen)
    df = _koppel_resultaten(df, stacked, perioden, koppelingen)
    return _verrijk(df)


def _bouw_tbgi_inschrijvingen(stacked: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Inschrijving-grain voor TBGI-only input (geen ISP beschikbaar).

    Gebruikt TBGI Inschrijving als vervanging voor ISP; elke inschrijving
    krijgt hier een pseudo-periode vanaf ``DatumInschrijving`` (alleen om
    dezelfde ``_inschrijving_periode_id`` te krijgen als in de ISP-route).
    Dat is géén schooljaar-lidmaatschap: welk schooljaar een TBGI-inschrijving
    telt, bepaalt ``schooljaar.py`` via ``Teldatum`` (#197), niet via deze
    ``DatumInschrijving``-periode. Verander deze pseudo-periode niet in de
    veronderstelling dat hij het schooljaar bepaalt.
    """
    inschrijving = voeg_persoon_id_toe(stacked["Inschrijving"])
    return _verrijk(voeg_periode_id_toe(inschrijving.drop("Recordsoort", strict=False)))


def tbgi_zonder_isp(
    stacked: dict[str, pl.DataFrame], isp_inschrijvingen: pl.DataFrame
) -> pl.DataFrame:
    """TBGI-inschrijvingen die niet al als ISP-periode bestaan (#196).

    Een inschrijving met ISP-perioden (RO/GRONDSLAG) is rijker dan haar
    TBGI-weergave en blijft de parent; TBGI vult alleen aan wat ontbreekt,
    bijv. een student die niet in de meegeleverde RO-bestanden staat.
    """
    tbgi = _bouw_tbgi_inschrijvingen(stacked).with_columns(
        pl.lit(BRON_TBGI).alias(BRON)
    )
    if isp_inschrijvingen.is_empty():
        return tbgi
    return tbgi.join(
        isp_inschrijvingen.select(JOIN_INSTELLING_INSCHRIJVING).unique(),
        on=JOIN_INSTELLING_INSCHRIJVING,
        how="anti",
        nulls_equal=True,
    )
