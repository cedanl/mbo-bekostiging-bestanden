# MBO-bekostigingsbestanden

DUO levert aan MBO-instellingen periodiek bestanden waarmee de instelling kan controleren of haar studenten bekostigd worden en op welke grondslag. Deze bestanden zijn technisch van opzet: meerdere recordtypes per bestand, gecodeerde velden, geen kolomkoppen.

**Deze tool leest die ruwe bestanden in en zet ze om naar schone, getypeerde Parquet-bestanden** — klaar voor analyse in Python, R, Power BI of een ander tool naar keuze.

---

## Drie bestandstypen

| Bestand | Map | Wat het is |
|---|---|---|
| `RO_*.csv` | `h15/` | Registratieoverzicht – alle inschrijvingen en diploma's in een selectieperiode |
| `TBGI_*.XML` | `h16/` | TBG-i – bekostigingsgrondslagen per inschrijving en diploma, inclusief signalen |
| `GRONDSLAG_IP_MBO_*.csv` | `h17/` | Afslag register-levering IP – bekostigingsrelevante data voor de peildatum 1-10 |

---

## Wat levert de tool op?

Na het verwerken van een RO-bestand staat er in `data/02-prepared/` één Parquet-bestand per recordtype:

```
data/02-prepared/demo/h15/27DV/
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

De bestanden zijn direct bruikbaar:

```python
import polars as pl

isg = pl.read_parquet("data/02-prepared/demo/h15/27DV/ISG.parquet")
print(isg.dtypes)
# DatumInschrijving: Date  ← echte datum, geen string
# AantalPER: Int64         ← integer, geen tekst
```

Datumvelden zijn `Date`, telvelden zijn `Int64`. Nullwaarden zijn `null`, geen lege strings.

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
