"""Kolomnamen, codes en grains die de sterbouw schrijft en ``quality`` leest.

Afhankelijkheidsloos, zodat ``quality.py`` de ster kan beoordelen zonder de
code te importeren die hem bouwt (#365, ``docs/architectuur.md``). Zelfde
patroon als ``niveau.py`` en ``ernst.py``.
"""

# DUO-kalender: telling op 1 oktober, studiejaar van 1 augustus t/m 31 juli.
TELDATUM_MAAND = 10
TELDATUM_DAG = 1
STUDIEJAAR_START_MAAND = 8
STUDIEJAAR_START_DAG = 1
STUDIEJAAR_EIND_MAAND = 7
STUDIEJAAR_EIND_DAG = 31

# Eén ISP-periode (of TBGI-inschrijving zonder ISP) in fact_inschrijving; elk
# detailfeit wijst er via deze sleutel naartoe zonder fan-out.
PERIODE_ID = "_inschrijving_periode_id"
PERIODE_SLEUTEL = (PERIODE_ID,)

# Herkomst van een rij in de centrale inschrijvingstabel (#196): een ISP-periode
# (RO/GRONDSLAG) of een TBGI-inschrijving zonder ISP-perioden. In de
# bekostigingsfeiten het recordtype waar de rij vandaan komt (BII/BID/TBGI).
BRON = "Bron"
BRON_ISP = "ISP"
BRON_TBGI = "TBGI"
BRON_BII = "BII"
BRON_BID = "BID"

# Waarom een detailrij aan haar periode hangt (#121). Alleen binnen_periode is
# de periode waarin de referentiedatum valt; datum_leeg, voor_eerste_periode en
# geen_datumkolom vallen terug op de eerste periode van de inschrijving.
KOPPELSTATUS = "_periode_koppel_status"
KOPPELSTATUS_BINNEN = "binnen_periode"
KOPPELSTATUS_GEEN_INSCHRIJVING = "geen_inschrijving"
KOPPELSTATUSSEN = (
    KOPPELSTATUS_BINNEN,
    "datum_leeg",
    "voor_eerste_periode",
    "geen_datumkolom",
    KOPPELSTATUS_GEEN_INSCHRIJVING,
)

# Jaargebonden vlaggen op periode-grain: verouderd sinds fact_inschrijving_schooljaar
# (#164). Migratiepad (#201): een release markeert ze, de major daarna verwijdert ze.
VEROUDERD_TOT = "v4.0.0"
VEROUDERDE_KOLOMMEN = (
    "_actief_1_oktober",
    "_bekostigd_eerste_1okt",
    "_gediplomeerd_in_jaar",
    "_ingeschreven_jaar_later",
    "_deelnemer_niet_bekostigd_eerste_1okt",
    "_hoogste_niveau",
    "_laagste_CREBO",
    "_hoofdinschrijving",
    "_telling",
    "_jr_noemer",
    "_jr_teller",
    "_dr_noemer",
    "_dr_teller",
    "_entree_uitstroom",
    "_entree_doorstroom",
    "Opbrengstjaar_uitsplitsing",
    "_driejaars_teljaar",
    "Opbrengstjaar_3jaars_voortschrijdend",
    "_num_opbrengstjaar_3jr",
)

# Business key per detailfeit (#327, tabel in docs/datamodel.md). ``levering``
# hoort erbij: Inschrijvingvolgnummer is alleen uniek per persoon binnen één
# instelling.
_INSCHRIJVING = ("levering", "_persoon_id", "Inschrijvingvolgnummer")
DETAIL_GRAIN: dict[str, tuple[str, ...]] = {
    "fact_bpv": (*_INSCHRIJVING, "Volgnummer"),
    "fact_kzd": (*_INSCHRIJVING, "Resultaatvolgnummer"),
    "fact_amo": (*_INSCHRIJVING, "Resultaatvolgnummer"),
    "fact_geo": (*_INSCHRIJVING, "CodeGeneriekExamenonderdeel"),
    "fact_bekostiging": (*_INSCHRIJVING, "Teldatum"),
    "fact_bekostiging_diploma": (*_INSCHRIJVING, "Resultaatvolgnummer"),
}

SCHOOLJAAR_FEIT = "fact_inschrijving_schooljaar"
SCHOOLJAAR = "Schooljaar"
SCHOOLJAAR_GRAIN = ["BRIN", "_persoon_id", "Inschrijvingvolgnummer", SCHOOLJAAR]
# Per groep precies één hoofdinschrijving (invariant, gecontroleerd in quality).
HOOFDINSCHRIJVING_GROEP = ["BRIN", "_persoon_id", SCHOOLJAAR]
HOOFDINSCHRIJVING = "_hoofdinschrijving"
