"""Documentatie per grafiek in het dashboard.

Elke grafiek in ``dashboard.py`` toont via :func:`chart_help` een uitklapbaar
uitlegblok: welke OBT-variabelen gebruikt worden en, in menselijke taal, welke
datamanipulatie erachter zit.  Waar relevant is een definitiekanttekening
opgenomen (bijv. verschil met de inspectie-indicator Jaarresultaat).

Bewust géén bedrijfslogica; de berekeningen leven in ``dashboard.py`` zelf.
"""

import streamlit as st

CHART_DOCS: dict[str, dict] = {
    # ── Tab Rendementen ──────────────────────────────────────────────────────
    "jr_indicatief": {
        "titel": "Jaarresultaat (JR) — indicatief, per niveau",
        "variabelen": [
            "levering",
            "Niveau",
            "_actief_1_oktober",
            "_gediplomeerd_in_jaar",
        ],
        "manipulatie": (
            "De **populatieregels** (bijlage 3) worden eerst toegepast: alleen "
            "leerwegen bol/bbl/ex (ov en od buiten beschouwing) en niveaus ≥ 2.  "
            "Van de overgebleven inschrijvingen die op 1 oktober van het "
            "studiejaar actief waren, wordt per levering × niveau het aandeel "
            "berekend dat in dat cursusjaar (augustus t/m juli) een diploma "
            "behaalde: **JR = gediplomeerden / actief op 1-okt × 100**.  De "
            "DUO-normen (voldoende: 67/68/68; hoog: 82/85/85 voor niveau "
            "2/3/4) worden er per niveau naast gezet."
        ),
        "kanttekening": (
            "Dit is een **indicatieve schatting**, geen officiële inspectie-"
            "indicator.  De inspectie definieert het jaarresultaat anders: "
            "JR = (b+d)/(b+c+d), waarbij b = gediplomeerde doorstromers, "
            "c = uitstromers zonder diploma en d = uitstromers met diploma. "
            "Ongediplomeerde doorstromers horen **niet** in de noemer.  Er is "
            "geen algemene norm van 75%; de DUO-normen zijn niveau-afhankelijk. "
            "Zie 'Toelichting onderwijsresultaten', hfst. 3 en bijlage 1."
        ),
    },
    "berekend_oordeel": {
        "titel": "Berekend oordeel Studiesucces (indicatief)",
        "variabelen": [
            "Niveau",
            "_actief_1_oktober",
            "_gediplomeerd_in_jaar",
            "metadata/normen.toml",
        ],
        "manipulatie": (
            "Op basis van de JR per niveau wordt de beoordelingsregel van "
            "tabel 3 toegepast (via `indicatoren.bereken_oordeel`): hoog als "
            "alle drie de indicatoren voldoen en JR of DR de hoge norm haalt; "
            "voldoende als ≥ 2 van de 3 voldoen; anders onvoldoende.  De "
            "normen komen uit `metadata/normen.toml`."
        ),
        "kanttekening": (
            "Hier is **alleen JR** beschikbaar; DR en SR worden door de OBT "
            "niet berekend.  Bij één indicator is een oordeel alleen mogelijk "
            "als de twee aanwezige dezelfde richting uitwijzen (§3.5); met "
            "maar één indicator is het oordeel dus indicatief en wijkt het af "
            "van het inspectieoordeel op basis van drie indicatoren over drie "
            "cursusjaren."
        ),
    },
    "entree": {
        "titel": "Entree-indicatoren (niveau 1)",
        "variabelen": [
            "Niveau",
            "_entree_doorstroom",
            "_entree_uitstroom",
            "_gediplomeerd_in_jaar",
        ],
        "manipulatie": (
            "Alle niveau-1-inschrijvingen worden in vier categorieën verdeeld "
            "(hoofdstuk 5 van de toelichting): doorstroom met/zonder diploma en "
            "uitstroom met/zonder diploma.  Doorstroom = dezelfde persoon heeft "
            "ook een inschrijving op niveau ≥ 2; diploma = `_gediplomeerd_in_jaar`.  "
            "De vier aandelen tellen op tot 100% van het aantal niveau-1-"
            "inschrijvingen (de noemer)."
        ),
    },
    "diplomas_leertraject": {
        "titel": "Diploma's per Leertraject",
        "variabelen": ["Leertraject", "DIP_DatumResultaat"],
        "manipulatie": (
            "Elke inschrijving wordt op basis van `DIP_DatumResultaat` (gevuld of "
            "leeg) ingedeeld als 'Diploma behaald' of 'Geen diploma'.  Daarna wordt "
            "het aantal inschrijvingen per combinatie van Leertraject en "
            "diplomastatus geteld."
        ),
    },
    # ── Tab Bekostiging ──────────────────────────────────────────────────────
    "bekostigingstrechter": {
        "titel": "Bekostigingstrechter",
        "variabelen": [
            "levering",
            "_actief_1_oktober",
            "_bekostigd_eerste_1okt",
            "_deelnemer_niet_bekostigd_eerste_1okt",
        ],
        "manipulatie": (
            "Vier telstappen die elkaar opvolgen: (1) alle inschrijvingen; "
            "(2) actief op 1 oktober (`DatumInschrijving ≤ 1-10` en uitgeschreven "
            "na 1-10 of nog ingeschreven); (3) daarvan met `IndicatieBekostigbaar` "
            "= 'J'; (4) actief maar niet bekostigd (= verschil tussen stap 2 en 3)."
        ),
    },
    "bekostiging_levering": {
        "titel": "Bekostigd vs niet-bekostigd per levering",
        "variabelen": ["levering", "IndicatieBekostigbaar"],
        "manipulatie": (
            "`IndicatieBekostigbaar` wordt genormaliseerd naar 'Bekostigd' "
            "(codes 'J'/'1') of 'Niet bekostigd' (overig).  Per levering wordt het "
            "aantal inschrijvingen per categorie geteld."
        ),
    },
    "bekostigingsgrondslagen": {
        "titel": "Bekostigingsgrondslagen (TBGI)",
        "variabelen": [
            "fact_bekostiging.Bekostigingsstatus",
            "fact_bekostiging.BijdrageInschrijvingAanDeelnemerswaarde",
        ],
        "manipulatie": (
            "Gelezen uit `fact_bekostiging` (grain: één rij per inschrijving per "
            "teldatum, afkomstig uit het TBGI-bestand).  Het aantal rijen wordt "
            "per `Bekostigingsstatus` geteld en aflopend gesorteerd.  Aanvullend "
            "wordt de som van `BijdrageInschrijvingAanDeelnemerswaarde` over alle "
            "rijen getoond als totale deelnemerswaarde."
        ),
    },
    "na_1okt": {
        "titel": "Inschrijvingen na 1-oktober",
        "variabelen": ["_ingeschreven_jaar_later"],
        "manipulatie": (
            "Telt het aantal inschrijvingen waarvan `DatumInschrijving` ná 1 "
            "oktober van het studiejaar valt.  Deze studenten tellen niet mee voor "
            "de 1-oktober-bekostiging."
        ),
    },
    # ── Tab Opleidingen ──────────────────────────────────────────────────────
    "top10_opleidingen": {
        "titel": "Top-10 opleidingen naar inschrijvingen",
        "variabelen": ["Opleidingcode", "Opleiding_naam"],
        "manipulatie": (
            "Het aantal inschrijvingen wordt per `Opleidingcode` geteld, aflopend "
            "gesorteerd, en de tien grootste worden getoond.  Waar beschikbaar "
            "wordt de CREBO-naam uit de verrijkingstabel getoond."
        ),
    },
    "inschrijvingen_domein": {
        "titel": "Inschrijvingen per domein",
        "variabelen": ["dim_opleiding.Opleiding_domein"],
        "manipulatie": (
            "Het aantal inschrijvingen wordt per CREBO-domein ("
            "`Opleiding_domein`, afgeleid uit `hoofdgroep_naam` in de CREBO-tabel) "
            "geteld en aflopend gesorteerd. Elke inschrijving telt mee voor het "
            "domein van de bijbehorende opleiding."
        ),
    },
    "inschrijvingen_sectorkamer": {
        "titel": "Inschrijvingen per sectorkamer",
        "variabelen": ["dim_opleiding.Opleiding_sectorkamer"],
        "manipulatie": (
            "Het aantal inschrijvingen wordt per S-BB sectorkamer ("
            "`Opleiding_sectorkamer`, afgeleid uit `sectorkamer_naam` in de "
            "CREBO-tabel) geteld en aflopend gesorteerd."
        ),
    },
    "bol_bbl_levering": {
        "titel": "BOL vs BBL per levering",
        "variabelen": ["levering", "Leertraject"],
        "manipulatie": (
            "Per levering wordt het aantal inschrijvingen geteld, opgesplitst "
            "naar Leertraject (BOL, BBL, …)."
        ),
    },
    "bpv_coverage": {
        "titel": "BPV-coverage",
        "variabelen": ["Leertraject", "BPV_Aantal"],
        "manipulatie": (
            "Elke inschrijving wordt op basis van `BPV_Aantal` (> 0) ingedeeld als "
            "'Met BPV' of 'Zonder BPV'.  Daarna wordt het aantal per combinatie van "
            "Leertraject en BPV-status geteld."
        ),
    },
    "bpv_periodes": {
        "titel": "BPV-periodes — duur en omvang",
        "variabelen": [
            "fact_bpv.DatumBegin",
            "fact_bpv.DatumEindWerkelijk",
            "fact_bpv.Omvang",
        ],
        "manipulatie": (
            "Gelezen uit `fact_bpv` (grain: één rij per BPV-stage per inschrijving).  "
            "Stages met bekende begin- én einddatum tellen mee.  De duur wordt "
            "berekend als het aantal dagen tussen `DatumBegin` en "
            "`DatumEindWerkelijk`.  "
            "De gemiddelde omvang (uren/weken, afhankelijk van de bron) wordt "
            "apart getoond."
        ),
    },
    "kzd": {
        "titel": "KZD-behaaldverhouding per levering",
        "variabelen": ["levering", "KZD_Aantal", "KZD_AantalBehaald"],
        "manipulatie": (
            "Alleen inschrijvingen met minimaal één KZD-onderdeel tellen mee.  Per "
            "inschrijving wordt het percentage behaalde onderdelen berekend "
            "(`KZD_AantalBehaald / KZD_Aantal × 100`), waarna per levering het "
            "gemiddelde over de inschrijvingen wordt getoond."
        ),
    },
    "kzd_detail": {
        "titel": "Keuzedelen — resultaten per code",
        "variabelen": ["fact_kzd.CodeKeuzedeel", "fact_kzd.Resultaat"],
        "manipulatie": (
            "Gelezen uit `fact_kzd` (grain: één rij per keuzedeel per inschrijving).  "
            "Per keuzedeel-code (`CodeKeuzedeel`) wordt het totaal en het aantal "
            "behaalde resultaten geteld.  Een keuzedeel telt als behaald als het "
            "veld `Resultaat` de tekst 'BEHAALD' bevat.  Top-15 op volume."
        ),
    },
    "instelling": {
        "titel": "Instelling",
        "variabelen": ["Instelling_naam", "Instelling_plaats"],
        "manipulatie": (
            "Toont de unieke combinaties van instellingsnaam en -plaats die in de "
            "data voorkomen (afgeleid uit de BRIN-tabel)."
        ),
    },
    # ── Tab Studenten ────────────────────────────────────────────────────────
    "geslacht_leertraject": {
        "titel": "Geslachtsverdeling per Leertraject",
        "variabelen": ["Geslacht", "Leertraject"],
        "manipulatie": (
            "De codes M/V/O worden vertaald naar 'Man'/'Vrouw'/'Onbekend'.  Per "
            "combinatie van Geslacht en Leertraject wordt het aantal inschrijvingen "
            "geteld."
        ),
    },
    "herkomst": {
        "titel": "Herkomst (migratieachtergrond)",
        "variabelen": ["Nationaliteit1_migratieachtergrond"],
        "manipulatie": (
            "Het aantal inschrijvingen wordt per migratieachtergrond geteld "
            "(afgeleid uit de eerste nationaliteit via de nationaliteitscode-"
            "tabel), aflopend gesorteerd."
        ),
    },
    "top10_gemeenten": {
        "titel": "Top 10 gemeenten",
        "variabelen": ["Gemeente"],
        "manipulatie": (
            "Het aantal studenten wordt per gemeente geteld (gemeentenaam afgeleid "
            "uit `Postcodecijfers` via de postcodetabel), aflopend gesorteerd, en "
            "de tien grootste worden getoond."
        ),
    },
    "top10_geboorteland": {
        "titel": "Top 10 geboorteland",
        "variabelen": ["CodeGeboorteland_naam"],
        "manipulatie": (
            "Het aantal studenten wordt per geboorteland geteld (naam afgeleid via "
            "de landcodetabel), exclusief 'Onbekend'/'NULL', aflopend gesorteerd, "
            "en de tien grootste worden getoond."
        ),
    },
    "uitstroomredenen": {
        "titel": "Uitstroomredenen",
        "variabelen": ["RedenUitschrijving"],
        "manipulatie": (
            "Lege of ontbrekende codes worden getoond als 'Nog ingeschreven'.  "
            "Bekende codes krijgen een leesbaar label (bijv. 'Diploma BOL', "
            "'Eigen verzoek'); overige codes worden als 'Overig (code: …)' "
            "getoond.  Het aantal wordt per reden geteld en aflopend gesorteerd."
        ),
    },
    "duur_inschrijving": {
        "titel": "Duur inschrijving (maanden)",
        "variabelen": ["DatumInschrijving", "DatumUitschrijvingWerkelijk"],
        "manipulatie": (
            "Alleen inschrijvingen met een bekende in- én uitschrijfdatum tellen "
            "mee.  De duur in maanden wordt berekend als "
            "(uit − in) in dagen / 30 en ingedeeld in vijf klassen: "
            "< 6, 6–12, 12–24, 24–36 en > 36 maanden.  Per klasse wordt het aantal "
            "geteld."
        ),
    },
    # ── Tab Opleidingsstructuur ──────────────────────────────────────────────
    "dossier_inschrijvingen": {
        "titel": "Inschrijvingen per kwalificatiedossier (23xxx)",
        "variabelen": [
            "dim_opleiding.Opleiding_dossiercode",
            "dim_opleiding.Opleiding_dossier",
        ],
        "manipulatie": (
            "Een **kwalificatiedossier** (23xxx-code) is een brede beroepsgerichte "
            "eenheid die meerdere verwante kwalificaties (25xxx/27xxx) bundelt. "
            "Elke CREBO-kwalificatie valt onder precies één dossier. "
            "Het aantal inschrijvingen wordt per dossier geteld en aflopend "
            "gesorteerd. "
            "Dossiercode en -naam zijn afgeleid uit de CREBO-metadatatable "
            "(`crebo.csv`)."
        ),
        "kanttekening": (
            "Een student kan meerdere kwalificaties (25xxx/27xxx) onder hetzelfde "
            "dossier (23xxx) volgen; tel op dossierniveau dus niet gelijk aan unieke "
            "studenten. Voor een stabiele longitudinale tijdreeks over meerdere "
            "studiejaren is groeperen op dossiercode (23xxx) te verkiezen boven "
            "individuele kwalificatiecodes, omdat 25xxx-codes kunnen overgaan in 27xxx."
        ),
    },
    "sbb_beroep_inschrijvingen": {
        "titel": "Inschrijvingen per beroep (S-BB koppeltabel)",
        "variabelen": ["dim_opleiding.Opleiding_beroep"],
        "manipulatie": (
            "De S-BB mbo-opleidingskoppeltabel (Groep 19, kwalificatie-mijn.s-bb.nl) "
            "koppelt elke actuele CREBO-kwalificatiecode (25xxx/27xxx) aan een "
            "beroepsnaam. Het aantal inschrijvingen wordt per beroep geteld. "
            "Getoond zijn de top-20 beroepen naar inschrijvingen. "
            "Inschrijvingen op codes die niet in de koppeltabel voorkomen "
            "tellen niet mee."
        ),
    },
    "sbb_looptijd": {
        "titel": "Looptijd van opleidingen (S-BB)",
        "variabelen": [
            "dim_opleiding.Opleiding_eerste_schooljaar",
            "dim_opleiding.Opleiding_laatste_schooljaar",
        ],
        "manipulatie": (
            "De S-BB koppeltabel registreert per kwalificatiecode het eerste en "
            "laatste schooljaar dat de opleiding actief is. "
            "De staafgrafiek toont het aantal inschrijvingen per "
            "`Opleiding_laatste_schooljaar`: "
            "een piek bij een recent schooljaar duidt op veel lopende opleidingen, "
            "een piek in het verleden op opleidingen die al zijn beëindigd."
        ),
        "kanttekening": (
            "Een inschrijving op een 'verlopen' opleiding (laatste schooljaar < huidig "
            "schooljaar) hoeft geen datafout te zijn: studenten die vóór de "
            "looptijdwijziging zijn ingeschreven mogen de opleiding doorgaans afmaken."
        ),
    },
    "hercodering_25_27": {
        "titel": "Hercodering: 25xxx → 27xxx (via S-BB opvolger)",
        "variabelen": [
            "dim_opleiding.Opleidingcode",
            "dim_opleiding.Opleiding_opvolger",
        ],
        "manipulatie": (
            "Bij herziening van een kwalificatiedossier krijgt een bestaande "
            "kwalificatie (25xxx) een nieuwe code (27xxx). "
            "De S-BB koppeltabel bevat de kolom `opvolger_crebo` die de nieuwe code "
            "vermeldt. De tabel toont alle unieke 25xxx-codes in de data waarvoor "
            "een opvolger is geregistreerd, plus het totaal aantal inschrijvingen "
            "op die 'oude' codes."
        ),
        "kanttekening": (
            "Voor longitudinale analyses over meerdere studiejaren moeten 25xxx en "
            "de bijbehorende 27xxx-opvolger als één opleiding worden behandeld. "
            "Groepeer op dossiercode (23xxx) voor een stabiele tijdreeks "
            "die onafhankelijk is van hernummering."
        ),
    },
    # ── Tab Examens ──────────────────────────────────────────────────────────
    "geo_slagingspercentage": {
        "titel": "GEO slagingspercentage (eindcijfer ≥ 5,5)",
        "variabelen": ["fact_geo.CodeGeneriekExamenonderdeel", "fact_geo.Eindcijfer"],
        "manipulatie": (
            "Gelezen uit `fact_geo` (grain: één rij per inschrijving × "
            "examenonderdeel).  Per generiek examenonderdeel wordt het aandeel "
            "deelnemers met een eindcijfer van 5,5 of hoger berekend: "
            "**geslaagd (%) = (eindcijfer ≥ 5,5) / totaal met eindcijfer × 100**.  "
            "De drempel 5,5 is de gangbare slaaggrens; deelnemers zonder eindcijfer "
            "tellen niet mee in de noemer.  Gesorteerd op slagingspercentage."
        ),
    },
    "geo_eindcijfers": {
        "titel": "GEO-examencijfers",
        "variabelen": ["fact_geo.CodeGeneriekExamenonderdeel", "fact_geo.Eindcijfer"],
        "manipulatie": (
            "Gelezen uit `fact_geo` (grain: één rij per "
            "inschrijving × examenonderdeel).  "
            "Voor elk aanwezig generiek examenvak wordt het gemiddelde eindcijfer en "
            "het aantal invullingen berekend.  De code wordt via `geo_codes.toml` "
            "vertaald naar een leesbare naam."
        ),
    },
    "geo_ie_ce": {
        "titel": "GEO IE vs CE — vergelijking",
        "variabelen": [
            "fact_geo.CodeGeneriekExamenonderdeel",
            "fact_geo.CijferIE",
            "fact_geo.CijferCE",
        ],
        "manipulatie": (
            "Gelezen uit `fact_geo`.  Voor elk examenonderdeel met zowel een "
            "gevuld `CijferIE` als `CijferCE` worden de gemiddelden naast "
            "elkaar gezet.  De code wordt via `geo_codes.toml` vertaald naar "
            "een leesbare naam."
        ),
    },
    "amo": {
        "titel": "AMO-onderdelen",
        "variabelen": ["AMO_Aantal"],
        "manipulatie": (
            "Telt het totaal aantal examenvakken voor de arbeidsmarktgerichte "
            "opleidingsdelen (`AMO_Aantal`) en het gemiddelde per inschrijving."
        ),
    },
}


def chart_help(key: str) -> None:
    """Toon een uitklapbaar uitlegblok voor de grafiek met ``key``.

    Rendert niets als de key niet bestaat, zodat het dashboard robuust blijft
    bij grafieken waarvoor (nog) geen documentatie is.
    """
    doc = CHART_DOCS.get(key)
    if doc is None:
        return
    with st.expander(f"ℹ️ Hoe is deze grafiek gemaakt? — {doc['titel']}"):
        st.write(doc["manipulatie"])
        variabelen = " · ".join(f"`{v}`" for v in doc["variabelen"])
        st.caption(f"**Gebruikte variabelen:** {variabelen}")
        kanttekening = doc.get("kanttekening")
        if kanttekening:
            st.warning(kanttekening)
