# mbo-bekostiging-bestanden

## Overview
Ingestion-repo (Type 1). Leest ruwe DUO MBO-bekostigingsbestanden in en zet ze
om naar schone, onderzoeksklare data. Andere repos bouwen voort op de output.
Pipeline-fase: `ingest > decode > validate > export`.

## Standards
Volg de CEDA technische standaarden: https://github.com/cedanl/.github/tree/main/standards/README.md

## Tech Stack
- Python 3.13, uv voor dependency-management
- Polars voor data-verwerking
- Streamlit voor de interactieve interface
- pytest (tests), ruff (lint/format), ty (type checking)

## Project Structure
```
mbo-bekostiging-bestanden/
├── .devcontainer/                 # Reproduceerbare dev-omgeving
├── .github/workflows/             # CI (tests + lint)
├── data/
│   ├── 01-raw/demo/               # Synthetische demo-bron (in git)
│   ├── 02-prepared/demo/
│   └── 03-output/demo/
├── src/mbo_bekostiging_bestanden/
│   ├── ingest.py                  # Ruwe bestanden inlezen
│   ├── decode.py                  # Codes omzetten via metadata
│   ├── validate.py                # Kwaliteitscontroles
│   ├── export.py                  # Schone data wegschrijven
│   ├── pipeline.py                # Orkestratie van de fasen
│   └── metadata/                  # Veldindelingen / codeboeken
├── app/
│   ├── main.py                    # Streamlit-app (geen bedrijfslogica)
│   └── config.toml                # Datapaden
└── tests/                         # pytest op de demo-data
```

## How to Run
- Dependencies: `uv sync`
- Tests: `uv run pytest`
- App: `uv run streamlit run app/main.py`
- Pipeline (Python): `run_pipeline(source, target)` uit `pipeline.py`

## Data
- **Input**: ruwe DUO-bekostigingsbestanden in `data/01-raw/`. Multi-record,
  `;`-gescheiden (regeltypes `VLP`/`PER`/`ISG`/…) plus XML (TBGI). Demo-data
  staat in submappen `h15/`, `h16/`, `h17/`.
- **Output**: schone Parquet in `data/02-prepared/` of `data/03-output/`.
- Echte data is gitignored; alleen demo-data in `data/*/demo/` staat in git
  (overgenomen uit `cedanl/duo-mbo-datafiles`).
- Privacy: geen persoonsgegevens committen; bekostiging is op instellingsniveau.
