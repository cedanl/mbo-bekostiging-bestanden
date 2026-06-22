# Aan de slag

## Vereisten

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Installatie

```bash
uv sync
```

## RO-bestand verwerken

```python
from mbo_bekostiging_bestanden.pipeline import run_pipeline

frames = run_pipeline(
    source="data/01-raw/demo/h15/RO_27DV_20240731_20260324.csv",
    target="data/02-prepared/demo/h15/27DV",
)
```

`run_pipeline` geeft een dict van recordtype-code naar Polars DataFrame terug én schrijft elk recordtype als Parquet naar de doelmap.

## Output lezen

Na het verwerken staan de bestanden in de doelmap:

```python
import polars as pl

isg = pl.read_parquet("data/02-prepared/demo/h15/27DV/ISG.parquet")
isg.head(3)
```

| Burgerservicenummer | Inschrijvingvolgnummer | DatumInschrijving | DatumUitschrijvingGepland |
|---|---|---|---|
| … | C3 | 2023-01-30 | 2025-01-29 |

Datumvelden zijn `pl.Date`, telvelden zijn `pl.Int64`. Je kunt direct filteren en joinen zonder type-conversie.

## Bestanden koppelen

De recordtypes zijn via `Burgerservicenummer` en `Inschrijvingvolgnummer` aan elkaar te koppelen:

```python
per = pl.read_parquet("data/02-prepared/demo/h15/27DV/PER.parquet")
isg = pl.read_parquet("data/02-prepared/demo/h15/27DV/ISG.parquet")

per.join(isg, on="Burgerservicenummer")
```

## Interactieve app

```bash
uv run streamlit run app/main.py
```

Open daarna `http://localhost:8501`, kies een bronbestand en klik op **Verwerk**.

## Tests

```bash
uv run pytest
```

## Datastructuur

```
data/
├── 01-raw/demo/
│   ├── h15/   ← RO-bestanden (Registratieoverzicht)
│   ├── h16/   ← TBGI XML (bekostigingsgrondslagen)
│   └── h17/   ← GRONDSLAG IP MBO
├── 02-prepared/demo/
│   └── h15/27DV/   ← één submap per BRIN-code
└── 03-output/demo/
```

Echte data zet je in `data/01-raw/` buiten de `demo/`-submap — die staat in `.gitignore`.
