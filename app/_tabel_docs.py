"""Documentatie per tabel op de Analysemodel-pagina.

Elke star-schema-tabel in ``analysemodel.py`` krijgt via :func:`tabel_help` een
uitklapbaar uitlegblok in gewone taal: wát de tabel bevat en op welk
DUO-bronbestand (h15 RO / h16 TBGI / h17 GRONDSLAG) de records gebaseerd zijn.
Waar een tabel leeg kán blijven, staat dat er expliciet bij.

Bewust géén bedrijfslogica; het model leeft in ``src/.../star.py``.
"""

import streamlit as st

BRONDATA_INTRO = (
    "Elk DUO-bestand per levering en recordtype, getrouw aan de levering en "
    "alleen getypeerd: de werkbare vorm van de ruwe bestanden. Kies een tabel, "
    "kies eventueel welke kolommen je ziet en download de volledige tabel als "
    "CSV; persoonsgegevens zijn standaard verborgen."
)

ANALYSEMODEL_INTRO = (
    "De leveringen samengevoegd tot dimensies en feiten (star schema), met "
    "ontwerpkeuzes zoals canonicalisatie van overlappende leveringen, "
    "hoofdinschrijving en niveau-aanvulling (zie de documentatie). Kies een "
    "tabel, kies eventueel welke kolommen je ziet en download de volledige "
    "tabel als CSV; persoonsgegevens zijn standaard verborgen.\n\n"
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
    "fact_inschrijving_schooljaar": {
        "titel": "Inschrijvingen per schooljaar",
        "wat": (
            "Eén rij per deelnemer, instelling, inschrijving en schooljaar waarin "
            "de inschrijving op 1 oktober actief is. Hier staan de tellingen: "
            "hoofdinschrijving (één per deelnemer per instelling per jaar), "
            "bekostigd, jaarresultaat (JR) en diplomaresultaat (DR)."
        ),
        "bron": (
            "Afgeleid uit de ISP-perioden: een periode telt in elk schooljaar "
            "waarvan zij 1 oktober dekt, tot de peildatum van de levering."
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
        "bron": (
            "De BID-records uit h17 (GRONDSLAG) én de Diploma-records uit h16 "
            "(TBGI); kolom `Bron` zegt welke. **Leeg** als je geen h16 "
            "verwerkte én je h17 geen BID-regels bevat."
        ),
    },
    "meta_leveringen": {
        "titel": "Leveringen (metadata)",
        "wat": (
            "Technische metadata per verwerkt bronbestand: peildatum, "
            "studiejaar en controle-aantallen. Handig om te zien welke "
            "leveringen zijn opgenomen."
        ),
        "bron": (
            "Elk verwerkt bestand staat erin. Peildatum en controle-aantallen "
            "komen uit de VLP- en SLR-records (voorloop- en sluitrecord); een "
            "TBGI-bestand (XML) heeft die niet, dus daar zijn ze leeg."
        ),
    },
    "meta_canonicalisatie": {
        "titel": "Vervangen leveringen (metadata)",
        "wat": (
            "Welke leveringen zijn vervangen door een nieuwere levering van "
            "dezelfde instelling, met het aantal inschrijvingen en ISP-perioden "
            "en de reden. Zo telt een inschrijving die in meerdere leveringen "
            "staat maar één keer. Leeg als geen leveringen overlappen."
        ),
        "bron": (
            "Afgeleid bij het bouwen van het star schema: per inschrijving "
            "(instelling × deelnemer × volgnummer) wint de levering met de "
            "nieuwste aanmaakdatum (VLP)."
        ),
    },
    "meta_referentiedata": {
        "titel": "Referentiedata (metadata)",
        "wat": (
            "Welke referentietabellen de run gebruikte: bron, datum van "
            "opname, tot wanneer ze de opleidingen dekken, en een vingerafdruk "
            "(sha256) van de inhoud. `afwijkend` betekent dat het bestand op "
            "schijf niet meer het bestand uit het manifest is."
        ),
        "bron": (
            "`metadata/referentiedata.json` in het package, vergeleken met de "
            "bestanden ernaast. Het niveau van RO-inschrijvingen komt uit "
            "`crebo.csv` en de S-BB-koppeltabel."
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
