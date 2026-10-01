"""Domeinfilters die de app-jaarselectie consistent toepassen.

De logica is app-agnostisch en leeft daarom in het package (niet in ``app/``)
zodat de UI-pagina's én de tests dezelfde selectie gebruiken.

Eén jaarselector, elk feit met zijn eigen jaarbetekenis (#240): ``Schooljaar``
in de schooljaar-fact, het schooljaar van ``Teldatum`` in de bekostiging.
Eén kolom voor leveringsjaar, periodejaar en observatiejaar samen liet
TBGI-only jaren wegvallen.
"""

import polars as pl

from mbo_bekostiging_bestanden.contracts import (
    PERIODE_ID,
    PERIODE_SLEUTEL,
    STUDIEJAAR_START_MAAND,
    TELDATUM_DAG,
    TELDATUM_MAAND,
)

_SCHOOLJAAR = "Schooljaar"
_TELDATUM = "Teldatum"
# Schooljaar waarin een ISP-periode begint (perioden.leid_studiejaar_af).
_PERIODE_JAAR = "Studiejaar_periode"
# Koppelsleutels van detail-feiten naar fact_inschrijving, in voorkeursvolgorde:
# de periodesleutel wijst één ISP-periode aan; de inschrijvingssleutel is de
# fallback voor star-output van vóór die sleutel (en kent geen periode).
_INSCHRIJVING_SLEUTEL = ("levering", "_persoon_id", "Inschrijvingvolgnummer")


def schooljaar_van(datum: pl.Expr) -> pl.Expr:
    """Schooljaar *t* loopt van 1-8-t t/m 31-7-(t+1)."""
    datum = datum.cast(pl.Date, strict=False)
    return datum.dt.year() - (datum.dt.month() < STUDIEJAAR_START_MAAND).cast(pl.Int32)


def peildatum(schooljaar: pl.Expr) -> pl.Expr:
    """1 oktober van ``schooljaar``: de teldatum van de bekostiging."""
    return pl.date(schooljaar, TELDATUM_MAAND, TELDATUM_DAG)


def beschikbare_schooljaren(
    jaren: pl.DataFrame, fact_bekostiging: pl.DataFrame
) -> list[int]:
    """Schooljaren in de schooljaar-fact of in de teldata van de bekostiging."""
    reeksen = []
    if _SCHOOLJAAR in jaren.columns:
        reeksen.append(jaren[_SCHOOLJAAR].cast(pl.Int64))
    if _TELDATUM in fact_bekostiging.columns:
        reeksen.append(
            fact_bekostiging.select(schooljaar_van(pl.col(_TELDATUM)))
            .to_series()
            .cast(pl.Int64)
        )
    if not reeksen:
        return []
    return sorted(pl.concat(reeksen).drop_nulls().unique().to_list())


def filter_op_schooljaren(feit: pl.DataFrame, geselecteerd: list[int]) -> pl.DataFrame:
    """Rijen van ``feit`` (met ``Schooljaar``) in de geselecteerde schooljaren."""
    if _SCHOOLJAAR not in feit.columns:
        return feit.clear()
    return feit.filter(pl.col(_SCHOOLJAAR).is_in(geselecteerd))


def filter_bekostiging_op_schooljaren(
    fact_bekostiging: pl.DataFrame, geselecteerd: list[int]
) -> pl.DataFrame:
    """Bekostigingsrijen waarvan de ``Teldatum`` in een geselecteerd schooljaar valt.

    TBGI-bekostiging deelt geen ``levering`` met de ISP-perioden; een join via
    de inschrijving zou haar rijen weglaten.
    """
    if _TELDATUM not in fact_bekostiging.columns:
        return fact_bekostiging.clear()
    return fact_bekostiging.filter(
        schooljaar_van(pl.col(_TELDATUM)).is_in(geselecteerd)
    )


def filter_perioden_op_schooljaren(
    perioden: pl.DataFrame, jaren: pl.DataFrame, geselecteerd: list[int]
) -> pl.DataFrame:
    """Perioden die in een geselecteerd schooljaar beginnen óf er op 1 oktober
    actief zijn (volgens ``jaren``, de schooljaar-fact).

    Het beginjaar alleen mist een TBGI-pseudo-periode (begin = inschrijving,
    telt in het jaar van haar teldatum, #197) en perioden over meerdere jaren;
    1 oktober alleen mist korte perioden die geen peildatum dekken.
    """
    actief = filter_op_schooljaren(jaren, geselecteerd)
    begint = (
        pl.col(_PERIODE_JAAR).is_in(geselecteerd)
        if _PERIODE_JAAR in perioden.columns
        else pl.lit(False)
    )
    if PERIODE_ID in actief.columns and PERIODE_ID in perioden.columns:
        begint = begint | pl.col(PERIODE_ID).is_in(
            actief[PERIODE_ID].drop_nulls().implode()
        )
    return perioden.filter(begint)


def _koppelsleutel(
    detail: pl.DataFrame, inschrijvingen: pl.DataFrame
) -> tuple[str, ...] | None:
    """Eerste koppelsleutel die in beide tabellen staat, of ``None``."""
    gedeeld = set(detail.columns) & set(inschrijvingen.columns)
    return next(
        (s for s in (PERIODE_SLEUTEL, _INSCHRIJVING_SLEUTEL) if set(s) <= gedeeld),
        None,
    )


def filter_detail_op_inschrijvingen(
    detail: pl.DataFrame,
    geselecteerde_inschrijvingen: pl.DataFrame,
) -> pl.DataFrame:
    """Beperk een detail-feit tot de rijen van de geselecteerde inschrijvingen.

    Koppelt via ``_inschrijving_periode_id`` zodat alleen detailrijen uit de
    geselecteerde ISP-perioden overblijven; ontbreekt die sleutel, dan via
    (levering, _persoon_id, Inschrijvingvolgnummer).  Een semi-join, dus nooit
    fan-out.  Zonder gedeelde sleutel of zonder selectie is het resultaat leeg.
    """
    sleutel = _koppelsleutel(detail, geselecteerde_inschrijvingen)
    if sleutel is None:
        return detail.clear()
    return detail.join(geselecteerde_inschrijvingen, on=sleutel, how="semi")


def detail_zonder_inschrijving(
    detail: pl.DataFrame, inschrijvingen: pl.DataFrame
) -> pl.DataFrame:
    """Tegenhanger van :func:`filter_detail_op_inschrijvingen`: de wees-rijen."""
    sleutel = _koppelsleutel(detail, inschrijvingen)
    if sleutel is None:
        return detail
    return detail.join(inschrijvingen, on=sleutel, how="anti")
