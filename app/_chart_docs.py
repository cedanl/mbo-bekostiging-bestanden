"""Documentatie per grafiek in het dashboard.

Elke grafiek in ``dashboard.py`` toont via :func:`chart_help` een uitklapbaar
uitlegblok: welke star schema-variabelen gebruikt worden en, in menselijke taal,
welke datamanipulatie erachter zit.  Waar relevant is een definitiekanttekening
opgenomen (bijv. verschil met de inspectie-indicator Jaarresultaat).

Bewust géén bedrijfslogica; de berekeningen leven in ``dashboard.py`` zelf.
"""

import streamlit as st

# Gedeelde uitleg voor grafieken op detail-feiten (fact_bpv, fact_kzd, fact_geo).
_DETAIL_SELECTIE = (
    "  Alleen rijen uit de ISP-perioden in de gekozen studiejaren tellen mee; de "
    "koppeling met de inschrijving loopt via `_inschrijving_periode_id`."
)

CHART_DOCS: dict[str, dict] = {
    # ── Tab Rendementen ──────────────────────────────────────────────────────
    "kwaliteit": {
        "titel": "Kwaliteitsstatus en bronleveringen",
        "variabelen": [
            "quality.json.summary",
            "quality.json.conformiteit",
            "quality.json.deliveries",
            "quality.json.star",
            "meta_leveringen.Peilgrens",
            "meta_leveringen.Laatste_peildatum",
        ],
        "manipulatie": (
            "De status komt uit `quality.json` naast het star schema: `fail` bij "
            "minstens één error, `warn` bij warnings, anders `pass`.  Elke melding "
            "staat erbij met haar bron (een levering of de ster) en ernst; de "
            "ernst en de telling in de status komen uit dezelfde functie "
            "(`quality.kwaliteitsmeldingen`).  De tabel toont per levering de "
            "aanmaakdatum, het observatievenster (tot welke peildatum de levering "
            "iets kan zeggen) en de SLR-reconciliatie.  Onder de status staat de "
            "conformiteit: per proxy-indicator (JR, DR) de status, de formele "
            "afwijkingen (#369) en dat formeel gebruik is uitgesloten (#296), het "
            "privacyprofiel van het artefact, de gebruikte "
            "PvE-versie en of de PvE-bron intact is (#364); die komen uit "
            "`quality.json.conformiteit`."
        ),
        "kanttekening": (
            "Grafieken op een ster met status `fail` zijn niet betrouwbaar: los "
            "eerst de errors op."
        ),
    },
    "jr_indicatief": {
        "titel": "Jaarresultaat (JR-proxy) — per schooljaar en niveau",
        "variabelen": [
            "fact_inschrijving_schooljaar.Schooljaar",
            "fact_inschrijving_schooljaar.Niveau",
            "fact_inschrijving_schooljaar._jr_noemer",
            "fact_inschrijving_schooljaar._jr_teller",
        ],
        "manipulatie": (
            "Gelezen uit `fact_inschrijving_schooljaar` (één rij per inschrijving "
            "× schooljaar waarin zij op 1 oktober actief is).  De noemer is "
            "`_jr_noemer` (de hoofdinschrijving: één per deelnemer × instelling × "
            "schooljaar), de teller `_jr_teller` (daarvan gediplomeerd in dat "
            "schooljaar); beide berekent de pipeline, het dashboard telt alleen op "
            "(`indicatoren.rendement`).  Daarna gelden de **populatieregels** "
            "(bijlage 3): leerwegen bol/bol-dt/bbl/ex (OVO en ODT buiten "
            "beschouwing) en niveaus ≥ 2.  **JR = teller / noemer × 100** per "
            "schooljaar × niveau, met de DUO-normen uit `metadata/normen.toml` "
            "ernaast."
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
    "dr_indicatief": {
        "titel": "Diplomaresultaat (DR-proxy) — per schooljaar en niveau",
        "variabelen": [
            "fact_inschrijving_schooljaar.Schooljaar",
            "fact_inschrijving_schooljaar.Niveau",
            "fact_inschrijving_schooljaar._dr_noemer",
            "fact_inschrijving_schooljaar._dr_teller",
        ],
        "manipulatie": (
            "Gelezen uit `fact_inschrijving_schooljaar`.  Noemer `_dr_noemer`: de "
            "hoofdinschrijving (niveau ≥ 2) in schooljaar t van een student die "
            "in t+1 bij geen enkele instelling in de dataset staat ingeschreven, "
            "alleen als t+1 waarneembaar is (een levering van het eigen BRIN "
            "dekt 1-10-(t+1)).  Teller `_dr_teller`: daarvan wie bij de eigen "
            "instelling een diploma op niveau ≥ 2 behaalde tussen 1-8-(t-5) en "
            "de peildatum 1-10-(t+1) (zesjaarsvenster; één uitkomst per "
            "student, ook bij meerdere diploma's, #119).  Beide berekent de "
            "pipeline; na de "
            "**populatieregels** (bijlage 3) geldt **DR = teller / noemer × 100** "
            "per schooljaar × niveau, met de DUO-normen ernaast."
        ),
        "kanttekening": (
            "Dit is een **indicatieve schatting**, geen officiële inspectie-"
            "indicator.  Het diplomaniveau komt van de opleidingscode van het "
            "diploma (CREBO, dan S-BB); een diploma zonder bekend niveau telt "
            "niet.  Diploma's van vóór de eerste levering ziet de dataset niet.  "
            "Uitstroom is instelling-onafhankelijk, maar de dataset bevat alleen "
            "de eigen leveringen: een overstap naar een instelling buiten de "
            "dataset telt hier als uitstroom (`quality.json` → `dr_scope`, "
            "#118).  Schooljaren zonder waarneembaar t+1 vallen buiten de "
            "noemer.  Zie §3.1 en bijlage 1."
        ),
    },
    "berekend_oordeel": {
        "titel": "Proxy-oordeel Studiesucces (indicatief)",
        "variabelen": [
            "fact_inschrijving_schooljaar.Niveau",
            "fact_inschrijving_schooljaar._jr_noemer",
            "fact_inschrijving_schooljaar._jr_teller",
            "fact_inschrijving_schooljaar._dr_noemer",
            "fact_inschrijving_schooljaar._dr_teller",
            "metadata/normen.toml",
        ],
        "manipulatie": (
            "JR en DR worden per niveau opgeteld over de geselecteerde "
            "schooljaren (tellers en noemers, niet de percentages).  Daarop wordt "
            "de beoordelingsregel van "
            "tabel 3 toegepast (via `indicatoren.bereken_oordeel`): hoog als "
            "alle drie de indicatoren voldoen en JR of DR de hoge norm haalt; "
            "voldoende als ≥ 2 van de 3 voldoen; anders onvoldoende.  De "
            "normen komen uit `metadata/normen.toml`.  De kolommen heten `JR-proxy` "
            "en `DR-proxy`; de vergelijking met de voldoende-norm is indicatief."
        ),
        "kanttekening": (
            "Het oordeel telt de **geselecteerde** schooljaren op, niet het "
            "formele driejaarsvenster.  SR (startersresultaat) is **niet "
            "beschikbaar** — de inspectie "
            "berekent dit over drie cohorten met zes jaar inschrijvings­"
            "historie, die buiten de eigen leveringen valt.  Bij één "
            "ontbrekende indicator is een oordeel alleen mogelijk als de twee "
            "aanwezige indicatoren dezelfde richting uitwijzen (§3.5)."
        ),
    },
    "entree": {
        "titel": "Entree-indicatoren (niveau 1)",
        "variabelen": [
            "fact_inschrijving_schooljaar._entree_noemer",
            "_entree_doorstroom",
            "_entree_uitstroom",
            "_gediplomeerd_in_jaar",
        ],
        "manipulatie": (
            "Gelezen uit `fact_inschrijving_schooljaar`, dus één rij per "
            "student × instelling × schooljaar.  Populatie (`_entree_noemer`): de "
            "hoofdinschrijving op niveau 1 in schooljaar t die Entree daarna "
            "verlaat, met t+1 waarneembaar.  Doorstroom = in t+1 een inschrijving "
            "op niveau ≥ 2, bij welke instelling in de dataset ook (#118); "
            "uitstroom = in t+1 nergens meer ingeschreven; wie in Entree blijft "
            "telt niet mee.  Diploma = "
            "`_gediplomeerd_in_jaar` (diploma in schooljaar t).  De vier aandelen "
            "tellen op tot 100% van de populatie (hoofdstuk 5 van de toelichting, "
            "#306)."
        ),
    },
    "diplomas_leertraject": {
        "titel": "Diploma's per Leertraject",
        "variabelen": ["Leertraject", "DIP_DatumResultaat"],
        "manipulatie": (
            "Elke inschrijving wordt op basis van `DIP_DatumResultaat` (gevuld of "
            "leeg) ingedeeld als 'Diploma behaald' of 'Geen diploma'.  Daarna wordt "
            "het aantal inschrijvingen per combinatie van Leertraject en "
            "diplomastatus geteld.  **Periode-grain**: rijen van "
            "`fact_inschrijving` die in een geselecteerd schooljaar beginnen of "
            "er op 1 oktober actief zijn."
        ),
    },
    # ── Tab Bekostiging ──────────────────────────────────────────────────────
    "bekostigingstrechter": {
        "titel": "Bekostigingstrechter",
        "variabelen": [
            "fact_inschrijving",
            "fact_inschrijving_schooljaar._bekostigd",
        ],
        "manipulatie": (
            "Vier tellingen: (1) inschrijvingsperioden in `fact_inschrijving`; "
            "(2) actief op 1 oktober = rijen in `fact_inschrijving_schooljaar` "
            "(inschrijving × schooljaar waarin een periode 1 oktober dekt); "
            "(3) daarvan bekostigbaar (`_bekostigd`: `IndicatieBekostigbaar` = J "
            "in de periode op 1 oktober); (4) actief maar niet bekostigbaar "
            "(verschil tussen 2 en 3)."
        ),
    },
    "bekostiging_levering": {
        "titel": "Bekostigd vs niet-bekostigd per levering",
        "variabelen": [
            "fact_inschrijving_schooljaar.levering",
            "fact_inschrijving_schooljaar._bekostigd",
        ],
        "manipulatie": (
            "Gelezen uit `fact_inschrijving_schooljaar`: één rij per inschrijving "
            "× geselecteerd schooljaar waarin zij op 1 oktober actief is.  "
            "'Bekostigd' = `_bekostigd` (`IndicatieBekostigbaar` = J in de periode "
            "op 1 oktober), anders 'Niet bekostigd'.  Per levering wordt het "
            "aantal per categorie geteld (#240)."
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
            "teldatum, uit TBG-i of GRONDSLAG-BII).  Gefilterd op het schooljaar "
            "waarin de `Teldatum` valt (1-8 t/m 31-7), dat in de sidebar-selectie "
            "moet zitten (#240).  Het aantal rijen wordt per "
            "`Bekostigingsstatus` geteld en aflopend gesorteerd.  Aanvullend "
            "wordt de som van `BijdrageInschrijvingAanDeelnemerswaarde` over alle "
            "rijen getoond als totale deelnemerswaarde."
        ),
    },
    "na_1okt": {
        "titel": "Inschrijvingen na 1-oktober",
        "variabelen": ["DatumInschrijving", "BRIN", "_persoon_id"],
        "manipulatie": (
            "Telt de inschrijvingen (persoon × instelling × volgnummer, elk één "
            "keer) waarvan `DatumInschrijving` in een geselecteerd schooljaar ná "
            "1 oktober valt.  Ze tellen dat schooljaar niet mee op de peildatum "
            "en dus niet voor de 1-oktober-bekostiging (#201)."
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
            "Elke inschrijvingsperiode wordt op basis van `BPV_Aantal` (> 0; "
            "BPV's die in die periode begonnen) ingedeeld als 'Met BPV' of "
            "'Zonder BPV'.  Daarna wordt het aantal per combinatie van "
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
            "apart getoond." + _DETAIL_SELECTIE
        ),
    },
    "kzd": {
        "titel": "KZD-behaaldverhouding per levering",
        "variabelen": ["levering", "KZD_Aantal", "KZD_AantalBehaald"],
        "manipulatie": (
            "Alleen inschrijvingsperioden met minimaal één KZD-resultaat tellen "
            "mee.  Per periode wordt het percentage behaalde onderdelen berekend "
            "(`KZD_AantalBehaald / KZD_Aantal × 100`), waarna per levering het "
            "gemiddelde over die perioden wordt getoond.  Elk keuzedeel telt in "
            "precies één periode (op `DatumResultaat`)."
        ),
    },
    "kzd_detail": {
        "titel": "Keuzedelen — resultaten per code",
        "variabelen": ["fact_kzd.CodeKeuzedeel", "fact_kzd.Behaald"],
        "manipulatie": (
            "Gelezen uit `fact_kzd` (grain: één rij per keuzedeel per inschrijving).  "
            "Per keuzedeel-code (`CodeKeuzedeel`) wordt het totaal en het aantal "
            "behaalde resultaten geteld.  `Behaald` is in de pipeline exact bepaald "
            "uit de DUO-waardenlijst (`Behaald`/`Niet behaald`); een onbekende "
            "waarde telt niet als behaald.  Top-15 op volume." + _DETAIL_SELECTIE
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
            + _DETAIL_SELECTIE
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
            "vertaald naar een leesbare naam." + _DETAIL_SELECTIE
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
            "een leesbare naam." + _DETAIL_SELECTIE
        ),
    },
    "amo": {
        "titel": "AMO-onderdelen",
        "variabelen": ["AMO_Aantal"],
        "manipulatie": (
            "Telt het totaal aantal examenvakken voor de arbeidsmarktgerichte "
            "opleidingsdelen (`AMO_Aantal`) en het gemiddelde per "
            "inschrijvingsperiode met AMO-onderdelen; elk onderdeel telt in "
            "precies één periode (op `DatumResultaat`)."
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
