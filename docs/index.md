# MBO-bekostigingsbestanden

DUO levert aan MBO-instellingen periodiek bestanden waarmee de instelling kan controleren of haar studenten bekostigd worden en op welke grondslag. Deze bestanden zijn technisch van opzet: meerdere recordtypes per bestand, gecodeerde velden, geen kolomkoppen.

**Deze tool leest die ruwe bestanden in en levert twee producten**: de **brondata per levering** (getrouw aan het DUO-bestand) en een **analysemodel** (star schema) dat de leveringen samenvoegt — beide direct bruikbaar in Excel, Python, R of Power BI. Zie [Datamodel](datamodel.md) en [Ontwerpkeuzes](ontwerpkeuzes.md).

---

## Drie bestandstypen

| Bestand | Map | Wat het is |
|---|---|---|
| `RO_*.csv` | `h15/` | Registratieoverzicht – alle inschrijvingen en diploma's in een selectieperiode |
| `TBGI_*.XML` | `h16/` | TBG-i – bekostigingsgrondslagen per inschrijving en diploma, inclusief signalen |
| `GRONDSLAG_IP_MBO_*.csv` | `h17/` | Afslag register-levering IP – bekostigingsrelevante data voor de peildatum 1-10 |

---

## Wat levert de tool op?

| | Brondata per levering | Analysemodel |
|---|---|---|
| Map | `data/02-prepared/<map>/<levering>/` | `data/03-output/<scenario>/star/datamodel/` |
| Wat | Elk DUO-bestand per recordtype | Dimensies en feiten over alle leveringen |
| Keuzes | Alleen technisch (typering, notaties) | Inhoudelijk: canonicalisatie, hoofdinschrijving, peildatum, niveau-aanvulling, … ([Ontwerpkeuzes](ontwerpkeuzes.md)) |
| Gegarandeerd | Kolommen en volgorde volgens het PvE; een onbekend recordtype of gevuld veld voorbij het schema breekt de ingest (fail-closed, #257) in plaats van stil te worden genegeerd | Grain en relaties per tabel ([Datamodel](datamodel.md)); status in `quality.json` |
| Beperkingen | Bevat nog BSN/ONr in platte tekst, en heeft de salt niet nodig (#173); zie [opslag en retentie](aan-de-slag.md#opslag-en-retentie-van-brondata) | JR/DR zijn indicatief: alleen de eigen leveringen (#118, #119); legacy-vlaggen in `fact_inschrijving` (#201) |
| Voor wie | Wie eigen keuzes wil maken of een levering wil controleren | Wie direct wil analyseren met de keuzes van deze tool |

De fasering: `ingest > decode > validate > export` levert de brondata;
`stack > canonicaliseer > transform (pseudonimiseer, koppel) > enrich > schooljaar > star`
levert het analysemodel. Beide stappen schrijven een `quality.json`.

### Stap 1 — Brondata (per leveringsbestand)

Elk ruw bestand wordt genormaliseerd naar één Parquet-bestand per recordtype:

```
data/02-prepared/demo/h15/RO_27DV_20240731_20260324/
├── VLP.parquet    ← bestandskop (1 rij)
├── PER.parquet    ← personen
├── ISG.parquet    ← inschrijvingen
├── ISP.parquet    ← inschrijvingsperiodes
├── BPV.parquet    ← BPV-overeenkomsten
├── DIP.parquet    ← diploma's
├── GEO.parquet    ← generieke examenonderdelen
├── KZD.parquet    ← keuzedelen
└── SLR.parquet    ← sluitrecord (tellingen)
```

Datumvelden zijn `Date`, telvelden zijn `Int64`, lege velden zijn `null` (geen lege strings).

### Stap 2 — Analysemodel: star schema (gecombineerd over alle leveringen)

Alle prepared-mappen worden gecombineerd tot Parquet-bestanden in `data/03-output/star/datamodel/`:

| Bestand | Grain | Inhoud |
|---|---|---|
| `dim_deelnemer.parquet` | Persoon | Persoonskenmerken (geslacht, geboorteland, gemeente …) |
| `dim_opleiding.parquet` | Opleiding | CREBO-attributen incl. S-BB koppeltabel |
| `dim_instelling.parquet` | Instelling | Naam en vestigingsplaats |
| `fact_inschrijving.parquet` | ISP-inschrijvingsperiode | Centrale feittabel op periode-grain met attributen en aggregaten |
| `fact_inschrijving_schooljaar.parquet` | Inschrijving × schooljaar | Actief op 1 oktober, hoofdinschrijving, telling, JR en DR per schooljaar |
| `fact_bpv.parquet` | BPV-overeenkomst | Alle BPV-periodes per inschrijving |
| `fact_kzd.parquet` | Keuzedeel-resultaat | KZD-resultaten per inschrijving |
| `fact_amo.parquet` | AMO-resultaat | AMvB-onderdelen per inschrijving |
| `fact_geo.parquet` | GEO-examenonderdeel | Eindcijfers IE/CE in long format |
| `fact_bekostiging.parquet` | GRONDSLAG BII, TBGI Teldatum | Bekostigingsgrondslagen per teldatum |
| `fact_bekostiging_diploma.parquet` | GRONDSLAG BID, TBGI Diploma | Diplomawaarde-bijdragen per diploma |
| `meta_leveringen.parquet` | Leveringsbestand | VLP + SLR metadata (één rij per bronbestand) |
| `meta_canonicalisatie.parquet` | Leveringspaar | Vervangen leveringen bij overlap (aantallen + reden) |
| `meta_referentiedata.parquet` | Referentiebestand | Bron, opname, dekking en sha256 van de referentietabellen (#132) |
| `meta_koppelkeuzes.parquet` | Koppeling | Per koppeling hoeveel sleutels meer dan één kandidaat hadden, en hoeveel rijen daardoor zijn weggelaten |

Zie [Datamodel](datamodel.md) voor een volledig schema-overzicht.

Een `levering`-kolom in elke tabel geeft aan uit welk bronbestand een rij afkomstig is (bijv. `h15/RO_27DV_20240731_20260324`).

> **Niveau-aanvulling**: Wanneer het veld `Niveau` leeg is (komt voor in RO-bestanden), wordt het automatisch afgeleid uit de CREBO-tabel (`metadata/crebo.csv`) op basis van `Opleidingcode`.

> **Studiejaar-afleiding**: GRONDSLAG levert `Studiejaar` expliciet; voor RO- en TBGI-leveringen wordt het afgeleid uit `DatumBegin` resp. `DatumInschrijving` (maand ≥ 8 → studiejaar = jaar, maand < 8 → studiejaar = jaar − 1). Hierdoor zijn alle bekostigingsvlaggen ook voor RO-data gevuld.

#### Jaarbegrippen

DUO werkt met drie jaarbegrippen die in de data voorkomen:

| Concept | Definitie | In het star schema |
|---|---|---|
| **Studiejaar** | 1 aug jaar *S* – 31 jul jaar *S+1* | Kolom `Studiejaar` (int) in `fact_inschrijving`; expliciet uit GRONDSLAG, afgeleid voor RO/TBGI |
| **Bekostigingsjaar** | Kalenderjaar *T*; refereert aan studiejaar *T−2* voor inschrijvingen | Niet als aparte kolom; `Bekostigingsjaar = Studiejaar + 2` |
| **Kalenderjaar** | Gebruikt door DUO voor diplomaselectie (diploma's in jaar *T−2* voor bekostigingsjaar *T*) | Af te leiden uit `DIP_DatumResultaat` |

"Boekjaar" (fiscaal jaar) is geen DUO-concept en wordt niet gebruikt.

#### Berekende vlaggen in fact_inschrijving

!!! warning "Tel niet op deze vlaggen — gebruik `fact_inschrijving_schooljaar`"
    Deze vlaggen staan op **periode-grain** en zijn verouderd (#201). Een periode die meerdere 1-oktobers dekt,
    telt hier één keer; in de demo telt `_telling` daardoor tot drie rijen per persoon per levering. Voor tellingen
    en rendementen per schooljaar is `fact_inschrijving_schooljaar` de bron (zie [Datamodel](datamodel.md)).

fact_inschrijving voegt per inschrijvingsperiode een reeks berekende vlaggen toe:

| Groep | Kolom | Type | Betekenis |
|---|---|---|---|
| Bekostiging | `_actief_1_oktober` | `Boolean` | ISP omvat 1 oktober van het studiejaar |
| | `_bekostigd_eerste_1okt` | `Boolean` | Actief op 1 oktober EN bekostigbaar (IndicatieBekostigbaar = 'J') |
| | `_gediplomeerd_in_jaar` | `Boolean` | DIP-record aanwezig in het studiejaar |
| | `_ingeschreven_jaar_later` | `Boolean` | Nog ingeschreven in het volgende studiejaar |
| | `_deelnemer_niet_bekostigd_eerste_1okt` | `Boolean` | Actief op 1 okt maar niet bekostigd |
| Selectie | `_hoogste_niveau` | `Boolean` | Hoogste numeriek niveau per persoon × instelling × levering, over de hele historiek (niet per studiejaar) |
| | `_laagste_CREBO` | `Boolean` | Laagste CREBO-code bij gelijk niveau |
| | `_hoofdinschrijving` | `Boolean` | Precies één rij per persoon × studiejaar × instelling × levering: hoogste niveau, dan laagste CREBO, dan meest recente periode |
| Tellingen | `_telling` | `Boolean` | `_actief_1_oktober AND _hoofdinschrijving` — telt de deelnemer mee voor bekostiging |
| Rendement | `_jr_noemer` | `Boolean` | = `_telling`; noemer van het Jaarresultaat |
| | `_jr_teller` | `Boolean` | Noemer AND gediplomeerd_in_jaar (teller van het Jaarresultaat) |
| Entree | `_entree_uitstroom` | `Boolean` | MBO-1 + uitgeschreven (geen actieve ISP meer). Verouderd: gebruik `_entree_*` in `fact_inschrijving_schooljaar` (#306) |
| | `_entree_doorstroom` | `Boolean` | MBO-1 + een hogere inschrijving bij dezelfde instelling. Verouderd, zie hierboven |
| Afgeleid | `Niveau_gecombineerd` | `Utf8` | Niveau + spatie + Leertraject (bijv. `MBO-4 BOL`) |

#### Verrijking via decodeertabellen

Na het berekenen van de vlaggen worden leesbare labels toegevoegd via LEFT JOINs op de
decodeertabellen in `metadata/`:

| Bronkolom | Toegevoegde kolommen | Decodeertabel |
|---|---|---|
| `Nationaliteit1` | `Nationaliteit1_naam`, `Nationaliteit1_migratieachtergrond` | `nationaliteitscode.csv` |
| `Nationaliteit2` | `Nationaliteit2_naam`, `Nationaliteit2_migratieachtergrond` | `nationaliteitscode.csv` |
| `CodeGeboorteland` | `CodeGeboorteland_naam`, `CodeGeboorteland_migratieachtergrond` | `landcode.csv` |
| `Postcodecijfers` | `Gemeente`, `Gemeentecode` | `postcodecijfers.csv` |
| `Opleidingcode` | `Opleiding_naam`, `Opleiding_leerweg`, `Opleiding_domein`, `Opleiding_subgroep`, `Opleiding_dossier`, `Opleiding_sectorkamer` | `crebo.csv` |
| `BRIN` | `Instelling_naam`, `Instelling_plaats` | `brinnummer.csv` |

---

## Ruwe opbouw

Alle CSV-bestanden zijn **multi-record**: elke regel begint met een recordtype-code (`VLP`, `PER`, `ISG`, …). Er zijn geen kolomkoppen.

```
VLP|27DV|2024-07-31|2026-03-24|2026-03-25
PER|BSN1||1987-11-23|V
ISG|BSN1||C3|2023-01-30|2025-01-29||08
```

Lees meer over de inhoud van elk bestand in [Databestanden](databestanden/index.md) of duik direct in de [Recordtypes](recordtypes/index.md).

---

## Bronnen

- Bestandsbeschrijving DUO PvE MBO-instelling v4.8.2 (12-05-2026), `bestandsbeschrijving_beknopt.pdf` in deze repo; versie, datum en sha256 staan in `metadata/pve_bron.json`. Een test controleert dat elk schema naar die versie verwijst, en een wekelijkse workflow (`pve-upstream`) meldt als duo.nl een andere versie publiceert (#299)
- Demo-data: [cedanl/duo-mbo-datafiles](https://github.com/cedanl/duo-mbo-datafiles)
