# Aan de slag

## Vereisten

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Installatie

```bash
uv sync
```

## Pipeline draaien

```python
from mbo_bekostiging_bestanden.pipeline import run_pipeline

run_pipeline(
    "data/01-raw/demo/h17/GRONDSLAG_IP_MBO_27DV_20251119_2025.csv",
    "data/03-output/demo/grondslag.parquet"
)
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
└── 03-output/demo/
```

Echte data zet je in `data/01-raw/` buiten de `demo/`-submap — die staat in `.gitignore`.
