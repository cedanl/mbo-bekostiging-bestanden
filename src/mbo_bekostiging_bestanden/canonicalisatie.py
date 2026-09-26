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
REDEN = "_reden"
# Waarom de winnende levering is gekozen (lineage in meta_canonicalisatie).
REDEN_AANMAAKDATUM = "recentere_aanmaakdatum"
REDEN_LEVERINGSNAAM = "leveringsnaam"
# Voorkeursregel in leesbare vorm, voor quality.json.
REGEL = (
    "Per inschrijving (BRIN × _persoon_id × Inschrijvingvolgnummer) wint de "
    "levering met de hoogste VLP-DatumAanmaak; bij gelijke of ontbrekende "
    "aanmaakdatum de alfabetisch laatste leveringsnaam."
)
OVERZICHT_KOLOMMEN = pl.Schema(
    {
        "levering": pl.Utf8,
        "vervangen_door": pl.Utf8,
        "reden": pl.Utf8,
        "inschrijvingen": pl.UInt32,
        "isp_perioden": pl.UInt32,
    }
)


def vervangen_inschrijvingen(isp: pl.DataFrame, vlp: pl.DataFrame) -> pl.DataFrame:
    """Inschrijvingen waarvoor een recentere levering bestaat.

    Args:
        isp: Rijen met minimaal ``levering``, ``BRIN``, ``_persoon_id`` en
             ``Inschrijvingvolgnummer`` (meerdere perioden per inschrijving
             mogen).
        vlp: Eén rij per levering met ``levering`` en ``DatumAanmaak``.

    Returns:
        Eén rij per vervangen inschrijving: ``levering``, ``_persoon_id``,
        ``Inschrijvingvolgnummer``, ``_vervangen_door`` (winnende levering) en
        ``_reden`` (:data:`REDEN_AANMAAKDATUM` of :data:`REDEN_LEVERINGSNAAM`).
    """
    if not set(INSCHRIJVING) <= set(isp.columns):
        return pl.DataFrame(schema=[*INSCHRIJVING_IN_LEVERING, VERVANGEN_DOOR, REDEN])
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
    aanmaak_winnaar = aanmaak.rename(
        {LEVERING: VERVANGEN_DOOR, "DatumAanmaak": "_aanmaak_winnaar"}
    )
    return (
        voorkomens.join(recentst, on=INSCHRIJVING)
        .filter(pl.col(LEVERING) != pl.col(VERVANGEN_DOOR))
        .join(aanmaak_winnaar, on=VERVANGEN_DOOR, how="left")
        .with_columns(
            pl.when(pl.col("_aanmaak_winnaar") > pl.col("DatumAanmaak"))
            .then(pl.lit(REDEN_AANMAAKDATUM))
            .otherwise(pl.lit(REDEN_LEVERINGSNAAM))
            .alias(REDEN)
        )
        .select(*INSCHRIJVING_IN_LEVERING, VERVANGEN_DOOR, REDEN)
    )


def canonicalisatie_overzicht(
    isp: pl.DataFrame, vervangen: pl.DataFrame
) -> pl.DataFrame:
    """Lineage per leveringspaar: wat is vervangen, door welke levering en waarom.

    Args:
        isp:       ISP-rijen vóór canonicalisatie (één rij per periode).
        vervangen: Output van :func:`vervangen_inschrijvingen`.

    Returns:
        Eén rij per (levering, vervangen_door, reden) met het aantal vervangen
        inschrijvingen en ISP-perioden; leeg (met vast schema) zonder overlap.
    """
    if vervangen.is_empty():
        return pl.DataFrame(schema=OVERZICHT_KOLOMMEN)
    perioden = isp.join(vervangen, on=INSCHRIJVING_IN_LEVERING, how="semi")
    per_inschrijving = vervangen.join(
        perioden.group_by(INSCHRIJVING_IN_LEVERING).len("_perioden"),
        on=INSCHRIJVING_IN_LEVERING,
        how="left",
    )
    return (
        per_inschrijving.group_by(LEVERING, VERVANGEN_DOOR, REDEN)
        .agg(
            pl.len().alias("inschrijvingen"),
            pl.col("_perioden").sum().alias("isp_perioden"),
        )
        .rename({VERVANGEN_DOOR: "vervangen_door", REDEN: "reden"})
        .sort(LEVERING, "vervangen_door")
        .cast(OVERZICHT_KOLOMMEN)
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
