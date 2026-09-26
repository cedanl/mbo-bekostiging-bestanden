# mbo-bekostiging-bestanden

## Overview
Ingestion-repo (Type 1). Leest ruwe DUO MBO-bekostigingsbestanden in en zet ze
om naar schone, onderzoeksklare data. Andere repos bouwen voort op de output.
Pipeline-fase: `ingest > decode > validate > export > stack > transform > enrich > star schema`.

## Standards
Volg de CEDA technische standaarden: https://github.com/cedanl/.github/tree/main/standards/README.md

## Coding Principles (voor alle LLM-bijdragers)
- **Modulair & onderhoudbaar** — herhalende logica hoort in een herbruikbare functie of module, niet inline gedupliceerd.
- **Geen hardcoded waarden** — paden, codes, labels en drempelwaarden komen uit config (`config.toml`, constanten bovenaan het bestand, of parameters). Nooit als magic string midden in de code.
- **Dynamisch** — lees kolomnamen, opties en lijsten uit de data; neem ze niet over als vaste lijst tenzij ze écht stabiel zijn.
- **Boy Scout Principle** — laat elke file die je aanraakt schoner achter dan je hem aantrof: verwijder dode code, los triviale stijlproblemen op, vereenvoudig onduidelijke logica.
- **Geen Tactical Tornado** — geen snelle quick-fixes die technische schuld opbouwen of toekomstig onderhoud bemoeilijken. Kies de duurzame oplossing, ook als die iets meer werk is.
- **Geen commit tenzij gevraagd** — implementeer lokaal en meld wat er gedaan is; wacht op een expliciete commit-opdracht van de gebruiker.
- **Grafiektoelichtingen bijhouden** — bij elke aanpassing aan het dashboard of een grafiek (`app/pages/dashboard.py` e.d.): check de bijbehorende toelichting in `app/_chart_docs.py`, werk deze bij als de grafiek verandert, en maak er een aan als een (nieuwe) grafiek nog geen toelichting heeft. Een grafiek zonder toelichting is niet af.

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
│       └── star/datamodel/        # Star schema (11 Parquet-bestanden)
├── src/mbo_bekostiging_bestanden/
│   ├── ingest.py                  # Ruwe bestanden inlezen
│   ├── decode.py                  # Codes omzetten via metadata
│   ├── validate.py                # Kwaliteitscontroles
│   ├── export.py                  # Schone data wegschrijven
│   ├── pipeline.py                # Orkestratie van de fasen
│   ├── stack.py                   # Leveringen stapelen
│   ├── transform.py               # Domein-transformaties (intern, niet publiek)
│   ├── enrich.py                  # Decodeertabellen joinen
│   ├── star.py                    # Dimensionaal model (star schema)
│   ├── cli.py                     # CLI entry point
│   └── metadata/                  # Veldindelingen / codeboeken
├── app/
│   ├── main.py                    # Streamlit-app (geen bedrijfslogica)
│   └── config.toml                # Datapaden
└── tests/                         # pytest op de demo-data
```

## How to Run
- Dependencies: `uv sync`
- App: `uv run streamlit run app/main.py`
- Tests + lint: `MBO_PSEUDONIMISERING_SALT="ci-test-key-do-not-use-in-production" uv run pytest`
- Pipeline (Python): `run_pipeline(source, target)` uit `pipeline.py`
- De pipeline pseudonimiseert persoons-identifiers en faalt zonder een geldige salt (fail-closed, zie env-var `MBO_PSEUDONIMISERING_SALT`).

## Releases
Alleen via een tag op `main`; `.github/workflows/release.yml` is de gate.
1. PR die `version` in `pyproject.toml` ophoogt → merge naar `main`.
2. Wacht tot CI en Docs op `main` groen zijn.
3. `git fetch && git tag vX.Y.Z origin/main && git push origin vX.Y.Z`.

De workflow controleert dat de tag op `main` staat, gelijk is aan de
pyproject-versie en dat CI én Docs voor die commit groen zijn, en maakt dan
de GitHub Release met notes gegenereerd uit de gemergde PR's.
**Nooit** zelf `gh release create` draaien of handmatig release-notes met
cijfers/issuenummers schrijven — dat omzeilt de gate.

## Data
- **Input**: ruwe DUO-bekostigingsbestanden in `data/01-raw/`. Multi-record,
  `;`-gescheiden (regeltypes `VLP`/`PER`/`ISG`/…) plus XML (TBGI). Demo-data
  staat in submappen `h15/`, `h16/`, `h17/`.
- **Output**: schone Parquet in `data/02-prepared/` of `data/03-output/`.
- Echte data is gitignored; alleen demo-data in `data/*/demo/` staat in git
  (overgenomen uit `cedanl/duo-mbo-datafiles`).
- **Privacy**: RO- en GRONDSLAG-data is persoonsniveau (PER-records). Persoonsidentificerende gegevens (Burgerservicenummer, Onderwijsnummer) worden verwijderd uit de star-output. Persoons-identifiers worden gepseudonimiseerd via HMAC-SHA256 met een configureerbare salt via env-var `MBO_PSEUDONIMISERING_SALT` (fail-closed; `app/config.toml` alleen voor lokale demo). Geen BSN/ONr en geen echte salt committen; alleen demo-data in repo.
- **Deployment**: de Streamlit-app is uitsluitend voor lokaal/demo-gebruik en wordt nooit gehost (ook niet op SURF, geen SRAM). Voeg geen login, exportrechten of audit-logging toe zonder nieuw besluit (zie #82).
