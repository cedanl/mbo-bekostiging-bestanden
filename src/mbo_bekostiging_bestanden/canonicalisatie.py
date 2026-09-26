"""Canonicalisatie van overlappende leveringen (#134, #174).

Een levering is een bronbestand, geen tellingseenheid. Dezelfde inschrijving
kan in meerdere leveringen staan (correctie, herlevering, overlappende
periode). Per inschrijving telt alleen de meest recente levering; alle rijen
van die inschrijving uit oudere leveringen vallen weg — in ISP én in de
detailfeiten, zodat detailrijen altijd bij de gekozen levering horen.

Een inschrijving is ``(BRIN, _persoon_id, Inschrijvingvolgnummer)``:

- ``BRIN`` omdat een inschrijvingvolgnummer niet instellingsoverstijgend
  uniek is;
- ``_persoon_id`` draagt het identifierdomein (PGN/BSN/ONR, #128), dus
  RO- en GRONDSLAG-leveringen worden nooit met elkaar samengevoegd.

Recentheid volgt ``DatumAanmaak`` uit het VLP-record van de levering; bij
gelijke of ontbrekende aanmaakdatum beslist de leveringsnaam. Rijen zonder
volledige inschrijvingssleutel worden niet gecanonicaliseerd: zonder BRIN of
volgnummer is niet vast te stellen dat twee rijen dezelfde inschrijving zijn.
"""

import polars as pl

LEVERING = "levering"
# Sleutel van een inschrijving binnen één levering; een levering hoort bij één
# instelling (VLP), dus BRIN is hierin impliciet.
INSCHRIJVING_IN_LEVERING = [LEVERING, "_persoon_id", "Inschrijvingvolgnummer"]
# Sleutel van een inschrijving over leveringen heen.
INSCHRIJVING = ["BRIN", "_persoon_id", "Inschrijvingvolgnummer"]
# Recentheid van een levering, in voorkeursvolgorde (hoogste wint).
_RECENTHEID = ["DatumAanmaak", LEVERING]
VERVANGEN_DOOR = "_vervangen_door"


def vervangen_inschrijvingen(isp: pl.DataFrame, vlp: pl.DataFrame) -> pl.DataFrame:
    """Inschrijvingen waarvoor een recentere levering bestaat.

    Args:
        isp: Rijen met minimaal ``levering``, ``BRIN``, ``_persoon_id`` en
             ``Inschrijvingvolgnummer`` (meerdere perioden per inschrijving
             mogen).
        vlp: Eén rij per levering met ``levering`` en ``DatumAanmaak``.

    Returns:
        Eén rij per vervangen inschrijving: ``levering``, ``_persoon_id``,
        ``Inschrijvingvolgnummer`` en ``_vervangen_door`` (winnende levering).
    """
    if not set(INSCHRIJVING) <= set(isp.columns):
        return pl.DataFrame(schema=[*INSCHRIJVING_IN_LEVERING, VERVANGEN_DOOR])
    aanmaak = (
        vlp.select(LEVERING, "DatumAanmaak").unique(LEVERING)
        if {LEVERING, "DatumAanmaak"} <= set(vlp.columns)
        else pl.DataFrame(schema={LEVERING: pl.Utf8, "DatumAanmaak": pl.Date})
    )
    voorkomens = (
        isp.select(LEVERING, *INSCHRIJVING)
        .drop_nulls(INSCHRIJVING)
        .unique()
        .join(aanmaak, on=LEVERING, how="left")
    )
    recentst = (
        voorkomens.sort(_RECENTHEID, descending=True, nulls_last=True)
        .group_by(INSCHRIJVING, maintain_order=True)
        .agg(pl.col(LEVERING).first().alias(VERVANGEN_DOOR))
    )
    return (
        voorkomens.join(recentst, on=INSCHRIJVING)
        .filter(pl.col(LEVERING) != pl.col(VERVANGEN_DOOR))
        .select(*INSCHRIJVING_IN_LEVERING, VERVANGEN_DOOR)
    )


def verwijder_vervangen(df: pl.DataFrame, vervangen: pl.DataFrame) -> pl.DataFrame:
    """Verwijder de rijen van vervangen inschrijvingen uit ``df``.

    Tabellen zonder inschrijvingssleutel (bijv. levering-metadata) blijven
    ongewijzigd. Rijen uit leveringen die niet in ``vervangen`` voorkomen
    (zoals TBGI) worden nooit geraakt.
    """
    if vervangen.is_empty() or not set(INSCHRIJVING_IN_LEVERING) <= set(df.columns):
        return df
    return df.join(
        vervangen.select(INSCHRIJVING_IN_LEVERING),
        on=INSCHRIJVING_IN_LEVERING,
        how="anti",
    )
