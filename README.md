# mbo-bekostiging-bestanden

Leest DUO MBO-bekostigingsbestanden in en zet ze om naar schone, onderzoeksklare data.

## Context

MBO-instellingen worden bekostigd op basis van bestanden die DUO publiceert. Die
bestanden zijn ruw en lastig direct te gebruiken. Deze repo leest ze in,
decodeert de velden, controleert de kwaliteit en levert schone tabellen op
waarop andere CEDA-projecten kunnen voortbouwen.

Doelgroep: analisten en onderzoekers bij mbo-instellingen die met
bekostigingsdata werken.

## Quick start

1. Installeer de dependencies:

   ```
   uv sync
   ```

2. Start de interactieve app:

   ```
   uv run streamlit run app/main.py
   ```

3. Of draai de pipeline in Python:

   ```python
   from mbo_bekostiging_bestanden.pipeline import run_pipeline
   run_pipeline("data/01-raw/demo/bekostiging_demo.csv", "data/03-output/demo/bekostiging.parquet")
   ```

De repo bevat synthetische demo-data, zodat alles direct werkt zonder eigen bestanden.

## Data

- **Input**: ruwe bekostigingsbestanden in `data/01-raw/` (fixed-width/CSV van DUO).
- **Output**: schone Parquet-tabellen in `data/02-prepared/` of `data/03-output/`.
- Echte data staat niet in git; alleen synthetische demo-data in `data/*/demo/`.

## Ontwikkeling

Open de repo in de devcontainer (VS Code / GitHub Codespaces) voor een werkende
omgeving. Tests draaien met:

```
uv run pytest
```

## Referenties

- Technische context en projectstructuur: [`CLAUDE.md`](CLAUDE.md)
- CEDA-standaarden: https://github.com/cedanl/.github/tree/main/standards/README.md

## Contact

Onderhouden door CEDA (cedanl). Bijdragen via issues en pull requests.

## License

MIT
