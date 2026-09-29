# Aan de slag

## Vereisten

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- `MBO_PSEUDONIMISERING_SALT` (zie [Pseudonimisering](#pseudonimisering))

## Installatie

```bash
uv sync
export MBO_PSEUDONIMISERING_SALT="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
```

---

## Pseudonimisering

Persoons-identifiers (BSN, Onderwijsnummer, PGN) worden met HMAC-SHA256
gehasht, samen met hun soort: een PGN, BSN en ONr met dezelfde cijfers krijgen
een verschillend `_persoon_id`. Dat vereist een salt, ingesteld via de env-var:

```bash
export MBO_PSEUDONIMISERING_SALT="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
```

Zonder geldige salt faalt de pipeline (fail-closed).

- **Productie:** de salt komt uitsluitend uit de environment (secret manager,
  bijv. via het deploymentplatform). Geen salt in de repo of in
  applicatieconfig opslaan.
- **Lokale demo:** het `export`-commando hierboven genereert een willekeurige
  salt per shell. Bewaar die zelf als je pseudoniemen tussen sessies wilt
  kunnen koppelen.
- **Tests/CI:** gebruiken de vaste, publieke waarde
  `ci-test-key-do-not-use-in-production`. Die is herleidbaar en hoort dus
  nooit bij echte data.
- `app/config.toml` heeft nog een `[security] pseudonimisering_salt`-fallback
  voor oude setups, maar de meegeleverde config bevat bewust géén salt meer.
  Gebruik die fallback niet voor echte data; een echte salt hoort er niet thuis.

---

## Interactieve app

```bash
uv run streamlit run app/main.py
```

!!! warning "Alleen lokaal"
    De app is een lokale, single-user analysetool en wordt bewust niet gehost
    (ook niet op SURF). Er is geen login, geen rolgebaseerd exportrecht en geen
    audit-log. In preview en download zijn persoonsgegevens standaard verborgen; wie
    de app draait kan dat uitzetten en is dan zelf verantwoordelijk voor de export.

    Een kolom geldt als persoonsgegeven als een van deze patronen (hoofdletterongevoelig)
    in de kolomnaam voorkomt; zo vallen ook afgeleide kolommen als `Postcodecijfers_*`
    eronder:
    <!-- pii-patronen -->
    `_persoon_id`, `Burgerservicenummer`, `DatumOverlijden`, `DatumVertrek`, `DatumVestiging`, `Geboortedatum`, `Geboorteland`, `Gemeente`, `Geslacht`, `Leeftijd`, `Migratieachtergrond`, `Nationaliteit`, `Onderwijsnummer`, `Postcode`, `PseudoNummer`, `RedenUitschrijving`, `Verblijfstitel`, `Vertrokken`.
    <!-- /pii-patronen -->

Open daarna `http://localhost:8501`. Zet ruwe bestanden in `data/01-raw/` (in een submap
per half jaar, bijv. `h15/`, `h16/`, `h17/`). De app detecteert automatisch alle herkenbare
bestanden in `data/01-raw/` en maakt de twee producten in aparte stappen (#264):

1. **Verwerk bestanden** (brondata): elk bestand naar `data/02-prepared/`, zoals `mbo verwerk`.
   Faalt een bestand, dan blijft er van dat bestand geen (oude) brondata staan.
2. **Bouw analysemodel** (ster): stapelt de brondata van de huidige bestanden en schrijft het
   star schema naar `data/03-output/star/datamodel/`, zoals `mbo star`. Beschikbaar zodra er
   brondata is, ook na een herstart; de ruwe bestanden worden niet opnieuw verwerkt.

Navigeer naar **Resultaten** om de tabellen te bekijken en te downloaden als CSV.

---

## CLI

```bash
# Stap 1: verwerk één ruw bestand
uv run mbo verwerk data/01-raw/demo/h15/RO_27DV_20240731_20260324.csv \
    data/02-prepared/demo/h15/RO_27DV_20240731_20260324

# Stap 2: bouw star schema vanuit prepared-mappen
uv run mbo star \
    data/02-prepared/demo/h15/RO_27DV_20240731_20260324 \
    data/02-prepared/demo/h16/TBGI_25LX_2027_20251124 \
    data/02-prepared/demo/h17/GRONDSLAG_IP_MBO_27DV_20251119_2025 \
    --output data/03-output/demo/star \
    --relative-to data/02-prepared/demo

# (optioneel) stapel prepared-mappen zonder star schema te bouwen
uv run mbo stapel \
    data/02-prepared/demo/h15/RO_27DV_20240731_20260324 \
    data/02-prepared/demo/h17/GRONDSLAG_IP_MBO_27DV_20251119_2025 \
    --output data/03-output/demo/gestapeld \
    --relative-to data/02-prepared/demo
```

---

## Python API

### Eén bestand verwerken

```python
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline

# Detecteert bestandstype automatisch (RO / GRONDSLAG / TBGI)
frames = run_auto_pipeline(
    source="data/01-raw/demo/h15/RO_27DV_20240731_20260324.csv",
    target="data/02-prepared/demo/h15/RO_27DV_20240731_20260324",
)
# frames["ISP"]  ← Polars DataFrame, datums als pl.Date
```

Of rechtstreeks per type:

```python
from mbo_bekostiging_bestanden.pipeline import (
    run_pipeline,           # RO
    run_grondslag_pipeline, # GRONDSLAG IP MBO
    run_tbgi_pipeline,      # TBGI XML
)
```

Naast de tabellen schrijft elke run een `quality.json` in de doelmap:

| Sleutel | Betekenis |
|---|---|
| `slr_status` / `slr_details` | Gelezen recordaantallen tegen de controletotalen in het sluitrecord (`match`, `mismatch` of `unknown`) |
| `parseverlies` | Per recordtype en kolom het aantal gevulde bronwaarden dat na typering leeg is (ongeldige datum of getal) |
| `star.verouderde_kolommen` | Per tabel de jaargebonden kolommen die verouderd zijn en in v4.0.0 verdwijnen (info, telt niet mee in de status); gebruik `fact_inschrijving_schooljaar` (#201) |
| `regelinventaris` | Per kolom het aantal regels waarin een positie buiten het PvE (bijv. `Postcodecijfers_positie19`) verschilt van het veld dat ze meestal herhaalt; betekenis onbekend, de waarde staat in de brondata (#260). Een onbekend recordtype, een gevuld veld voorbij het schema of een ontbrekend verplicht achterveld wordt niet gerapporteerd — de ingest breekt daar meteen op (fail-closed, #257, #281), vóórdat `quality.json` geschreven wordt |
| `domeinafwijkingen` | Per recordtype en veld het aantal (`aantal`) gevulde waarden buiten hun waardedomein (patroon of waardenlijst uit `metadata/waardenlijsten.toml`, per veld gekoppeld via `domeinen` in het schema) en de ernst (`ernst`: `error` of `warning`, per domein ingesteld). Een afwijking wijst vaak op een verschoven veldindeling, bijv. een DUO-versie die een positie weglaat; voor structurele velden (BRIN, Studiejaar) staat de ernst op `error` (#238) |
| `warnings` / `errors` | Leesbare meldingen; de app toont ze op Home |

### Star schema bouwen

```python
from mbo_bekostiging_bestanden.pipeline import run_star

star = run_star(
    sources=[
        "data/02-prepared/demo/h15/RO_27DV_20240731_20260324",
        "data/02-prepared/demo/h16/TBGI_25LX_2027_20251124",
        "data/02-prepared/demo/h17/GRONDSLAG_IP_MBO_27DV_20251119_2025",
    ],
    target="data/03-output/demo/star",
    relative_to="data/02-prepared/demo",
)

star["fact_inschrijving"]        # één rij per inschrijvingsperiode
star["fact_bpv"]                 # alle BPV-overeenkomsten
star["fact_kzd"]                 # keuzedelen per inschrijving
star["fact_bekostiging"]         # bekostigingsdetail (BII / TBGI Teldatum)
star["meta_leveringen"]          # VLP + SLR metadata per levering
star["dim_deelnemer"]            # persoonskenmerken
star["dim_opleiding"]            # CREBO-attributen
star["dim_instelling"]           # instellingsnamen
```

### Star schema lezen (zonder herverwerking)

```python
import polars as pl

fact = pl.read_parquet("data/03-output/demo/star/datamodel/fact_inschrijving.parquet")

# Hoeveel bekostigde inschrijvingen per levering?
fact.filter(pl.col("IndicatieBekostigbaar") == "J") \
    .group_by("levering") \
    .len()
```

### Leveringen stapelen (laag-niveau)

```python
from mbo_bekostiging_bestanden.stack import stack_prepared

stacked = stack_prepared(
    sources=[
        "data/02-prepared/demo/h15/RO_27DV_20240731_20260324",
        "data/02-prepared/demo/h17/GRONDSLAG_IP_MBO_27DV_20251119_2025",
    ],
    relative_to="data/02-prepared/demo",
)
# stacked["ISP"]  — rijen uit beide leveringen, eerste kolom = "levering"
```

Schema-drift (bijv. `Burgerservicenummer` in RO vs. `PseudoNummer` in GRONDSLAG)
wordt automatisch afgehandeld — ontbrekende kolommen krijgen `null`.

---

## Let op bij Excel-gebruik

`fact_inschrijving` heeft grain = inschrijvingsperiode (ISP). De aggregaten
`BPV_*`, `KZD_*` en `AMO_*` gelden per periode: elke BPV, elk keuzedeel en elk
AMO-onderdeel telt mee in precies één periode (dezelfde als zijn
`_inschrijving_periode_id` in het detail-feit). Je kunt ze dus direct optellen
over `fact_inschrijving` zonder dubbeltelling.
Voor afzonderlijke BPV-regels gebruik je `fact_bpv.parquet`.

---

## Tests

```bash
export MBO_PSEUDONIMISERING_SALT="ci-test-key-do-not-use-in-production"  # alleen tests/CI
uv run pytest
```

De tests draaien fail-closed op de pseudonimiserings-salt; zonder de env-var
slaat de pipeline-fase af (zie [Pseudonimisering](#pseudonimisering)).

---

## Datastructuur

```
data/
├── 01-raw/demo/
│   ├── h15/   ← RO-bestanden (Registratieoverzicht)
│   ├── h16/   ← TBGI XML (bekostigingsgrondslagen)
│   └── h17/   ← GRONDSLAG IP MBO
├── 02-prepared/demo/
│   ├── h15/RO_27DV_20240731_20260324/   ← één submap per bronbestand (volledige naam)
│   ├── h16/TBGI_25LX_2027_20251124/
│   └── h17/GRONDSLAG_IP_MBO_27DV_20251119_2025/
└── 03-output/demo/
    └── star/
        └── datamodel/
            ├── dim_deelnemer.parquet
            ├── dim_opleiding.parquet
            ├── dim_instelling.parquet
            ├── fact_inschrijving.parquet
            ├── fact_bpv.parquet
            ├── fact_kzd.parquet
            ├── fact_amo.parquet
            ├── fact_geo.parquet
            ├── fact_bekostiging.parquet
            ├── fact_bekostiging_diploma.parquet
            └── meta_leveringen.parquet
```

Echte data zet je in `data/01-raw/` buiten de `demo/`-submap — die staat in `.gitignore`.
