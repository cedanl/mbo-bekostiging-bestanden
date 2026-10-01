"""Interne analysetabellen vanuit gestapelde genormaliseerde records.

Alleen orkestratie; de logica staat per domein in ``identiteit``,
``perioden``, ``inschrijvingen``, ``periodevlaggen``, ``opleidingsniveau`` en
``details``. Output (nul informatieverlies):

  inschrijvingen      ISP-grain, alles flat + dynamische GEO-pivot +
                      BPV/KZD/AMO geaggregeerd per ISP-periode
  detail_bpv          BPV volledig uitgesplitst
  detail_kzd_amo      KZD en AMO volledig, kolom _bron geeft herkomst aan
  detail_bekostiging  BII (GRONDSLAG) + TBGI-Teldatum per
                      inschrijving × teldatum
  detail_bekostiging_diploma  BID (GRONDSLAG) + TBGI-Diploma per
                      inschrijving × diploma
  detail_geo          GEO in long format, grain: inschrijving × onderdeel
  meta_leveringen     VLP + SLR per bronbestand
  meta_canonicalisatie, meta_koppelkeuzes  verantwoording van keuzes
"""

import polars as pl

from mbo_bekostiging_bestanden.canonicalisatie import (
    canonicalisatie_overzicht,
    vervangen_inschrijvingen,
    verwijder_vervangen,
)
from mbo_bekostiging_bestanden.contracts import BRON, BRON_ISP
from mbo_bekostiging_bestanden.details import bouw_details, koppel_aan_periode
from mbo_bekostiging_bestanden.enrich import enrich_inschrijvingen
from mbo_bekostiging_bestanden.inschrijvingen import (
    bouw_inschrijvingen,
    isp_met_instelling,
    tbgi_zonder_isp,
)
from mbo_bekostiging_bestanden.koppelingen import Koppelingen
from mbo_bekostiging_bestanden.stack import heeft_records


def _bouw_meta_leveringen(
    stacked: dict[str, pl.DataFrame], koppelingen: Koppelingen
) -> pl.DataFrame:
    """Eén rij per gestapelde levering, met VLP + SLR waar die bestaan.

    Elke levering die in een tabel voorkomt staat erin, ook zonder VLP/SLR
    (TBGI-XML); die velden blijven dan leeg (#188).
    """
    leveringen = [
        df.select("levering") for df in stacked.values() if "levering" in df.columns
    ]
    if not leveringen:
        return pl.DataFrame()
    meta = pl.concat(leveringen).unique().sort("levering")
    for recordtype in ("VLP", "SLR"):
        records = stacked.get(recordtype, pl.DataFrame()).drop(
            "Recordsoort", strict=False
        )
        if "levering" in records.columns:
            meta = koppelingen.links(
                meta, records, on=["levering"], naam=f"meta_leveringen.{recordtype}"
            )
    return meta


def bouw_analysetabellen(stacked: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Bouw de analysetabellen vanuit gestapelde genormaliseerde records.

    Args:
        stacked: Output van :func:`~mbo_bekostiging_bestanden.stack.stack_prepared`,
                 dict van tabelnaam → DataFrame.

    Returns:
        Dict met ``inschrijvingen``, ``detail_bpv``, ``detail_kzd_amo``,
        ``detail_bekostiging``, ``detail_bekostiging_diploma``, ``detail_geo``,
        ``meta_leveringen``, ``meta_canonicalisatie`` en ``meta_koppelkeuzes``.
    """
    heeft_isp = heeft_records(stacked, "ISP")
    heeft_inschrijving = heeft_records(stacked, "Inschrijving")

    if not heeft_isp and not heeft_inschrijving:
        raise ValueError(
            "Gestapelde data bevat geen ISP- of Inschrijving-records; "
            "analysetabellen kunnen niet worden gebouwd."
        )

    koppelingen = Koppelingen()
    # Canonicalisatie vóór alle indicatoren: per inschrijving telt alleen de
    # meest recente levering, ook in de detailfeiten (#134, #174).
    if heeft_isp:
        isp = isp_met_instelling(stacked)
        vervangen = vervangen_inschrijvingen(isp, stacked.get("VLP", pl.DataFrame()))
        inschrijvingen = bouw_inschrijvingen(
            stacked, verwijder_vervangen(isp, vervangen), koppelingen
        ).with_columns(pl.lit(BRON_ISP).alias(BRON))
        overzicht = canonicalisatie_overzicht(isp, vervangen)
    else:
        inschrijvingen = pl.DataFrame()
        vervangen = pl.DataFrame()
        overzicht = canonicalisatie_overzicht(pl.DataFrame(), vervangen)
    if heeft_inschrijving:
        inschrijvingen = pl.concat(
            [inschrijvingen, tbgi_zonder_isp(stacked, inschrijvingen)],
            how="diagonal_relaxed",
        )
    inschrijvingen = enrich_inschrijvingen(inschrijvingen)
    details = {
        naam: koppel_aan_periode(
            naam, verwijder_vervangen(detail, vervangen), inschrijvingen
        )
        for naam, detail in bouw_details(stacked, koppelingen).items()
    }
    return {
        "inschrijvingen": inschrijvingen,
        **details,
        "meta_leveringen": _bouw_meta_leveringen(stacked, koppelingen),
        "meta_canonicalisatie": overzicht,
        "meta_koppelkeuzes": koppelingen.overzicht(),
    }
