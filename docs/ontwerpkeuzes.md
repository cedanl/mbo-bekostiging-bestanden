---
icon: lucide/compass
---

# Ontwerpkeuzes

De tool levert twee producten (zie [Home](producten/brondata.md)):

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

### Veldindeling per recordtype uit het PvE

**Keuze:** Veldindeling per recordtype uit het PvE (`metadata/*_schema.toml`), positioneel

**Waarom:** DUO-bestanden hebben geen kolomkoppen

**Gevolg:** Een verschoven veld valt niet op door parsen; daarom de controles hieronder

**Code:** `ingest.py`

**Issue:** #127

### PvE-versie staat in één manifest

**Keuze:** De **PvE-versie** staat alleen in `metadata/pve_bron.json`, met de sha256 van de beknopte extractie; schema's herhalen haar niet. Een nieuwe versie gaat via `scripts/vergelijk_pve.py` (per pagina, zonder versiestrings)

**Waarom:** Versies stonden in drie schema's en het manifest, en een upgrade was een handmatige doorloop

**Alternatief:** Versie per schema

**Gevolg:** Eén wijziging per upgrade; wijzigingsoverzicht in `docs/pve-wijzigingen.md`

**Code:** `metadata.pve_bron`, `scripts/vergelijk_pve.py`

**Issue:** #298, #299

### Afwijkingen van het PvE volgen de data

**Keuze:** Afwijkingen van het PvE die echte leveringen hebben, volgen de data: VLP-`BRIN`, RO-DIP positie 7

**Waarom:** Echte bestanden wijken af van de spec

**Alternatief:** Strikt het PvE volgen

**Gevolg:** Gedocumenteerd per recordtype

**Code:** `*_schema.toml`

**Issue:** #127

### Twee layouts waar PvE en praktijk verschillen

**Keuze:** Waar echte leveringen en het PvE allebei voorkomen (GRONDSLAG-VLP met/zonder `BRIN`, RO-DIP met/zonder positie 7), kent het schema **beide layouts**; de ingest kiest per regel op lengte en de domeinen van de `herkenning`-velden

**Waarom:** Alleen de praktijkvariant verschoof een officiële regel stil (DIP) of wees hem af (VLP)

**Alternatief:** Eén layout kiezen; per bestand configureren

**Gevolg:** Geen of meer dan één passende layout, of gemengde layouts in één bestand, is een error. De kolomset is die van de praktijkvariant; de gekozen variant staat in `quality.json` → `layoutvarianten`. De officiële VLP haalt `BRIN` uit de bestandsnaam (PvE §17.3); dat staat erbij als `uit_bestandsnaam`

**Code:** `ingest._kies_layout`, `varianten` in `*_schema.toml`

**Issue:** #236, #321

### Onbekende recordtypes en velden breken de ingest

**Keuze:** Onbekende recordtypes, velden voorbij het schema en ontbrekende **verplichte** achtervelden **breken de ingest**

**Waarom:** Hun betekenis staat niet in het PvE, of de regel is afgeknipt; stil afknippen of aanvullen verbergt een verkeerd bestand

**Alternatief:** Niet inlezen, wel tellen; korte regels altijd aanvullen

**Gevolg:** Fail-closed; alleen de `optionele_achtervelden` (PvE "Verplicht: Nee") mogen aan het eind ontbreken

**Code:** `ingest.read_multi_record_csv`

**Issue:** #120, #257, #281

### Posities buiten het PvE bewaren

**Keuze:** Posities buiten het PvE die in echte leveringen staan (GRONDSLAG-PER 19–21) worden **bewaard als `<veld>_positie<n>`**, niet geïnterpreteerd

**Waarom:** Kopie of eerdere waarde? Het PvE zegt het niet

**Alternatief:** Niet inlezen (verlies) of als vorige waarde benoemen

**Gevolg:** Verschillen in `quality.json` → `regelinventaris`; niet in het analysemodel

**Code:** `metadata.extra_kolommen`

**Issue:** #260

### Waardedomein per veld controleren

**Keuze:** Waardedomein per veld (patroon of waardenlijst) wordt gecontroleerd; `BRIN` in elk recordtype. **Elk** RO- en GRONDSLAG-veld heeft een domein, een type (datum/getal: parseverlies) of een vastgelegde reden zonder domein (`[geen_domein]`). Staat de PvE-lijst niet in de beknopte PDF, dan alleen een formaatdomein

**Waarom:** Een verschoven veld is vaak alleen aan zijn waarden te zien (bijv. een ontbrekend middenveld, dat de regel maar één veld korter maakt)

**Alternatief:** Geen controle; lijsten uit secundaire bronnen overnemen

**Gevolg:** `quality.json` → `domeinafwijkingen` en `domeindekking`; nieuwe domeinen zijn `warning`, demo blijft op 0 afwijkingen

