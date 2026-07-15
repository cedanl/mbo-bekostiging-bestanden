# MBO-bekostigingsbestanden

DUO levert aan MBO-instellingen periodiek bestanden waarmee de instelling kan controleren of haar studenten bekostigd worden en op welke grondslag. Deze bestanden zijn technisch van opzet: meerdere recordtypes per bestand, gecodeerde velden, geen kolomkoppen.

**Deze tool leest die ruwe bestanden in, normaliseert ze en bouwt er één platte analysetabel (OBT) van** — direct bruikbaar in Excel, Python, R of Power BI.

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

### Stap 2 — OBT (gecombineerd over alle leveringen)

Alle prepared-mappen worden gecombineerd tot vijf bestanden in `data/03-output/obt/`:

| Bestand | Grain | Inhoud |
|---|---|---|
| `obt_inschrijvingen.parquet` | inschrijvingsperiode (ISP) | kern van de OBT; ISG/PER/BPV-aggregaat/KZD-aggregaat/GEO-pivot ingebakken |
| `detail_bpv.parquet` | BPV-overeenkomst | alle afzonderlijke BPV-records |
| `detail_kzd_amo.parquet` | keuzedeel / AMvB-onderdeel | alle KZD- en AMO-records |
| `detail_bekostiging.parquet` | teldatum | bekostigingsdetail (BII-records / TBGI Teldatum) |
| `meta_leveringen.parquet` | leveringsbestand | VLP-metadata per bron |

Een `levering`-kolom in elke tabel geeft aan uit welk bronbestand een rij afkomstig is (bijv. `h15/RO_27DV_20240731_20260324`).

#### Berekende vlaggen op obt_inschrijvingen

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
