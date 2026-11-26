---
icon: lucide/rocket
---

# Snel starten

Installeer de tool, draai de app of de CLI en vind je uitvoer terug in `data/`. Voor gebruik vanuit Python zie [Python-API](python-api.md).

## Vereisten

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- `MBO_PSEUDONIMISERING_SALT`, tenzij je bewust [identifiers behoudt](privacy.md#identifiers-behouden) (zie [Privacy en pseudonimisering](privacy.md))

## Installatie

```bash
uv sync
export MBO_PSEUDONIMISERING_SALT="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
```

### Windows

Gebruik PowerShell (de `export`-syntax werkt daar niet):

```powershell
uv sync
$env:MBO_PSEUDONIMISERING_SALT = python -c "import secrets; print(secrets.token_hex(32))"
uv run streamlit run app/main.py
```

In `cmd.exe`:

```bat
uv sync
for /f %i in ('python -c "import secrets; print(secrets.token_hex(32))"') do set "MBO_PSEUDONIMISERING_SALT=%i"
uv run streamlit run app/main.py
```

De variabele geldt alleen voor het huidige venster. Genereer de salt niet met
`%RANDOM%`: dat levert te weinig entropie voor een pseudonimiseringssleutel.

---

## Pseudonimisering en privacy

Persoons-identifiers (BSN, onderwijsnummer, PGN) worden bij het verwerken vervangen door het pseudoniem `_persoon_id`. Dat vereist een salt in de env-var `MBO_PSEUDONIMISERING_SALT` (zie [Installatie](#installatie)). Wat dit betekent, hoe je de salt beheert, hoe je bewust identifiers behoudt en hoe je brondata opslaat en verwijdert, staat op [Privacy en pseudonimisering](privacy.md).

---

## Interactieve app

```bash
uv run streamlit run app/main.py
```

Op Home kies je de invoer: de **vaste invoermap** (`[data] raw` in
`app/config.toml`) of **bestanden selecteren**. Gekozen bestanden worden in een
tijdelijke werkmap gezet en daarna net zo verwerkt; de invoermap blijft
ongemoeid. De brondata en het analysemodel komen op dezelfde plek als bij de
vaste map (`[data] prepared` en `output`).

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

Open **Werkbare data** (brondata per levering) of **Analysemodel** (star schema) in de zijbalk
om de tabellen te bekijken en te downloaden als CSV. Onder aan elke pagina download je
alle tabellen van die pagina in één keer als zip met CSV's (persoonsgegevens standaard verborgen).

---



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

`mbo verwerk` vervangt de doelmap in zijn geheel en pas na de kwaliteitspoort: een herverwerking laat geen tabellen van een eerdere bron achter (#414). Bij status `fail` eindigt het met exitcode 3, blijft een eerdere versie in de doelmap ongewijzigd en staan tabellen en rapport in `<doel>/diagnose/` (#415). Een doelmap die niet leeg is en geen eerdere brondata bevat, weigert `mbo verwerk`.

`mbo star` eindigt met exitcode 3 als `quality.json` de status `fail` heeft (#289). De ster wordt dan niet gepubliceerd: ster en rapport staan als diagnose in `<output>/diagnose/`, en een eerdere publicatie in `<output>/datamodel/` blijft ongewijzigd (#363). Met `--allow-quality-errors` bouwt de run door voor exploratief werk; dat staat in `provenance.kwaliteitsfouten_toegestaan` (ster) en in `kwaliteitsfouten_toegestaan` van het leveringsrapport (prepared, #394). Een kapot bronbestand geeft exitcode 1 met een korte melding (#291). De app blijft bouwen en toont de fout op Home (#290).

---

## Datastructuur

```
data/
├── 01-raw/demo/
│   ├── h15/   ← RO-bestanden (Registratieoverzicht)
│   ├── h16/   ← TBGI XML (bekostigingsgrondslagen)
│   └── h17/   ← GRONDSLAG IP MBO
├── 02-prepared/demo/
│   ├── h15/RO_27DV_20240731_20260324/   ← één submap per bronbestand (volledige naam); bij een fout ook diagnose/
│   ├── h16/TBGI_25LX_2027_20251124/
│   └── h17/GRONDSLAG_IP_MBO_27DV_20251119_2025/
└── 03-output/demo/
    └── star/
        ├── quality.json   ← rapport bij de gepubliceerde ster
        ├── diagnose/      ← alleen na een run met status fail: datamodel/ + quality.json, niet gepubliceerd
        └── datamodel/
            ├── dim_deelnemer.parquet
            ├── dim_opleiding.parquet
            ├── dim_instelling.parquet
            ├── fact_inschrijving.parquet
            ├── fact_inschrijving_schooljaar.parquet
            ├── fact_bpv.parquet
            ├── fact_kzd.parquet
            ├── fact_amo.parquet
            ├── fact_geo.parquet
            ├── fact_bekostiging.parquet
            ├── fact_bekostiging_diploma.parquet
            ├── meta_leveringen.parquet
            ├── meta_canonicalisatie.parquet
            ├── meta_referentiedata.parquet
            └── meta_koppelkeuzes.parquet
```

Echte data zet je in `data/01-raw/` buiten de `demo/`-submap — die staat in `.gitignore`.
