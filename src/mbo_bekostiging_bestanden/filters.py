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
    if _FEIT_STUDIEJAAR_KOLOM not in fact_bekostiging.columns:
        return fact_bekostiging
    jaar_kolom = periode_jaar_kolom(geselecteerde_inschrijvingen)
    if jaar_kolom is None:
        # Kan niet worden afgeleid met welke jaren de selectie overeenkomt: toon
        # niets in plaats van de volledige (TBGI-)feitentabel als fallback.
        return fact_bekostiging.clear()
    jaren = geselecteerde_inschrijvingen[jaar_kolom].drop_nulls().unique().to_list()
    if not jaren:
        return fact_bekostiging.clear()
    return fact_bekostiging.filter(pl.col(_FEIT_STUDIEJAAR_KOLOM).is_in(jaren))
