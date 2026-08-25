"""Documentatie per tabel op de Resultaten-pagina.

Elke star-schema-tabel in ``resultaten.py`` krijgt via :func:`tabel_help` een
uitklapbaar uitlegblok in gewone taal: wát de tabel bevat en op welk
DUO-bronbestand (h15 RO / h16 TBGI / h17 GRONDSLAG) de records gebaseerd zijn.
Waar een tabel leeg kán blijven, staat dat er expliciet bij.

Bewust géén bedrijfslogica; het model leeft in ``src/.../star.py``.
"""

import streamlit as st

# Korte, algemene uitleg over hoe de pagina werkt (bovenaan de pagina).
PAGINA_INTRO = (
    "Op deze pagina blader je door de verwerkte tabellen (het **star schema**). "
    "Kies een tabel, bekijk de eerste 1 000 rijen en download desgewenst de "
    "volledige tabel als CSV. Onder elke tabel-keuze staat uitleg over wat je "
    "ziet en waar de gegevens vandaan komen.\n\n"
    "Een tabel kan **leeg** zijn als het bijbehorende bronbestand niet is "
    "verwerkt (bijvoorbeeld geen h16-TBGI meegeleverd). Dat is geen fout."
)

# Per tabel: menselijke titel, wat de tabel bevat, en de bron/leegte-notitie.
TABEL_DOCS: dict[str, dict[str, str]] = {
    "dim_deelnemer": {
        "titel": "Deelnemers (studenten)",
        "wat": (
            "Eén regel per unieke student, met achtergrondkenmerken zoals "
            "geboortedatum, geslacht, woongemeente, nationaliteit en "
            "geboorteland. Studenten zijn gepseudonimiseerd — er staat geen BSN "
            "in, maar een intern persoons-id."
        ),
        "bron": (
            "Opgebouwd uit de PER-records in de inschrijvingsbestanden "
            "(h15 RO en/of h17 GRONDSLAG)."
        ),
    },
    "dim_opleiding": {
        "titel": "Opleidingen",
        "wat": (
            "Eén regel per unieke opleiding (crebo/opleidingscode), met naam, "
            "niveau, leerweg (bol/bbl), domein en de koppeling naar het "
            "S-BB-beroepsniveau."
        ),
        "bron": (
            "Afgeleid uit de inschrijvingen (h15/h17), verrijkt met de "
            "metadata-koppeltabellen (crebo- en S-BB-lijsten)."
        ),
    },
    "dim_instelling": {
        "titel": "Instellingen",
        "wat": (
            "Eén regel per onderwijsinstelling (BRIN), met naam en kenmerken "
            "van de instelling."
        ),
        "bron": (
            "De BRIN-code uit de bronbestanden, verrijkt met de "
            "metadata-tabel brinnummer."
        ),
    },
    "fact_inschrijving": {
        "titel": "Inschrijvingen — het hart van het model",
        "wat": (
            "Eén regel per inschrijving van een student in een opleiding. "
            "Verwijst naar de deelnemer, de opleiding en de instelling, en "
            "bevat afgeleide vlaggen zoals hoofdinschrijving, actief op "
            "1 oktober en gediplomeerd. Alle andere feittabellen hangen "
            "hieraan."
        ),
        "bron": (
            "De ISP-records uit zowel h15 (RO) als h17 (GRONDSLAG). Let op: "
            "dezelfde student kan in beide leveringen voorkomen — dat is geen "
            "dubbeling maar twee momentopnames. De kolom `levering` laat zien "
            "uit welk bestand een regel komt. Filter op één `levering` om "
            "dubbeltelling te voorkomen."
        ),
    },
    "fact_bpv": {
        "titel": "BPV (stages)",
        "wat": (
            "Eén regel per beroepspraktijkvorming-periode (stage) per "
            "inschrijving, met begin- en einddatum en het leerbedrijf."
        ),
        "bron": "De BPV-records uit h15 (RO) en/of h17 (GRONDSLAG).",
    },
    "fact_kzd": {
        "titel": "Keuzedelen",
        "wat": (
            "Eén regel per keuzedeel-resultaat per inschrijving, met de code "
            "van het keuzedeel en het behaalde resultaat."
        ),
        "bron": "De KZD-records uit h15 (RO) en/of h17 (GRONDSLAG).",
    },
    "fact_amo": {
        "titel": "AMO-onderdelen",
        "wat": (
            "Eén regel per aanvullende module/onderdeel per inschrijving. "
            "Vaak leeg als de bron geen AMO-records bevat."
        ),
        "bron": "De AMO-records uit h15 (RO) en/of h17 (GRONDSLAG).",
    },
    "fact_geo": {
        "titel": "GEO — generieke examenresultaten",
        "wat": (
            "De generieke examenonderdelen (Nederlands, rekenen, Engels, "
            "loopbaan en burgerschap) in long-format: één regel per "
            "inschrijving × examenonderdeel, met het resultaat."
        ),
        "bron": "De GEO-records uit h15 (RO) en/of h17 (GRONDSLAG).",
    },
    "fact_bekostiging": {
        "titel": "Bekostigingsgrondslagen",
        "wat": (
            "Per inschrijving × teldatum de bekostigingsgrondslag: telt deze "
            "inschrijving mee voor de bekostiging (bekostigbaar ja/nee) op de "
            "peildatum."
        ),
        "bron": (
            "De BII-records uit h17 (GRONDSLAG) én de Teldatum-records uit "
            "h16 (TBGI). **Leeg** als je geen h16 verwerkte én je h17 geen "
            "BII-regels bevat."
        ),
    },
    "fact_bekostiging_diploma": {
        "titel": "Diplomabekostiging",
        "wat": (
            "De diploma-gebonden bekostigingsbijdragen per inschrijving: de "
            "waarde die een behaald diploma oplevert."
        ),
        "bron": "De Diploma-records uit h16 (TBGI). **Leeg** zonder h16.",
    },
    "meta_leveringen": {
        "titel": "Leveringen (metadata)",
        "wat": (
            "Technische metadata per verwerkt bronbestand: peildatum, "
            "studiejaar en controle-aantallen. Handig om te zien welke "
            "leveringen zijn opgenomen."
        ),
        "bron": (
            "De VLP- en SLR-records (voorloop- en sluitrecord) uit elk "
            "verwerkt bestand."
        ),
    },
}


def tabel_help(key: str) -> None:
    """Toon een uitklapbaar uitlegblok voor de tabel met ``key``.

    Rendert niets als de key niet bestaat, zodat de pagina robuust blijft bij
    tabellen waarvoor (nog) geen documentatie is.
    """
    doc = TABEL_DOCS.get(key)
    if doc is None:
        return
    with st.expander(f"ℹ️ Wat zie ik hier? — {doc['titel']}"):
        st.write(doc["wat"])
        st.caption(f"**Gebaseerd op:** {doc['bron']}")
