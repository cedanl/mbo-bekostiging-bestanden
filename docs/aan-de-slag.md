# Aan de slag

## Vereisten

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Installatie

```bash
uv sync
```

---

## Interactieve app

```bash
uv run streamlit run app/main.py
```

Open daarna `http://localhost:8501`. Zet ruwe bestanden in `data/01-raw/` (in een submap
per half jaar, bijv. `h15/`, `h16/`, `h17/`) en klik op **Verwerk alles**. De app:

1. Detecteert automatisch alle herkenbare bestanden in `data/01-raw/`.
2. Verwerkt elk bestand naar `data/02-prepared/`.
3. Stapelt alle leveringen en bouwt één gecombineerde OBT.
4. Schrijft vijf Parquet-bestanden naar `data/03-output/obt/`.

Navigeer naar **Resultaten** om de tabellen te bekijken en te downloaden als CSV.

---

## CLI

```bash
# Stap 1: verwerk één ruw bestand
uv run mbo verwerk data/01-raw/demo/h15/RO_27DV_20240731_20260324.csv \
    data/02-prepared/demo/h15/RO_27DV_20240731_20260324

# Stap 2: bouw OBT vanuit prepared-mappen
uv run mbo obt \
    data/02-prepared/demo/h15/RO_27DV_20240731_20260324 \
    data/02-prepared/demo/h16/TBGI_25LX_2027_20251124 \
    data/02-prepared/demo/h17/GRONDSLAG_IP_MBO_27DV_20251119_2025 \
    --output data/03-output/demo/obt \
    --relative-to data/02-prepared/demo

# (optioneel) stapel prepared-mappen zonder OBT te bouwen
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

### OBT bouwen

```python
from mbo_bekostiging_bestanden.pipeline import run_obt

obt = run_obt(
    sources=[
        "data/02-prepared/demo/h15/RO_27DV_20240731_20260324",
        "data/02-prepared/demo/h16/TBGI_25LX_2027_20251124",
        "data/02-prepared/demo/h17/GRONDSLAG_IP_MBO_27DV_20251119_2025",
    ],
    target="data/03-output/demo/obt",
    relative_to="data/02-prepared/demo",
)

obt["obt_inschrijvingen"]  # één rij per inschrijvingsperiode
obt["detail_bpv"]          # alle BPV-overeenkomsten
obt["detail_kzd_amo"]      # keuzedelen en AMvB-onderdelen
obt["detail_bekostiging"]  # bekostigingsdetail (BII / TBGI Teldatum)
obt["meta_leveringen"]     # VLP-metadata per bronbestand
```

### OBT lezen (zonder herverwerking)

```python
import polars as pl

isp = pl.read_parquet("data/03-output/demo/obt/obt_inschrijvingen.parquet")

# Hoeveel bekostigde inschrijvingen per levering?
isp.filter(pl.col("IndicatieBekostigbaar") == "J") \
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

De OBT heeft grain = inschrijvingsperiode (ISP). `BPV_Aantal` en `BPV_TotaalOmvang`
in `obt_inschrijvingen` zijn aggregaten per inschrijving die herhalen op elke ISP-rij.
Doe in Excel altijd eerst een **groepering op `(levering, _persoon_id, Inschrijvingvolgnummer)`**
voordat je BPV-kolommen sommeert, anders tel je dubbel.
Voor afzonderlijke BPV-regels gebruik je `detail_bpv.parquet`.

---

## Tests

```bash
uv run pytest
```

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
    └── obt/
        ├── obt_inschrijvingen.parquet
        ├── detail_bpv.parquet
        ├── detail_kzd_amo.parquet
        ├── detail_bekostiging.parquet
        └── meta_leveringen.parquet
```

Echte data zet je in `data/01-raw/` buiten de `demo/`-submap — die staat in `.gitignore`.
