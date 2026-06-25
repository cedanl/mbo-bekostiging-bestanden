# mbo-bekostiging-bestanden

Leest DUO MBO-bekostigingsbestanden in en zet ze om naar schone, onderzoeksklare data.

## Context

MBO-instellingen worden bekostigd op basis van bestanden die DUO publiceert. Die
bestanden zijn ruw en lastig direct te gebruiken. Deze repo leest ze in,
decodeert de velden, controleert de kwaliteit en bouwt er één platte tabel van
(OBT) waarop andere CEDA-projecten kunnen voortbouwen.

Doelgroep: analisten en onderzoekers bij mbo-instellingen die met
bekostigingsdata werken.

## Quick start

```bash
uv sync
```

**Interactieve app** — zet bestanden in `data/01-raw/` en klik op *Verwerk alles*:

```bash
uv run streamlit run app/main.py
```

**CLI**:

```bash
# Verwerk één ruw bestand naar prepared
uv run mbo verwerk data/01-raw/demo/h15/RO_27DV_20240731_20260324.csv \
    data/02-prepared/demo/h15/RO_27DV_20240731_20260324

# Bouw OBT vanuit meerdere prepared-mappen
uv run mbo obt \
    data/02-prepared/demo/h15/RO_27DV_20240731_20260324 \
    data/02-prepared/demo/h16/TBGI_25LX_2027_20251124 \
    data/02-prepared/demo/h17/GRONDSLAG_IP_MBO_27DV_20251119_2025 \
    --output data/03-output/demo/obt \
    --relative-to data/02-prepared/demo
```

**Python API**:

```python
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline, run_obt

run_auto_pipeline("data/01-raw/demo/h15/RO_27DV_20240731_20260324.csv",
                  "data/02-prepared/demo/h15/RO_27DV_20240731_20260324")

obt = run_obt(
    sources=["data/02-prepared/demo/h15/RO_27DV_20240731_20260324",
             "data/02-prepared/demo/h16/TBGI_25LX_2027_20251124",
             "data/02-prepared/demo/h17/GRONDSLAG_IP_MBO_27DV_20251119_2025"],
    target="data/03-output/demo/obt",
    relative_to="data/02-prepared/demo",
)
# obt["obt_inschrijvingen"]  — één rij per inschrijvingsperiode (ISP)
```

De repo bevat demo-data, zodat alles direct werkt zonder eigen bestanden.

## Data

- **Input**: ruwe bekostigingsbestanden in `data/01-raw/`. Drie typen:
  `RO_*.csv` (h15), `TBGI_*.XML` (h16), `GRONDSLAG_IP_MBO_*.csv` (h17).
- **Prepared**: genormaliseerde Parquet per recordtype in `data/02-prepared/`,
  één submap per leveringsbestand (`groep/bestandsstam/`).
- **Output**: vijf OBT-bestanden in `data/03-output/obt/`:
  - `obt_inschrijvingen` — grain = inschrijvingsperiode (ISP), joins naar ISG/PER/BPV/KZD/GEO ingebakken
  - `detail_bpv` — alle BPV-overeenkomsten (één rij per overeenkomst)
  - `detail_kzd_amo` — keuzedelen en AMvB-onderdelen
  - `detail_bekostiging` — bekostigingsdetail (BII-records / TBGI Teldatum)
  - `meta_leveringen` — metadata per leveringsbestand
- Echte data staat niet in git; alleen demo-data in `data/*/demo/`.

## Ontwikkeling

```bash
uv run pytest       # tests
uv run ruff check   # lint
```

Open de repo in de devcontainer (VS Code / GitHub Codespaces) voor een kant-en-klare omgeving.

## Referenties

- Uitgebreide documentatie: [`docs/`](docs/index.md)
- Technische context: [`CLAUDE.md`](CLAUDE.md)
- CEDA-standaarden: https://github.com/cedanl/.github/tree/main/standards/README.md

## Contact

Onderhouden door CEDA (cedanl). Bijdragen via issues en pull requests.

## License

MIT
