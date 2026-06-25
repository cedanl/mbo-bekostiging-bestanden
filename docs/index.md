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
