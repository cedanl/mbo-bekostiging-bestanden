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

# Begeleidende kolom ``<datumveld>_precisie`` bij een datum waarin het PvE ``00``
# toestaat (#206). ``onbekend``: jaar 0, de datum is null (#391).
PRECISIE_SUFFIX = "_precisie"
PRECISIE_ONBEKEND = "onbekend"

# Koppelsleutels tussen recordtypes. ``Inschrijvingvolgnummer`` is alleen uniek
# per persoon binnen één instelling, dus zonder ``levering`` hoort ``BRIN`` erbij.
JOIN_PERSOON = ["levering", "_persoon_id"]
JOIN_INSCHRIJVING = [*JOIN_PERSOON, "Inschrijvingvolgnummer"]
JOIN_INSTELLING_INSCHRIJVING = ["BRIN", "_persoon_id", "Inschrijvingvolgnummer"]

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

# Bron-BRIN van een detailrij die afwijkt van haar parent-inschrijving (#357);
# de parent wint in ``BRIN``, de bronwaarde blijft zichtbaar.
BRIN_BRON = "_brin_bron"
# Business key per detailfeit (#327, tabel in docs/datamodel.md).
_INSCHRIJVING = tuple(JOIN_INSCHRIJVING)
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

# Tabel in de TBG-i-brondata met XML-elementen buiten het schema, als ruwe XML
# met hun plaats (#420); het analysemodel neemt hem niet over.
ONBEKENDE_XML = "OnbekendeXML"
