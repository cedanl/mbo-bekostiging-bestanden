# mbo-bekostiging-bestanden

Leest DUO MBO-bekostigingsbestanden in en zet ze om naar schone, onderzoeksklare data.

<video src="https://github.com/user-attachments/assets/ec17d64d-0e60-4cd6-8304-1adc92f10a91" controls width="100%"></video>

## Context

MBO-instellingen worden bekostigd op basis van bestanden die DUO publiceert. Die
bestanden zijn ruw en lastig direct te gebruiken. Deze repo leest ze in,
decodeert de velden, controleert de kwaliteit en exporteert een star schema
(dimensies + feittabellen) waarop andere CEDA-projecten kunnen voortbouwen.

Doelgroep: analisten en onderzoekers bij mbo-instellingen die met
bekostigingsdata werken.

## Quick start

```bash
uv sync
export MBO_PSEUDONIMISERING_SALT="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
uv run streamlit run app/main.py
```

De repo bevat demo-data, zodat alles direct werkt zonder eigen bestanden.

> **Pseudonimisering (fail-closed):** persoons-identifiers worden gehasht met
> HMAC-SHA256 plus deze salt. Zonder `MBO_PSEUDONIMISERING_SALT` weigert de
> pipeline te draaien. Productie gebruikt uitsluitend de environment
> (secret manager); lokaal genereert het `export`-commando hierboven een
> willekeurige salt per shell. Bewaar die zelf als je pseudoniemen tussen sessies
> wilt kunnen koppelen. Bewaar echte salts nooit in git — een
> `app/config.toml`-fallback is puur voor demo en bevat geen salt meer.

> **Alleen lokaal gebruiken:** de app is een lokale, single-user analysetool en
> wordt bewust níet gehost (ook niet op SURF). Er is geen login, geen
> rolgebaseerd exportrecht en geen audit-log: wie de app draait, kan een tabel
> desgewenst mét persoonsgegevens downloaden (standaard staan die uit).

---

### Stap 1 — Bestanden verwerken

Open de app, bekijk de ontdekte bestanden en klik **Verwerk alles**. De pipeline
normaliseert alle ruwe DUO-bestanden naar Parquet en bouwt het star schema.

![Home — bestanden verwerken](docs/assets/home.gif)

### Stap 2 — Dashboard

Na de verwerking toont het Dashboard een visueel overzicht verdeeld over vijf
tabs: rendementen (JR), bekostigingstrechter, opleidingen (BOL/BBL, BPV, KZD),
studenten (geslacht, herkomst, gemeente) en GEO-examencijfers.

![Dashboard — analyse-overzicht](docs/assets/dashboard.gif)

### Stap 3 — Resultaten bekijken en downloaden

Op de Resultaten-pagina selecteer je een van de star-schema-tabellen,
bekijk je een preview van de eerste 1 000 rijen en download je de volledige
tabel als CSV.

![Resultaten — tabel preview en download](docs/assets/resultaten.gif)

---

**CLI**:

```bash
# Verwerk één ruw bestand naar prepared
uv run mbo verwerk data/01-raw/demo/h15/RO_27DV_20240731_20260324.csv \
    data/02-prepared/demo/h15/RO_27DV_20240731_20260324

# Bouw star schema vanuit meerdere prepared-mappen
uv run mbo star \
    data/02-prepared/demo/h15/RO_27DV_20240731_20260324 \
    data/02-prepared/demo/h16/TBGI_25LX_2027_20251124 \
    data/02-prepared/demo/h17/GRONDSLAG_IP_MBO_27DV_20251119_2025 \
    --output data/03-output/demo/star \
    --relative-to data/02-prepared/demo
```

**Python API**:

```python
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline, run_star

run_auto_pipeline("data/01-raw/demo/h15/RO_27DV_20240731_20260324.csv",
                  "data/02-prepared/demo/h15/RO_27DV_20240731_20260324")

run_star(
    sources=["data/02-prepared/demo/h15/RO_27DV_20240731_20260324",
             "data/02-prepared/demo/h16/TBGI_25LX_2027_20251124",
             "data/02-prepared/demo/h17/GRONDSLAG_IP_MBO_27DV_20251119_2025"],
    target="data/03-output/demo/star",
    relative_to="data/02-prepared/demo",
)
# Star schema staat in data/03-output/demo/star/datamodel/
```

### Eigen data verwerken

Wijs `app/config.toml` naar je eigen mappen en draai dezelfde stappen:

```toml
[data]
raw = "data/01-raw/eigen"
prepared = "data/02-prepared/eigen"
output = "data/03-output/eigen"
```

Zet je ruwe DUO-bestanden (`RO_*.csv`, `TBGI_*.XML`, `GRONDSLAG_IP_MBO_*.csv`) in
de `raw`-map. De app ontdekt en verwerkt ze automatisch. Echte data staat niet in
git.

## Data

- **Input**: ruwe bekostigingsbestanden in `data/01-raw/`. Drie typen:
  `RO_*.csv` (h15), `TBGI_*.XML` (h16), `GRONDSLAG_IP_MBO_*.csv` (h17).
- **Prepared**: genormaliseerde Parquet per recordtype in `data/02-prepared/`,
  één submap per leveringsbestand (`groep/bestandsstam/`).
- **Output**: elf star-schema-tabellen in `data/03-output/star/datamodel/`
  (zie [docs/datamodel.md](docs/datamodel.md) voor een volledig overzicht)
- Echte data staat niet in git; alleen demo-data in `data/*/demo/`.

## Ontwikkeling

```bash
export MBO_PSEUDONIMISERING_SALT="ci-test-key-do-not-use-in-production"  # alleen tests/CI
uv run pytest       # tests
uv run ruff check   # lint
```

De tests draaien fail-closed op persoons-pseudonimisering; zonder
`MBO_PSEUDONIMISERING_SALT` faalt de pipeline (zie [Quick start](#quick-start)).
De vaste testwaarde is publiek en dus herleidbaar: gebruik hem uitsluitend op
synthetische data (tests, CI), nooit voor het verwerken van echte bestanden.

Open de repo in de devcontainer (VS Code / GitHub Codespaces) voor een kant-en-klare omgeving.

## Referenties

- Uitgebreide documentatie: [`docs/`](docs/index.md)
- Technische context: [`CLAUDE.md`](CLAUDE.md)
- CEDA-standaarden: https://github.com/cedanl/.github/tree/main/standards/README.md

## Contact

Onderhouden door CEDA (cedanl). Bijdragen via issues en pull requests.

## License

MIT
