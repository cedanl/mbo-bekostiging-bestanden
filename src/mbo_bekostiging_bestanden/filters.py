"""Domeinfilters die de app-jaarselectie consistent toepassen.

De logica is app-agnostisch en leeft daarom in het package (niet in ``app/``)
zodat de UI-pagina's én de tests dezelfde selectie gebruiken.
"""

import polars as pl

_STUDIEJAAR_KOLOMMEN = ("Studiejaar_periode", "Studiejaar")
# In fact_bekostiging is "Studiejaar" afgeleid uit Teldatum (dus periode-semantiek),
# terwijl dezelfde kolomnaam in de inschrijvingsselectie het leveringjaar draagt.
# Bewust een aparte constante zónder "_periode-suffix": in het feit is er geen
# Studiejaar_periode-kolom, en het zijn twee verschillende begrippen die toevallig
# dezelfde naam delen.
_FEIT_STUDIEJAAR_KOLOM = "Studiejaar"
_SCHOOLJAAR_KOLOM = "Schooljaar"
# Koppelsleutels van detail-feiten naar fact_inschrijving, in voorkeursvolgorde:
# de periodesleutel wijst één ISP-periode aan; de inschrijvingssleutel is de
# fallback voor star-output van vóór die sleutel (en kent geen periode).
_PERIODE_SLEUTEL = ["_inschrijving_periode_id"]
_INSCHRIJVING_SLEUTEL = ["levering", "_persoon_id", "Inschrijvingvolgnummer"]


def periode_jaar_kolom(df: pl.DataFrame) -> str | None:
    """Jaarkolom die de periode-semantiek draagt.

    ``Studiejaar_periode`` (afgeleid uit datum) heeft voorrang als die aanwezig is;
    anders valt het terug op ``Studiejaar`` (backward-compat).  ``None`` wanneer
    geen van beide kolommen aanwezig is.
    """
    for naam in _STUDIEJAAR_KOLOMMEN:
        if naam in df.columns:
            return naam
    return None


def _filter_op_selectiejaren(
    feit: pl.DataFrame, jaar_kolom: str, geselecteerde_inschrijvingen: pl.DataFrame
) -> pl.DataFrame:
    """Beperk ``feit`` tot de jaren die in de inschrijvingsselectie voorkomen.

    De selectie draagt haar jaren in ``Studiejaar_periode`` (fallback
    ``Studiejaar``). Is daar niets uit af te leiden, dan is het resultaat leeg
    in plaats van de volledige feitentabel.
    """
    if jaar_kolom not in feit.columns:
        return feit
    selectie_kolom = periode_jaar_kolom(geselecteerde_inschrijvingen)
    if selectie_kolom is None:
        return feit.clear()
    jaren = geselecteerde_inschrijvingen[selectie_kolom].drop_nulls().unique()
    return feit.filter(pl.col(jaar_kolom).is_in(jaren.to_list()))


def filter_fact_bekostiging_op_jaar(
    fact_bekostiging: pl.DataFrame,
    geselecteerde_inschrijvingen: pl.DataFrame,
) -> pl.DataFrame:
    """Filter ``fact_bekostiging`` op de geselecteerde periodestudiejaren.

    TBGI-bekostiging (h16) overlapt qua ``levering`` niet met de ISP-leveringen,
    waardoor een FK-join via (levering, _persoon_id, Inschrijvingvolgnummer) de
    TBGI-rijen weglaat.  Daarom filteren we op het uit ``Teldatum`` afgeleide
    jaartal in ``fact_bekostiging``.
    """
    return _filter_op_selectiejaren(
        fact_bekostiging, _FEIT_STUDIEJAAR_KOLOM, geselecteerde_inschrijvingen
    )


def filter_schooljaren_op_jaar(
    jaren: pl.DataFrame, geselecteerde_inschrijvingen: pl.DataFrame
) -> pl.DataFrame:
    """Filter ``fact_inschrijving_schooljaar`` op de geselecteerde studiejaren.

    Schooljaar *t* en studiejaar *t* zijn hetzelfde jaar (1-8-t t/m 31-7-(t+1)).
    """
    return _filter_op_selectiejaren(
        jaren, _SCHOOLJAAR_KOLOM, geselecteerde_inschrijvingen
    )


def _koppelsleutel(
    detail: pl.DataFrame, inschrijvingen: pl.DataFrame
) -> list[str] | None:
    """Eerste koppelsleutel die in beide tabellen staat, of ``None``."""
    gedeeld = set(detail.columns) & set(inschrijvingen.columns)
    return next(
        (s for s in (_PERIODE_SLEUTEL, _INSCHRIJVING_SLEUTEL) if set(s) <= gedeeld),
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
