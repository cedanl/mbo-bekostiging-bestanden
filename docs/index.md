# MBO-bekostigingsbestanden

DUO levert aan MBO-instellingen periodiek bestanden waarmee de instelling kan controleren of haar studenten bekostigd worden en op welke grondslag. Deze bestanden zijn technisch van opzet: meerdere recordtypes per bestand, gecodeerde velden, geen kolomkoppen.

**Deze tool leest die ruwe bestanden in, normaliseert ze en bouwt er een star schema van** — direct bruikbaar in Excel, Python, R of Power BI; zie [Datamodel](datamodel.md).

---

## Drie bestandstypen

| Bestand | Map | Wat het is |
|---|---|---|
| `RO_*.csv` | `h15/` | Registratieoverzicht – alle inschrijvingen en diploma's in een selectieperiode |
| `TBGI_*.XML` | `h16/` | TBG-i – bekostigingsgrondslagen per inschrijving en diploma, inclusief signalen |
| `GRONDSLAG_IP_MBO_*.csv` | `h17/` | Afslag register-levering IP – bekostigingsrelevante data voor de peildatum 1-10 |

---

## Wat levert de tool op?

De verwerking bestaat uit twee stappen.

### Stap 1 — Prepared (per leveringsbestand)

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

### Stap 2 — Star schema (gecombineerd over alle leveringen)

Alle prepared-mappen worden gecombineerd tot tien Parquet-bestanden in `data/03-output/star/datamodel/`:

| Bestand | Grain | Inhoud |
|---|---|---|
| `dim_deelnemer.parquet` | Persoon | Persoonskenmerken (geslacht, geboorteland, gemeente …) |
| `dim_opleiding.parquet` | Opleiding | CREBO-attributen incl. S-BB koppeltabel |
| `dim_instelling.parquet` | Instelling | Naam en vestigingsplaats |
| `fact_inschrijving.parquet` | ISP-inschrijvingsperiode | Centrale feittabel met vlaggen en aggregaten |
| `fact_bpv.parquet` | BPV-overeenkomst | Alle BPV-periodes per inschrijving |
| `fact_kzd.parquet` | Keuzedeel-resultaat | KZD-resultaten per inschrijving |
| `fact_amo.parquet` | AMO-resultaat | AMvB-onderdelen per inschrijving |
| `fact_geo.parquet` | GEO-examenonderdeel | Eindcijfers IE/CE in long format |
| `fact_bekostiging.parquet` | TBGI Teldatum | Bekostigingsgrondslagen per teldatum |
| `fact_bekostiging_diploma.parquet` | TBGI Diploma | Diplomawaarde-bijdragen per diploma |

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

De OBT voegt per inschrijvingsperiode een reeks berekende vlaggen toe:

| Groep | Kolom | Type | Betekenis |
|---|---|---|---|
| Bekostiging | `_actief_1_oktober` | `Boolean` | ISP omvat 1 oktober van het studiejaar |
| | `_bekostigd_eerste_1okt` | `Boolean` | Eerste 1-okt-inschrijving ooit (niet eerder op dezelfde opleiding) |
| | `_gediplomeerd_in_jaar` | `Boolean` | DIP-record aanwezig in het studiejaar |
| | `_ingeschreven_jaar_later` | `Boolean` | Nog ingeschreven in het volgende studiejaar |
| | `_deelnemer_niet_bekostigd_eerste_1okt` | `Boolean` | Actief op 1 okt maar niet bekostigd als eerste inschrijving |
| Selectie | `_hoogste_niveau` | `Boolean` | Hoogste numeriek niveau per persoon × studiejaar |
| | `_laagste_CREBO` | `Boolean` | Laagste CREBO-code bij gelijk niveau |
| | `_hoofdinschrijving` | `Boolean` | Eén rij per persoon × studiejaar (combinatie van _hoogste_niveau + _laagste_CREBO) |
| Tellingen | `_telling` | `Boolean` | `_actief_1_oktober AND _hoofdinschrijving` — telt de deelnemer mee voor bekostiging |
| Rendement | `_jr_noemer` | `Boolean` | = `_telling`; noemer van het Jaarresultaat |
| | `_jr_teller` | `Boolean` | Noemer AND (gediplomeerd OR ingeschreven_jaar_later) |
| Entree | `_entree_uitstroom` | `Boolean` | MBO-1 + uitgeschreven (geen actieve ISP meer) |
| | `_entree_doorstroom` | `Boolean` | MBO-1 + een hogere inschrijving bij dezelfde instelling |
| Afgeleid | `Niveau_gecombineerd` | `Utf8` | Niveau + spatie + Leertraject (bijv. `MBO-4 BOL`) |
| | `_tellingen_aanwezig` | `UInt32` | Aantal ISP-rijen per persoon × inschrijving (duplicaatdetectie) |

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

- Bestandsbeschrijving DUO PvE MBO-instelling v4.8.3 (12-05-2026)
- Demo-data: [cedanl/duo-mbo-datafiles](https://github.com/cedanl/duo-mbo-datafiles)
