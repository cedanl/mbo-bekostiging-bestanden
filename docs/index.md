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
| Beperkingen | Gepseudonimiseerd (`_persoon_id` in plaats van BSN/ONr/PGN, #173), maar nog persoonsgegevens; zie [opslag en retentie](aan-de-slag.md#opslag-en-retentie-van-brondata) | JR/DR zijn indicatief: alleen de eigen leveringen (#118, #119) |
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

#### Afgeleide kolommen in fact_inschrijving

`fact_inschrijving` staat op **periode-grain** en draagt geen jaargebonden vlaggen: tellingen op 1 oktober,
hoofdinschrijving en rendementen (JR/DR/Entree) staan per schooljaar in `fact_inschrijving_schooljaar` (zie
[Datamodel](datamodel.md)). Tot en met v3.4.0 stonden er ook periode-varianten van die vlaggen; v4.0.0 heeft ze
verwijderd (#201).

| Kolom | Type | Betekenis |
|---|---|---|
| `Studiejaar_periode` | `Int64` | Studiejaar waarin de periode begint |
| `_niveau_herkomst` | `Utf8` | Herkomst van `Niveau`: bron, CREBO, S-BB of onbekend |
| `Niveau_gecombineerd` | `Utf8` | Niveau + spatie + Leertraject (bijv. `MBO-4 BOL`) |

#### Verrijking via decodeertabellen

Daarna worden leesbare labels toegevoegd via LEFT JOINs op de
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

- Bestandsbeschrijving DUO PvE MBO-instelling (hoofdstuk 13–17), `bestandsbeschrijving_beknopt.pdf` in deze repo; versie, datum en sha256 staan alleen in `metadata/pve_bron.json`. Een wekelijkse workflow (`pve-upstream`) meldt als duo.nl een andere versie publiceert (#299); hoe je die verwerkt en wat er per versie veranderde, staat in [PvE-versies](pve-wijzigingen.md) (#298)
- Demo-data: [cedanl/duo-mbo-datafiles](https://github.com/cedanl/duo-mbo-datafiles)