**Code:** `waardenlijsten.py`

**Issue:** #205, #238, #281, #288

### Tijdsgebonden waarden toetsen op de peildatum

**Keuze:** **Tijdsgebonden waarden** (PvE §16.6: Leertraject, Leerroutefase) worden getoetst op de `peildatum` van het recordtype (ISP: `DatumBegin`, TBG-i: `Teldatum`); `vanaf`/`tot` inclusief

**Waarom:** `BOL_DT` na 31-07-2023 of `VO` vóór 01-08-2020 bestaat niet, maar een tijdloos domein accepteerde het

**Alternatief:** Tijdloze domeinen; toetsen op de leveringsdatum

**Gevolg:** `buiten_geldigheid` en `zonder_peildatum` staan naast `aantal` (de echte domeinschendingen) en geven alleen een warning, ook in een error-domein: de waarde bestond in die periode (#360); rijen zonder peildatum krijgen geen toets maar staan als `zonder_peildatum` in `quality.json`. Alleen periodes die het PvE noemt

**Code:** `waardenlijsten._buiten_geldigheid`, `geldigheid` in `waardenlijsten.toml`, `peildatum` in `*_schema.toml`

**Issue:** #325

### Kwaliteitsstatus fail is een publicatiepoort

**Keuze:** Quality-status `fail` is een **publicatiepoort**: `run_star` en `mbo star` falen (exit 3) na het schrijven van ster en `quality.json`; `--allow-quality-errors` / `fail_on_errors=False` is de override

**Waarom:** Afnemers die op exitcode of UI-succes afgaan namen een product met errors als geslaagd mee

**Alternatief:** Alleen melden (voorheen); ster niet schrijven bij `fail` (dan is de diagnose weg)

**Gevolg:** De ster staat er bij een fout wel, als diagnose in `diagnose/` (zie hieronder); de override staat in `provenance.kwaliteitsfouten_toegestaan`. De app bouwt door en toont Home als fout, niet als succes

**Code:** `pipeline.run_star`, `quality.KwaliteitsFout`

**Issue:** #289, #290

### De ster atomair publiceren

**Keuze:** De ster wordt **atomair gepubliceerd** via een staging-map: alleen bij `pass`/`warn` of met de override komt ze in `datamodel/` + `quality.json`; anders in `diagnose/`. `publicatie.lees_ster` weigert standaard een ster met status `fail`

**Waarom:** Een downstream-proces dat alleen naar bestanden kijkt, zag een volledig ogende `datamodel/` ook bij `fail`, of een halve na een onderbroken run

**Alternatief:** Een vlag `publiceerbaar: false` in `quality.json` naast een `datamodel/` met fail-output: elke afnemer moet dan eerst het rapport lezen, en een onderbroken run blijft half

**Gevolg:** `datamodel/` is nooit half geschreven; een mislukte of onderbroken run laat de vorige publicatie staan. `provenance.gepubliceerd` zegt of het rapport bij een publicatie hoort. Bestaande paden blijven gelijk; nieuw is alleen `diagnose/`, dat een geslaagde publicatie weer opruimt

**Code:** `publicatie.py`, `pipeline.run_star`

**Issue:** #363

### Brondata per levering atomair publiceren

**Keuze:** De **brondata per levering** wordt ook atomair gepubliceerd: de pipeline bouwt naast de doelmap en vervangt die pas na de kwaliteitspoort in zijn geheel; bij `fail` zonder override komen tabellen en `quality.json` in `<doel>/diagnose/`

**Waarom:** Een herverwerking liet tabellen van de vorige bron staan (AMO/ISE), en een foute run had de vorige geldige Parquets en `quality.json` al overschreven

**Alternatief:** Per bestand overschrijven en verdwenen tabellen verwijderen: niet atomair, en een fout laat nog steeds een halve map achter

**Gevolg:** De brondatamap bevat altijd precies één run. Een doelmap die niet leeg is en geen `quality.json` of `diagnose/` heeft, wordt geweigerd, zodat een verkeerd gekozen map niet leeg raakt. De app slaat `diagnose/` over bij het zoeken naar brondata

**Code:** `publicatie.publiceer_brondata`, `pipeline._run`

**Issue:** #414, #415

### Pseudoniem bij decode

**Keuze:** **Pseudoniem bij decode**: BSN, onderwijsnummer en PGN worden in `decode_frames` vervangen door `_persoon_id`; `mbo verwerk` vereist de salt. De ruwe levering in `01-raw` blijft de auditbron

**Waarom:** De brondata bevatte identifiers in platte tekst en was zo niet deelbaar; elke laag moest ze zelf weghalen (#172, #212)

**Alternatief:** Een bridge-tabel identifier ↔ pseudoniem, of twee uitvoerprofielen (audit en analyse): een extra bestand met identifiers dat beheerd moet worden, terwijl `01-raw` die rol al heeft

**Gevolg:** Brondata en ster bevatten geen identifiers (behalve in de opt-in modus `identifiers_behouden`, #435); de sterbouw kent alleen `_persoon_id`. Alle leveringen in één ster moeten met dezelfde salt verwerkt zijn. Brondata van vóór v4.0.0 weigert `stack_prepared`: opnieuw verwerken

**Code:** `identiteit.pseudonimiseer`, `decode.decode_frames`, `stack._lees_levering`

**Issue:** #173

### Persoonsverwerking is een expliciete keuze

**Keuze:** **Persoonsverwerking is een expliciete keuze** (`identiteit.Persoonsverwerking`): `pseudonimiseren` (standaard; fail-closed zonder salt) of `identifiers_behouden` (opt-in: BSN/ONR/PGN blijven in de brondata, `dim_deelnemer` krijgt ze, geen salt nodig). Een ontbrekende salt schakelt de tweede modus nooit in

**Waarom:** BI-teams in een vertrouwde omgeving moeten DUO-data intern aan een eigen administratie koppelen en hebben daarvoor de identifier nodig

**Alternatief:** Een ontbrekende salt als schakelaar (stil lek: een vergeten salt zou persoonsgegevens laten staan); een bridge-tabel identifier ↔ pseudoniem; salt-opslag of autorisatie (buiten scope)

**Gevolg:** In deze modus is `_persoon_id` een ongezouten SHA-256 per identifierdomein: een stabiele join-sleutel, geen privacybescherming. Het profiel staat per levering en in de ster in `quality.json` (`privacyprofiel`); leveringen met verschillende profielen in één ster zijn een fout, en brondata met identifiers zonder dat profiel blijft geweigerd. Identifiers staan alleen in `dim_deelnemer` en zijn in preview en download standaard verborgen

**Code:** `identiteit.pseudonimiseer`, `pipeline._identifiers_behouden`, `star.build_star`

**Issue:** #435

### Lege waarden in verplichte velden

**Keuze:** **Lege waarden** in een PvE-verplicht veld (`verplichte_velden` per recordtype in het schema: "Verplicht: Ja" in §15.5/§16.5, "V" in §17.5) zijn een `error`, ook zonder waardedomein; een gevulde `_onbekend`-positie in RO-DIP ook. Uitzonderingen volgen de leveringen: TBG-i-Diploma `NiveauHoogstBekostigdeDiploma`/`IndicatieHoogstBekostigdeDiplomaIsSpecialist` (geen eerder diploma, geen waarde) en GRONDSLAG-KZD `Certificaat`; BRIN is ook verplicht waar het PvE het niet in de tabel noemt (GRONDSLAG-VLP-praktijklayout, TBG-i-kinderen)

**Waarom:** Een lege BRIN liet de instelling stil uit de ster verdwijnen bij status `pass` (#320); daarna bleken andere PvE-verplichte velden (VLP `DatumEindePeriode`, ISP `Opleidingcode`, TBG-i-Diploma `Inschrijvingvolgnummer`) leeg door te gaan, omdat verplichtheid aan het domein hing in plaats van aan het veld (#416, #419). `_onbekend` kan alleen door een verschuiving gevuld zijn (sinds #321 houdt de layoutherkenning zo'n regel al bij de ingest tegen; de domeincontrole is het vangnet)

**Alternatief:** Verplichtheid per domein (voorheen): mist elk verplicht veld zonder domein, en een domein dat in een optioneel veld terugkomt (GRONDSLAG-DIP `IndicatieBekostigbaar`) werd ten onrechte verplicht

**Gevolg:** Melding noemt het aantal lege waarden apart (`leeg`); demo blijft op 0 errors. GRONDSLAG-DIP `IndicatieBekostigbaar` is nu optioneel (PvE "O"). De domeinen `datum_verplicht` en `boolean_optioneel` zijn vervallen

**Code:** `waardenlijsten.controleer_waardedomeinen`, `verplichte_velden` in `*_schema.toml`

**Issue:** #320, #287, #416, #419

### Parseverlies is een error

**Keuze:** **Parseverlies** (een gevulde datum of getal die niet parseert) is een `error`, niet langer een warning

**Waarom:** De waarde werd null terwijl de run met exit 0 slaagde: stil dataverlies in de brondata

**Alternatief:** Alleen voor verplichte velden blokkeren en optionele in quarantaine zetten: het schema legt voor datum- en getalvelden geen verplichting vast, en quarantaine is een eigen voorziening

**Gevolg:** Elke gevulde, onparseerbare waarde blokkeert; `--allow-quality-errors` blijft de override. Gedeeltelijke datums (`00`) zijn geen parseverlies (#206). Demo blijft op 0 errors

**Code:** `quality.QualityReport.meld_parseverlies`

**Issue:** #390

### Datumnotatie per cel herkennen

**Keuze:** De **datumnotatie** (`ccyy-mm-dd`, `ccyymmdd`, `d-m-ccyy`) wordt per cel herkend; een cel in een andere notatie wordt null en telt als parseverlies

**Waarom:** De notatie werd uit één voorbeeldcel voor het hele bestand gekozen: een lege of ongeldige eerste datum maakte alle andere datums null, en `1-8-25` werd stil het jaar 25

**Alternatief:** Eén notatie per bestand met een duidelijke fout bij menging: verwerpt een levering waarvan elke waarde eenduidig is

**Gevolg:** Gemengde notaties parsen allemaal; een afwijkende cel kost alleen zichzelf

**Code:** `decode._NOTATIES`

**Issue:** #417

### Verplichte recordtypes moeten voorkomen

**Keuze:** Recordtypes met `verplicht = true` in het schema (VLP, PER, ISG, ISP, SLR) moeten voorkomen

**Waarom:** Zonder PER of ISG crashte `build_star` met een kale `KeyError`; de SLR toonde al `gelezen 0`

**Alternatief:** Controle pas in `build_star`

**Gevolg:** De ingest faalt met bestand en recordtype; DIP, GEO e.d. mogen ontbreken

**Code:** `validate.py`, `*_schema.toml`

**Issue:** #322

### TBGI krijgt dezelfde waardedomeinen

**Keuze:** TBGI (XML) krijgt dezelfde waardedomeinen als RO/GRONDSLAG (BRIN, Opleidingcode, Niveau, Leertraject, Leerroutefase, Status bepaling, IndicatieBekostigbaar); alleen BRIN is `error`, de rest `warning`

**Waarom:** XML heeft geen posities die kunnen verschuiven, maar een verminkte waarde bleef ongemerkt (PvE §16.6)

**Alternatief:** Niveau en leertraject ook op `error`: dat verandert dan ook RO/GRONDSLAG, waar ze dezelfde domeinen delen

**Gevolg:** Geen nieuwe meldingen op de demo. Elk TBG-i-veld heeft een domein, een type of een vastgelegde reden in `[geen_domein]` (Signaalvelden, volgnummers), zoals bij RO en GRONDSLAG (#356)

**Code:** `tbgi_schema.toml`

**Issue:** #323

### Onbekend XML-element melden

**Keuze:** Een XML-element buiten het schema wordt **gemeld** (warning, `regelinventaris.onbekende_xml_elementen`), niet afgewezen

**Waarom:** DUO mag XML uitbreiden; stil negeren verborg een nieuw veld

**Alternatief:** Ingest laten breken zoals bij CSV

**Gevolg:** Het element staat als ruwe XML met groep en plaats in de brondatatabel `OnbekendeXML` (alleen als er zo'n element is, #420); groep en tagnaam staan in `quality.json`. Het analysemodel neemt de tabel niet over: de inhoud is ongeïnterpreteerd en kan persoonsgegevens bevatten. Ook een element binnen een bladelement telt, met het blad als groep (`<Inschrijvingvolgnummer><Deel/>` → groep `Inschrijvingvolgnummer`): de tekstwaarde van het blad blijft gelezen, het kind niet (#359)

**Code:** `ingest.inventariseer_xml_elementen`, `contracts.ONBEKENDE_XML`

**Issue:** #324, #359, #420

### Genest XML-element zonder waarde

**Keuze:** Een schemaveld met een **genest element en zonder eigen waarde** (`<Opleidingcode><Deel>…</Deel></Opleidingcode>`) is een `error`, met veld en plaats (`regelinventaris.onleesbare_xml_velden`)

**Waarom:** De waarde zat in het kind en verdween; de melding was een generieke warning zonder veld of rij

**Alternatief:** Alleen bij een verplicht veld een error (dat vangt #419 al als `leeg`), anders warning

**Gevolg:** Waardeverlies blokkeert, net als parseverlies. De plaats is een `Tag[n]/`-pad vanaf het record, zonder persoonsgegevens; maximaal 10 per veld. Een blad mét eigen waarde en een kind blijft een uitbreiding (warning, #359)

**Code:** `ingest.inventariseer_xml_elementen`, `QualityReport.meld_regelinventaris`

**Issue:** #421

### Onbekende dag of maand in een datum

**Keuze:** Datum met onbekende dag/maand (`00`) → 1e van maand/jaar + `_precisie`

**Waarom:** Het PvE staat `00` toe bij `Geboortedatum`

**Alternatief:** Null (verlies van het jaar)

**Gevolg:** Kolom `Geboortedatum_precisie`

**Code:** `decode.py`

**Issue:** #206

### Datum met jaar 0000

**Keuze:** Datum met jaar `0000` → null; bij een `_precisie`-veld met precisie `onbekend` en een `warning`, anders parseverlies

**Waarom:** Jaar 0 bestaat niet: als `0000-01-01` liet Parquet het door, maar consumenten crashten (`year 0 is out of range`)

**Alternatief:** `0000-01-01` behouden; `0001-01-01` als plaatsvervanger (verzonnen datum)

**Gevolg:** `quality.json` → `onbekende_datums`; geen error, want de bron levert de waarde bewust als onbekend

**Code:** `decode.py`, `quality.tel_onbekende_datums`

**Issue:** #391

### Decimaalteken punt en komma

**Keuze:** Decimaalteken punt én komma bij bedragen/factoren

**Waarom:** Het PvE noemt het teken niet

**Alternatief:** Alleen punt

**Code:** `decode._to_float_expr`

**Issue:** #208

### IndicatieBekostigbaar normaliseren

**Keuze:** `IndicatieBekostigbaar` `J`/`1`/`true` → `J`, `N`/`0`/`false` → `N`

**Waarom:** Drie bronnen, drie notaties

**Alternatief:** Per bron laten

**Gevolg:** Eén notatie in alle lagen

**Code:** `waardenlijsten.toml`


!!! note "Pseudoniem bij decode"
    Decode vervangt `Burgerservicenummer`, `Onderwijsnummer` en `PseudoNummer` (PGN)
    door het pseudoniem `_persoon_id` (#173); de brondata bevat ze niet. Ze blijft
    persoonsgegevens (pseudoniemen, geboortedatum, postcodecijfers). De ruwe levering
    in `01-raw` is de auditbron.

## Analysemodel

### Canonicalisatie

**Keuze:** **Canonicalisatie**: per inschrijving (`BRIN × persoon × volgnummer`) wint de levering met de hoogste VLP-`DatumAanmaak`, daarna de alfabetisch laatste naam

**Waarom:** Een levering is een bronbestand, geen tellingseenheid

**Alternatief:** Alle leveringen optellen (dubbeltellingen)

**Gevolg:** Oudere leveringen van een inschrijving vallen weg, ook in de detailfeiten; lineage in `meta_canonicalisatie`

**Code:** `canonicalisatie.py`

**Issue:** #134, #175

### Pseudonimisering met identifierdomein

**Keuze:** **Pseudonimisering met identifierdomein** (BSN ≠ ONr ≠ PGN)

**Waarom:** Hetzelfde nummer in een ander domein is een andere persoon

**Alternatief:** Alleen het nummer hashen (valse koppelingen)

**Gevolg:** RO/TBG-i (BSN/ONr) koppelen niet aan GRONDSLAG (PGN)

**Code:** `identiteit.pseudonimiseer`

**Issue:** #128

### Periode-einde

**Keuze:** **Periode-einde** = vroegste van volgende `DatumBegin` − 1, `DatumEind`, `DatumUitschrijvingWerkelijk`

**Waarom:** Een uitgeschreven inschrijving is nooit meer actief

**Alternatief:** Alleen volgende periode

**Gevolg:** Perioden overlappen niet

**Code:** `perioden.voeg_periode_einde_toe`

**Issue:** #163

### Peildatum 1 oktober

**Keuze:** **Peildatum 1 oktober**, begrensd door wat de levering kan waarnemen (`DatumEindePeriode`, anders `DatumAanmaak`)

**Waarom:** Een levering zegt niets over later

**Alternatief:** Doortellen tot vandaag

**Gevolg:** Observatievenster in `meta_leveringen`; levering zonder schooljaar gemeld

**Code:** `schooljaar.py`

**Issue:** #164, #193, #211

### TBG-i telt op de 1-oktober-teldatum

**Keuze:** **TBG-i**: een inschrijving telt op haar 1-oktober-`Teldatum`; attributen komen van de teldatum

**Waarom:** TBG-i levert inschrijvingen, geen perioden (PvE §16.1)

**Alternatief:** `DatumInschrijving` als begin

**Gevolg:** Schooljaar volgt de bekostigingswaarneming. Een TBG-i-inschrijving zonder (gevulde) `Teldatum`, zoals een niet-bekostigde inschrijving waarvan DUO een leeg `<Teldatum>` levert (#445), staat wel in `fact_inschrijving` maar niet in `fact_inschrijving_schooljaar`: de inner join op 1-oktober-teldata levert geen schooljaar op, dus ook geen jaarvlaggen of indicatoren (PvE §16)

**Code:** `schooljaar._tbgi_waarnemingen`

**Issue:** #197, #445

### Centrale laag

**Keuze:** **Centrale laag**: ISP-perioden plus TBG-i-inschrijvingen die daar niet al staan

**Waarom:** ISP is rijker; TBG-i vult aan

**Alternatief:** Alleen ISP (TBG-i-feiten zonder parent)

**Gevolg:** Kolom `Bron` (`ISP`/`TBGI`)

**Code:** `inschrijvingen.tbgi_zonder_isp`

**Issue:** #196

### Hoofdinschrijving

**Keuze:** **Hoofdinschrijving**: per persoon × BRIN × schooljaar hoogste niveau, dan laagste CREBO, dan recentste `DatumBegin`

**Waarom:** De deelnemer telt één keer

**Alternatief:** Alle inschrijvingen tellen

**Gevolg:** `_hoofdinschrijving` = `_telling`

**Code:** `schooljaar._voeg_hoofdinschrijving_toe`

**Issue:** #130

### Niveau-aanvulling

**Keuze:** **Niveau-aanvulling**: bron → `crebo.csv` → S-BB → onbekend, met `_niveau_herkomst`

**Waarom:** RO levert vaak geen niveau

**Alternatief:** Leeg laten

**Gevolg:** Hoofdinschrijving en JR/DR hangen af van referentiedata zonder peildatum

**Code:** `enrich.py`, `opleidingsniveau.vul_niveau_aan`

**Issue:** #132

### Koppelkeuze bij meerdere kandidaten

**Keuze:** **Koppelkeuze** bij meerdere kandidaten: per koppeling een regel in `KOPPELREGELS`: `uniek` (het PvE staat één kandidaat toe: PER, ISG, VLP, GEO-pivot, meta), `hoogste` (DIP en BID.DIP: recentste diploma) of `ambigu` (ISE: het PvE staat meerdere perioden toe, de periode-grain heeft één kolomset); daarna op inhoud gesorteerd

**Waarom:** Nooit afhankelijk van de rijvolgorde in een bestand, en de keuze is een vastgelegde businessregel in plaats van een lexicografische toevalstreffer

**Alternatief:** Eerste rij in het bestand; overal dezelfde sortering

**Gevolg:** `meta_koppelkeuzes` met regel en toelichting; in `quality.json` een error bij `uniek` (PvE-schending), anders een warning. Een koppeling zonder regel faalt

**Code:** `koppelingen.py`

**Issue:** #209, #239

### Detailfeiten zonder of met vroege referentiedatum

**Keuze:** **Detailfeiten** zonder of met vroege referentiedatum → eerste periode van de inschrijving, **met koppelstatus**

**Waarom:** Anders geen parent

**Alternatief:** Wees laten

**Gevolg:** Niet stil: `_periode_koppel_status` per rij (`binnen_periode`, `datum_leeg`, `voor_eerste_periode`, `geen_datumkolom`, `geen_inschrijving`), telling in `quality.json` (info), filter in Resultaten

**Code:** `perioden.koppel_periode_id`

**Issue:** #121

### Business key van detailfeiten

**Keuze:** **Detailfeiten**: business key = `levering` + persoon + `Inschrijvingvolgnummer` + eigen volgnummer (`contracts.DETAIL_GRAIN`); `BRIN` altijd aanwezig, uit de parent-inschrijving via `_inschrijving_periode_id`

**Waarom:** `Inschrijvingvolgnummer` is alleen uniek binnen één instelling; RO-detailrecords hebben zelf geen BRIN, dus het schema hing af van de bronmix

**Alternatief:** Key zonder `levering`; BRIN uit de brontabel

**Gevolg:** Dubbele sleutel per detailfeit is een error in `quality.json` → `key_duplicates`; een rij zonder parent houdt haar eigen BRIN (bijv. TBG-i-diploma zonder inschrijving). Een afwijkende bron-BRIN wordt niet stil vervangen: ze staat in `_brin_bron` en is een warning in `star.brin_conflict`

**Code:** `contracts.DETAIL_GRAIN`, `star._met_brin_van_inschrijving`, `quality._UNICITEIT`, `quality._brin_conflict`

**Issue:** #327, #328, #357

### PGN-stabiliteit

**Keuze:** **PGN-stabiliteit** over studiejaren is onbekend; de koppeling neemt aan dat het GRONDSLAG-PGN stabiel is

**Waarom:** DUO heeft het niet bevestigd; een terugval op kenmerken geeft valse matches

**Alternatief:** Fuzzy match op BRIN/geslacht/leeftijd/postcode; GRONDSLAG-jaren niet koppelen

**Gevolg:** `conformiteit.pgn_stabiliteit = "onbekend"`; info-melding bij meerdere GRONDSLAG-studiejaren per instelling (`star.grondslag_studiejaren`)

**Code:** `quality._grondslag_studiejaren`

**Issue:** #128

### GRONDSLAG-BID in fact_bekostiging_diploma

**Keuze:** **GRONDSLAG-BID** in `fact_bekostiging_diploma`, met inschrijving, opleiding en `DatumBehaald` van het DIP-record (`Resultaatvolgnummer`, binnen levering en BRIN)

**Waarom:** BID mist die velden (PvE §17.5); één concept, één feit met TBG-i-Diploma (#208)

**Alternatief:** BID niet opnemen en melden

**Gevolg:** Kolom `Bron` (`BID`/`TBGI`); koppelkeuze `BID.DIP` in `meta_koppelkeuzes`

**Code:** `details._bid_met_dip`

**Issue:** #258

### Relatiecontract per feit

**Keuze:** **Relatiecontract per feit**: parent verplicht, behalve bij TBG-i-diploma's

**Waarom:** TBG-i levert diploma's los van inschrijvingen (PvE §16.1)

**Alternatief:** Overal verplicht

**Gevolg:** Verklaarde wees-rijen geen error; een BID zonder inschrijving is wel een error

**Code:** `quality._OPTIONELE_PARENT`

**Issue:** #196, #258

### Dekking per recordtype

**Keuze:** **Dekking per recordtype**: elk recordtype met eigen feit moet dat feit per levering bereiken; wat bewust geen eigen feit heeft staat met reden in een lijst (TBG-i Signaal en BekostigingsrelevanteBPV alleen in de brondata); DIP, ISE en ISG vullen kolommen van `fact_inschrijving` en tellen als gedekt zodra minstens één van die kolommen gevuld is (#326)

**Waarom:** Een recordtype dat nergens landt, gaf `pass` (#258)

**Alternatief:** Alleen tellingen vergelijken

**Gevolg:** Nul rijen uit een gevulde levering: error bij bekostiging, anders warning; een onbekend recordtype: warning

**Code:** `quality.controleer_dekking`

**Issue:** #295

### Conformiteitsblok in quality.json

**Keuze:** `quality.json` bevat een **conformiteitsblok** (`pve_versie`, `pve_bron_integriteit`, `pve_inhoudelijke_conformiteit`, `indicatoren`, `privacyprofiel`, `pgn_stabiliteit`), in het dashboard onder de status getoond

**Waarom:** `pass` zegt niets over betekenis: proxy-indicatoren en identifiers in brondata bleven onzichtbaar in het artefact

**Alternatief:** Alleen dashboardtekst

**Gevolg:** `indicatoren` komt uit één constante (`quality.INDICATOREN_STATUS`); `pve_inhoudelijke_conformiteit` blijft `niet_beoordeeld` tot de veld- en businessregelconformiteit formeel is afgetekend; de bronintegriteit zelf is sinds #299/#364 een aparte sleutel (`pve_schema` is vervallen)

**Code:** `quality.compile_quality_report`

**Issue:** #331

### Referentiedata met manifest

**Keuze:** **Referentiedata met manifest**: bron, opname, dekking en sha256 per referentietabel in `metadata/referentiedata.json`; de ster neemt het over als `meta_referentiedata`

**Waarom:** Niveau, JR en DR hangen voor RO aan `crebo.csv`/S-BB; welke versie is gebruikt, moet uit de output blijken

**Alternatief:** Versie alleen in git

**Gevolg:** Een test bewaakt dat manifest en inhoud kloppen en dat geen bestand `onbekend` als bron heeft (#316). Waar de bron niet openbaar is (DUO-`Dec_*`-bestanden), staat het bronbestand; de dekking van `crebo.csv` is uit de S-BB-crebolijst afgeleid (`bewerking`), niet geraden. Warning bij afwijkende inhoud, of bij onbekende codes ná de dekking

**Code:** `referentiedata.py`, `quality._check_referentiedata`

**Issue:** #132, #316

### Uniciteitscontracten

**Keuze:** **Uniciteitscontracten** per feit; bronfouten worden gemeld, niet stil ontdubbeld

**Waarom:** Stil ontdubbelen verbergt de bronfout

**Alternatief:** Deduplicatie

**Gevolg:** Error in `quality.json`

**Code:** `quality._UNICITEIT`

**Issue:** #200

### Dimensies

**Keuze:** **Dimensies**: per sleutel de eerste niet-lege waarde over leveringen, meest gevulde levering eerst; rij zonder sleutel valt weg

**Waarom:** Leveringen vullen verschillende velden

**Alternatief:** Eén levering kiezen

**Gevolg:** Een attribuut kan uit een andere levering komen dan de feitrij

**Code:** `star._build_dim`

**Issue:** #196

### JR en DR blijven proxy's

**Keuze:** **JR/DR blijven proxy's; formeel gebruik is uitgesloten**: geen officiële studiesucces-laag (`quality.json` → `conformiteit.indicatoren.*.formeel_gebruik = uitgesloten`)

**Waarom:** De formele indicatoren (Regeling studiesucces mbo) vragen een driejaarscijfer, 1-oktober- en jaartijdvaksemantiek, ≥ 6 jaar historie en instellingsoverstijgende koppeling; de eigen leveringen dekken dat niet

**Alternatief:** Een aparte `official_studiesucces`-laag bouwen (optie A)

**Gevolg:** Uitkomsten zijn indicatief en staan overal als proxy, met hun formele afwijkingen (#369). De regels zelf staan als publieke module `indicatoren` in de package (#294)

**Code:** `quality.INDICATOREN_STATUS`, `indicatoren.py`

**Issue:** #296, #294

### Indicatorpopulatie JR en DR

**Keuze:** **Indicatorpopulatie** JR/DR: niveau ≥ 2 en leertraject niet `OVO`/`ODT` (bijlage 3); de uitsluiting staat bij `domein.leertraject` in `waardenlijsten.toml`

**Waarom:** Eén bron voor de codes: een tweede, handmatige lijst (`ov`/`od`) matchte de echte codes niet

**Alternatief:** Alle leertrajecten meetellen

**Gevolg:** OVO- en ODT-inschrijvingen tellen niet mee in rendement en oordeel

**Code:** `app/indicatoren.populatie_regele_filter`

**Issue:** #286

### DR-teller

**Keuze:** **DR-teller**: diploma op niveau ≥ 2 (niveau van de diplomaopleiding, CREBO dan S-BB) bij de instelling die de student verlaat, behaald van 1-8-(t-5) tot de peildatum 1-10-(t+1); één uitkomst per rij

**Waarom:** Zesjaarsvenster en niveau ≥ 2 uit de inspectiedefinitie; het venster eindigt waar de uitstroom vaststaat, zodat een diploma in augustus of september ná het uitstroomjaar meetelt

**Alternatief:** Venster t/m 31-7-(t+1); diploma's van elke instelling in de dataset; niveau van de inschrijving

**Gevolg:** Diploma zonder bekend niveau of van vóór de eerste levering telt niet; indicatief, zo gelabeld in dashboard

**Code:** `schooljaar._voeg_dr_toe`, `_in_dr_diplomavenster`, `DIPLOMA_GROEP`

**Issue:** #119, #237

### Uitstroom (DR, Entree) instelling-onafhankelijk

**Keuze:** **Uitstroom (DR, Entree) instelling-onafhankelijk**: de persoon wordt in t+1 gezocht bij alle instellingen in de dataset; waarneembaarheid blijft per eigen BRIN

**Waarom:** De inspectiedefinitie kijkt naar het hele mbo, niet naar één instelling

**Alternatief:** Per BRIN met een waarschuwing (optie B)

**Gevolg:** Een overstap binnen de dataset is geen uitstroom; een overstap daarbuiten wel (`quality.json` → `dr_scope`). Een waarneming elders maakt een onwaarneembaar t+1 niet waarneembaar, anders tellen alleen blijvers

**Code:** `schooljaar.VOLGEND_JAAR_GROEP`

**Issue:** #118

### Entree

**Keuze:** **Entree** (niveau 1): populatie = entree-hoofdinschrijving in schooljaar t die Entree verlaat, met t+1 waarneembaar; doorstroom = niveau ≥ 2 in t+1 (instelling-onafhankelijk, #118), uitstroom = nergens meer ingeschreven; diploma in t

**Waarom:** Zelfde t+1-waarneming als DR; één student telt één keer per schooljaar

**Alternatief:** Per ISP-periode tellen (dubbeltelling bij meerdere perioden); uitschrijvingsdatum als uitstroom

**Gevolg:** Wie in Entree blijft, telt niet mee

**Code:** `schooljaar._voeg_entree_toe`

**Issue:** #306

### Geen jaarvlaggen op periode-grain

**Keuze:** **Geen jaarvlaggen op periode-grain**: `fact_inschrijving_schooljaar` is de enige bron voor jaargebonden vlaggen en indicatoren; de periode-varianten in `fact_inschrijving` zijn verwijderd

**Waarom:** Twee kolommen met dezelfde naam gaven verschillende getallen (demo: `_dr_noemer` 19 tegenover 6), en een fix moest op twee plekken

**Alternatief:** Langer laten staan, of hernoemen naar `legacy_*`

**Gevolg:** Breaking in v4.0.0, na markering in v3.2.0–v3.4.0 (`quality.json` → `star.verouderde_kolommen` is met de kolommen vervallen); de app las ze al niet meer

**Code:** `schooljaar.py`

**Issue:** #201

