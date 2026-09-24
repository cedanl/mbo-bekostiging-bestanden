"""Domeinfilters die de app-jaarselectie consistent toepassen.

De logica is app-agnostisch en leeft daarom in het package (niet in ``app/``)
zodat de UI-pagina's én de tests dezelfde selectie gebruiken.
"""

import polars as pl

_STUDIEJAAR_KOLOMMEN = ("Studiejaar_periode", "Studiejaar")


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


def filter_fact_bekostiging_op_jaar(
    fact_bekostiging: pl.DataFrame,
    geselecteerde_inschrijvingen: pl.DataFrame,
) -> pl.DataFrame:
    """Filter ``fact_bekostiging`` op de geselecteerde periodestudiejaren.

    TBGI-bekostiging (h16) overlapt qua ``levering`` niet met de ISP-leveringen,
    waardoor een FK-join via (levering, _persoon_id, Inschrijvingvolgnummer) de
    TBGI-rijen weglaat.  Daarom filteren we op het uit ``Teldatum`` afgeleide
    jaartal in ``fact_bekostiging``, vergeleken met dezelfde jaarkolom als de
    sidebar-selectie (``Studiejaar_periode``, fallback ``Studiejaar``).
    """
    if "Studiejaar" not in fact_bekostiging.columns:
        return fact_bekostiging
    jaar_kolom = periode_jaar_kolom(geselecteerde_inschrijvingen)
    if jaar_kolom is None:
        return fact_bekostiging.clear()
    jaren = geselecteerde_inschrijvingen[jaar_kolom].drop_nulls().unique().to_list()
    if not jaren:
        return fact_bekostiging.clear()
    return fact_bekostiging.filter(pl.col("Studiejaar").is_in(jaren))