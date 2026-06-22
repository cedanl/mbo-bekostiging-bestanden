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

3. Of draai de pipeline in Python (zodra het inlezen/decoderen geïmplementeerd is):

   ```python
   from mbo_bekostiging_bestanden.pipeline import run_pipeline
   run_pipeline("data/01-raw/demo/h17/GRONDSLAG_IP_MBO_27DV_20251119_2025.csv", "data/03-output/demo/grondslag.parquet")
   ```

De repo bevat demo-data, zodat alles direct werkt zonder eigen bestanden.

## Data

- **Input**: ruwe bekostigingsbestanden in `data/01-raw/`. Het zijn multi-record
  bestanden van DUO: regels beginnen met een recordtype (`VLP`, `PER`, `ISG`, …),
  `;`-gescheiden, plus XML-bestanden (TBGI). Het inlezen en decoderen per
  recordtype volgt in aparte issues.
- **Output**: schone Parquet-tabellen in `data/02-prepared/` of `data/03-output/`.
- Echte data staat niet in git; alleen demo-data in `data/*/demo/` (overgenomen
  uit [`cedanl/duo-mbo-datafiles`](https://github.com/cedanl/duo-mbo-datafiles)).

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
