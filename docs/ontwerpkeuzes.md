# Ontwerpkeuzes

De tool levert twee producten (zie [Home](index.md#wat-levert-de-tool-op)):

- **Brondata per levering** (`data/02-prepared/`): elk DUO-bestand per recordtype,
  getrouw aan de levering. Hierin zitten alleen **technische** keuzes: typering,
  herkenning van scheidingsteken en datumformaat, normalisatie van notaties.
- **Analysemodel** (`star/datamodel/`): de leveringen samengevoegd tot dimensies en
  feiten. Hierin zitten **inhoudelijke** keuzes: antwoorden op vragen die de bron zelf
  niet beantwoordt. Die keuzes staan hieronder, elk met een reden en een alternatief.

Wie het analysemodel gebruikt, neemt deze keuzes over. Wie een andere keuze wil,
bouwt verder op de brondata.

!!! note "Bijhouden"
    Elke wijziging die een keuze in het analysemodel toevoegt of verandert, werkt
    deze pagina bij (zie de PR-template).

## Brondata

| Keuze | Waarom | Alternatief | Gevolg | Code | Issue |
|---|---|---|---|---|---|
| Veldindeling per recordtype uit het PvE (`metadata/*_schema.toml`), positioneel | DUO-bestanden hebben geen kolomkoppen | — | Een verschoven veld valt niet op door parsen; daarom de controles hieronder | `ingest.py` | #127 |
| Afwijkingen van het PvE die echte leveringen hebben, volgen de data: VLP-`BRIN`, RO-DIP positie 7 | Echte bestanden wijken af van de spec | Strikt het PvE volgen | Gedocumenteerd per recordtype | `*_schema.toml` | #127 |
| Onbekende recordtypes, velden voorbij het schema en ontbrekende **verplichte** achtervelden **breken de ingest** | Hun betekenis staat niet in het PvE, of de regel is afgeknipt; stil afknippen of aanvullen verbergt een verkeerd bestand | Niet inlezen, wel tellen; korte regels altijd aanvullen | Fail-closed; alleen de `optionele_achtervelden` (PvE "Verplicht: Nee") mogen aan het eind ontbreken | `ingest.read_multi_record_csv` | #120, #257, #281 |
| Posities buiten het PvE die in echte leveringen staan (GRONDSLAG-PER 19–21) worden **bewaard als `<veld>_positie<n>`**, niet geïnterpreteerd | Kopie of eerdere waarde? Het PvE zegt het niet | Niet inlezen (verlies) of als vorige waarde benoemen | Verschillen in `quality.json` → `regelinventaris`; niet in het analysemodel | `metadata.extra_kolommen` | #260 |
| Waardedomein per veld (patroon of waardenlijst) wordt gecontroleerd; `BRIN` in elk recordtype | Een verschoven veld is vaak alleen aan zijn waarden te zien (bijv. een ontbrekend middenveld, dat de regel maar één veld korter maakt) | Geen controle | `quality.json` → `domeinafwijkingen` | `waardenlijsten.py` | #205, #238, #281 |
| Datum met onbekende dag/maand (`00`) → 1e van maand/jaar + `_precisie` | Het PvE staat `00` toe bij `Geboortedatum` | Null (verlies van het jaar) | Kolom `Geboortedatum_precisie` | `decode.py` | #206 |
| Decimaalteken punt én komma bij bedragen/factoren | Het PvE noemt het teken niet | Alleen punt | — | `decode._to_float_expr` | #208 |
| `IndicatieBekostigbaar` `J`/`1`/`true` → `J`, `N`/`0`/`false` → `N` | Drie bronnen, drie notaties | Per bron laten | Eén notatie in alle lagen | `waardenlijsten.toml` | — |

!!! warning "Nog geen deelbaar product"
    De brondata bevat nog `Burgerservicenummer` en `Onderwijsnummer` in platte tekst;
    pseudonimisering gebeurt pas bij het bouwen van het analysemodel (#173). De app
    verbergt ze standaard.

## Analysemodel

| Keuze | Waarom | Alternatief | Gevolg | Code | Issue |
|---|---|---|---|---|---|
| **Canonicalisatie**: per inschrijving (`BRIN × persoon × volgnummer`) wint de levering met de hoogste VLP-`DatumAanmaak`, daarna de alfabetisch laatste naam | Een levering is een bronbestand, geen tellingseenheid | Alle leveringen optellen (dubbeltellingen) | Oudere leveringen van een inschrijving vallen weg, ook in de detailfeiten; lineage in `meta_canonicalisatie` | `canonicalisatie.py` | #134, #175 |
| **Pseudonimisering met identifierdomein** (BSN ≠ ONr ≠ PGN) | Hetzelfde nummer in een ander domein is een andere persoon | Alleen het nummer hashen (valse koppelingen) | RO/TBG-i (BSN/ONr) koppelen niet aan GRONDSLAG (PGN) | `transform._add_persoon_id` | #128 |
| **Periode-einde** = vroegste van volgende `DatumBegin` − 1, `DatumEind`, `DatumUitschrijvingWerkelijk` | Een uitgeschreven inschrijving is nooit meer actief | Alleen volgende periode | Perioden overlappen niet | `transform._voeg_periode_einde_toe` | #163 |
| **Peildatum 1 oktober**, begrensd door wat de levering kan waarnemen (`DatumEindePeriode`, anders `DatumAanmaak`) | Een levering zegt niets over later | Doortellen tot vandaag | Observatievenster in `meta_leveringen`; levering zonder schooljaar gemeld | `schooljaar.py` | #164, #193, #211 |
| **TBG-i**: een inschrijving telt op haar 1-oktober-`Teldatum`; attributen komen van de teldatum | TBG-i levert inschrijvingen, geen perioden (PvE §16.1) | `DatumInschrijving` als begin | Schooljaar volgt de bekostigingswaarneming | `schooljaar._tbgi_waarnemingen` | #197 |
| **Centrale laag**: ISP-perioden plus TBG-i-inschrijvingen die daar niet al staan | ISP is rijker; TBG-i vult aan | Alleen ISP (TBG-i-feiten zonder parent) | Kolom `Bron` (`ISP`/`TBGI`) | `transform._tbgi_zonder_isp` | #196 |
| **Hoofdinschrijving**: per persoon × BRIN × schooljaar hoogste niveau, dan laagste CREBO, dan recentste `DatumBegin` | De deelnemer telt één keer | Alle inschrijvingen tellen | `_hoofdinschrijving` = `_telling` | `schooljaar._voeg_hoofdinschrijving_toe` | #130 |
| **Niveau-aanvulling**: bron → `crebo.csv` → S-BB → onbekend, met `_niveau_herkomst` | RO levert vaak geen niveau | Leeg laten | Hoofdinschrijving en JR/DR hangen af van referentiedata zonder peildatum | `enrich.py`, `transform._vul_niveau_aan` | #132 |
| **Koppelkeuze** bij meerdere kandidaten: inhoudelijke voorkeur (DIP: recentste `DatumResultaat`), anders op inhoud gesorteerd | Nooit afhankelijk van de rijvolgorde in een bestand | Eerste rij in het bestand | `meta_koppelkeuzes`; warning in `quality.json` | `koppelingen.py` | #209 |
| **Detailfeiten** zonder of met vroege referentiedatum → eerste periode van de inschrijving | Anders geen parent | Wees laten | Stille imputatie (nog open) | `transform._koppel_periode_id` | #121 |
| **GRONDSLAG-BID** in `fact_bekostiging_diploma`, met inschrijving, opleiding en `DatumBehaald` van het DIP-record (`Resultaatvolgnummer`, binnen levering en BRIN) | BID mist die velden (PvE §17.5); één concept, één feit met TBG-i-Diploma (#208) | BID niet opnemen en melden | Kolom `Bron` (`BID`/`TBGI`); koppelkeuze `BID.DIP` in `meta_koppelkeuzes` | `transform._bid_met_dip` | #258 |
| **Relatiecontract per feit**: parent verplicht, behalve bij TBG-i-diploma's | TBG-i levert diploma's los van inschrijvingen (PvE §16.1) | Overal verplicht | Verklaarde wees-rijen geen error; een BID zonder inschrijving is wel een error | `quality._OPTIONELE_PARENT` | #196, #258 |
| **Uniciteitscontracten** per feit; bronfouten worden gemeld, niet stil ontdubbeld | Stil ontdubbelen verbergt de bronfout | Deduplicatie | Error in `quality.json` | `quality._UNICITEIT` | #200 |
| **Dimensies**: per sleutel de eerste niet-lege waarde over leveringen, meest gevulde levering eerst; rij zonder sleutel valt weg | Leveringen vullen verschillende velden | Eén levering kiezen | Een attribuut kan uit een andere levering komen dan de feitrij | `star._build_dim` | #196 |
| **JR/DR** zijn benaderingen: DR zonder zesjaarsvenster en alleen binnen hetzelfde BRIN | Formele definitie vraagt meer historie | — | Indicatief; zo gelabeld in dashboard | `schooljaar._voeg_jr_toe`, `_voeg_dr_toe` | #118, #119 |
| **Entree** (niveau 1): populatie = entree-hoofdinschrijving in schooljaar t die Entree verlaat, met t+1 waarneembaar; doorstroom = niveau ≥ 2 bij dezelfde BRIN in t+1, uitstroom = daar niet meer ingeschreven; diploma in t | Zelfde t+1-waarneming als DR; één student telt één keer per schooljaar | Per ISP-periode tellen (dubbeltelling bij meerdere perioden); uitschrijvingsdatum als uitstroom | Wie in Entree blijft, telt niet mee | `schooljaar._voeg_entree_toe` | #306 |
| **Legacy periode-vlaggen** in `fact_inschrijving` naast de schooljaar-fact, gemarkeerd als verouderd | Achterwaartse compatibiliteit: afnemers krijgen één release om te migreren | Direct verwijderen | Twee bronnen van waarheid tot v4.0.0; de app leest ze niet meer; `quality.json` → `star.verouderde_kolommen` | `transform.VEROUDERDE_KOLOMMEN` | #201 |
