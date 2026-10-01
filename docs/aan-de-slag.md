# Aan de slag

## Vereisten

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- `MBO_PSEUDONIMISERING_SALT` (zie [Pseudonimisering](#pseudonimisering))

## Installatie

```bash
uv sync
export MBO_PSEUDONIMISERING_SALT="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
```

---

## Pseudonimisering

Persoons-identifiers (BSN, Onderwijsnummer, PGN) worden met HMAC-SHA256
gehasht, samen met hun soort: een PGN, BSN en ONr met dezelfde cijfers krijgen
een verschillend `_persoon_id`. Dat vereist een salt, ingesteld via de env-var:

```bash
export MBO_PSEUDONIMISERING_SALT="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
```

Zonder geldige salt faalt de stap die het analysemodel bouwt (`mbo star`, "Bouw
analysemodel" in de app; fail-closed). De stap die brondata schrijft (`mbo verwerk`,
"Verwerk bestanden") heeft geen salt nodig en pseudonimiseert niet: de brondata in
`02-prepared/` bevat BSN/ONr in platte tekst.

- **Productie:** de salt komt uitsluitend uit de environment (secret manager,
  bijv. via het deploymentplatform). Geen salt in de repo of in
  applicatieconfig opslaan.
- **Lokale demo:** het `export`-commando hierboven genereert een willekeurige
  salt per shell. Bewaar die zelf als je pseudoniemen tussen sessies wilt
  kunnen koppelen.
- **Tests/CI:** gebruiken de vaste, publieke waarde
  `ci-test-key-do-not-use-in-production`. Die is herleidbaar en hoort dus
  nooit bij echte data.
- `app/config.toml` heeft nog een `[security] pseudonimisering_salt`-fallback
  voor oude setups, maar de meegeleverde config bevat bewust géén salt meer.
  Gebruik die fallback niet voor echte data; een echte salt hoort er niet thuis.

### Opslag en retentie van brondata

De brondata (`data/02-prepared/`) is persoonsgegevens: ze bevat BSN/Onderwijsnummer in
platte tekst (#173). Ga ermee om als met de ruwe bestanden in `data/01-raw/`:

- **Opslag:** alleen lokaal, op een schijf met toegangsbeperking van de gebruiker; nooit in git
  (echte data is gitignored), nooit op een gedeelde of gehoste omgeving. De app wordt niet
  gehost (#82).
- **Retentie:** bewaar de brondata niet langer dan nodig om het analysemodel te bouwen.
  Het analysemodel (`03-output/`) bevat geen bronidentifiers en kan zonder de brondata
  worden bewaard; de brondata is opnieuw te maken uit de ruwe bestanden.
- **Verwijderen:** verwijder `02-prepared/` zodra het analysemodel gebouwd en gecontroleerd is.
  Een pseudoniem uit het analysemodel is alleen te koppelen met dezelfde salt.
- **Structurele oplossing:** pseudonimiseren vóór het wegschrijven van brondata staat in #173.

---

## Interactieve app

```bash
uv run streamlit run app/main.py
```

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

Navigeer naar **Resultaten** om de tabellen te bekijken en te downloaden als CSV.

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

`mbo star` eindigt met exitcode 3 als `quality.json` de status `fail` heeft (#289). De ster wordt dan niet gepubliceerd: ster en rapport staan als diagnose in `<output>/diagnose/`, en een eerdere publicatie in `<output>/datamodel/` blijft ongewijzigd (#363). Met `--allow-quality-errors` bouwt de run door voor exploratief werk; dat staat in `provenance.kwaliteitsfouten_toegestaan` (ster) en in `kwaliteitsfouten_toegestaan` van het leveringsrapport (prepared, #394). Een kapot bronbestand geeft exitcode 1 met een korte melding (#291). De app blijft bouwen en toont de fout op Home (#290).

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

Naast de tabellen schrijft elke run een `quality.json` in de doelmap:

| Sleutel | Betekenis |
|---|---|
| `slr_status` / `slr_details` | Gelezen recordaantallen tegen de controletotalen in het sluitrecord (`match`, `mismatch` of `unknown`) |
| `parseverlies` | Per recordtype en kolom het aantal gevulde bronwaarden dat na typering leeg is (ongeldige datum of getal); een error, dus exitcode 3 tenzij `--allow-quality-errors` (#390) |
| `onbekende_datums` | Per recordtype en kolom het aantal datums met jaar `0000`: null in de output, precisie `onbekend`; een warning (#391) |
| `conformiteit` | Wat de uitkomst betekent, naast of ze klopt (#331): `pve_versie` (gebruikte PvE-bronversie), `pve_bron_integriteit` (`pass`/`fail`: manifest-hash en upstream-check, #299), `pve_inhoudelijke_conformiteit` (`niet_beoordeeld`: veld- en businessregelconformiteit nog niet formeel afgetekend, #364), `indicatoren` (per JR/DR een `status` en `afwijkingen`; nu `proxy`, want JR/DR zijn geen formele Inspectie-indicatoren, #296/#297/#369), `privacyprofiel` (`gepseudonimiseerd` voor het analysemodel; brondata-rapporten dragen `brondata`) en `pgn_stabiliteit` (#128) |
| `regelinventaris` | Bij TBGI (XML): `onbekende_xml_elementen`, per groep en tagnaam het aantal XML-elementen dat het schema niet kent (warning, #324). Bij CSV: per kolom het aantal regels waarin een positie buiten het PvE (bijv. `Postcodecijfers_positie19`) verschilt van het veld dat ze meestal herhaalt; betekenis onbekend, de waarde staat in de brondata (#260). Een onbekend recordtype, een gevuld veld voorbij het schema of een ontbrekend verplicht achterveld wordt niet gerapporteerd — de ingest breekt daar meteen op (fail-closed, #257, #281), vóórdat `quality.json` geschreven wordt |
| `domeinafwijkingen` | Per recordtype en veld het aantal (`aantal`) waarden buiten hun waardedomein, bij een verplicht veld (BRIN, Studiejaar) inclusief lege waarden (apart als `leeg`, #320) (patroon of waardenlijst uit `metadata/waardenlijsten.toml`, per veld gekoppeld via `domeinen` in het schema) en de ernst (`ernst`: `error` of `warning`, per domein ingesteld). Waarden binnen het domein maar buiten hun geldigheidsperiode (`buiten_geldigheid`) en tijdgebonden waarden zonder peildatum (`zonder_peildatum`) staan ernaast, tellen niet mee in `aantal` en geven alleen een `warning` (#325, #360). Een afwijking wijst vaak op een verschoven veldindeling, bijv. een DUO-versie die een positie weglaat; voor structurele velden (BRIN, Studiejaar) staat de ernst op `error` (#238) |
| `warnings` / `errors` | Leesbare meldingen; de app toont ze op Home |
| `bronbestand` | Het ruwe bestand: `naam` (geen pad), `sha256` en `pve_versie`: de PvE-versie van de schema's waarmee het is ingelezen (`metadata/pve_bron.json`), niet een versie uit het bestand zelf (#300, #298) |

De `quality.json` van `run_star` legt in `provenance` vast waarmee de run is gemaakt: `pakketversie`, `git_commit` (leeg buiten een checkout van dit project) en `referentiemanifest_sha256`. De bronbestanden staan per levering onder `deliveries[].bronbestand` en als kolommen in `meta_leveringen`. Er staan geen paden of persoonsgegevens in (#300).

De `quality.json` van `run_star` bevat daarnaast `star.dekking`: per levering en recordtype het aantal ingelezen records (`ingelezen`) tegen het aantal rijen in het analysemodel (`bereikt`, in `feit`). De aantallen hoeven niet gelijk te zijn: canonicalisatie en koppelingen halen rijen weg. Maar een gevuld recordtype waarvan niets het model bereikt, wordt niet doorvertaald. Dat is een `error` voor bekostigingsrecords (BII, BID, TBG-i Teldatum en Diploma) en anders een `warning` (#295). DIP, ISE en ISG hebben geen eigen feit maar vullen kolommen van `fact_inschrijving`: `bereikt` telt dan de rijen waarin die kolommen gevuld zijn, en 0 is een `warning` (#326). Recordtypes zonder eigen feit en zonder kolommen (VLP, SLR, PER, TBG-i Inschrijving/Signaal/BekostigingsrelevanteBPV) staan er met een `verklaring` in plaats van een telling. Een onbekend recordtype krijgt een `warning`.

`star.periode_koppelstatus` telt per detail-feit hoe de rijen aan hun inschrijvingsperiode hangen (#121). Rijen die op de eerste periode terugvielen (datum leeg, vóór de eerste periode of geen datumkolom) geven een `info`-melding. In Resultaten kun je een detail-feit filteren op `_periode_koppel_status`.

`star.referentiedata` noemt per referentietabel de bron, de datum van opname, de dekking en de sha256 (#132). Er komt een `warning` als een bestand afwijkt van `metadata/referentiedata.json`. Er komt er ook een als de data opleidingscodes bevat die de referentie niet kent, in inschrijvingen die beginnen ná de dekking van de referentie. Dan is de referentie waarschijnlijk verouderd: werk haar bij met `uv run python scripts/update_sbb_koppeltabel.py`, dat ook het manifest bijwerkt.

### Star schema bouwen

```python
from mbo_bekostiging_bestanden.pipeline import run_star

star = run_star(
    sources=[
        "data/02-prepared/demo/h15/RO_27DV_20240731_20260324",
        "data/02-prepared/demo/h16/TBGI_25LX_2027_20251124",
        "data/02-prepared/demo/h17/GRONDSLAG_IP_MBO_27DV_20251119_2025",
    ],
    target="data/03-output/demo/star",
    relative_to="data/02-prepared/demo",
)

star["fact_inschrijving"]        # één rij per inschrijvingsperiode
star["fact_bpv"]                 # alle BPV-overeenkomsten
star["fact_kzd"]                 # keuzedelen per inschrijving
star["fact_bekostiging"]         # bekostigingsdetail (BII / TBGI Teldatum)
star["meta_leveringen"]          # VLP + SLR metadata per levering
star["dim_deelnemer"]            # persoonskenmerken
star["dim_opleiding"]            # CREBO-attributen
star["dim_instelling"]           # instellingsnamen
```

### Star schema lezen (zonder herverwerking)

```python
import polars as pl
from mbo_bekostiging_bestanden.publicatie import lees_ster

star = lees_ster("data/03-output/demo/star")  # weigert een ster met status fail
fact = star["fact_inschrijving"]

# Hoeveel bekostigde inschrijvingen per levering?
fact.filter(pl.col("IndicatieBekostigbaar") == "J") \
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

`fact_inschrijving` heeft grain = inschrijvingsperiode (ISP). De aggregaten
`BPV_*`, `KZD_*` en `AMO_*` gelden per periode: elke BPV, elk keuzedeel en elk
AMO-onderdeel telt mee in precies één periode (dezelfde als zijn
`_inschrijving_periode_id` in het detail-feit). Je kunt ze dus direct optellen
over `fact_inschrijving` zonder dubbeltelling.
Voor afzonderlijke BPV-regels gebruik je `fact_bpv.parquet`.

---

## Tests

```bash
export MBO_PSEUDONIMISERING_SALT="ci-test-key-do-not-use-in-production"  # alleen tests/CI
uv run pytest
```

De tests draaien fail-closed op de pseudonimiserings-salt; zonder de env-var
slaat de fase die het analysemodel bouwt af (zie [Pseudonimisering](#pseudonimisering)).

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
    └── star/
        ├── quality.json   ← rapport bij de gepubliceerde ster
        ├── diagnose/      ← alleen na een run met status fail: datamodel/ + quality.json, niet gepubliceerd
        └── datamodel/
            ├── dim_deelnemer.parquet
            ├── dim_opleiding.parquet
            ├── dim_instelling.parquet
            ├── fact_inschrijving.parquet
            ├── fact_bpv.parquet
            ├── fact_kzd.parquet
            ├── fact_amo.parquet
            ├── fact_geo.parquet
            ├── fact_bekostiging.parquet
            ├── fact_bekostiging_diploma.parquet
            └── meta_leveringen.parquet
```

Echte data zet je in `data/01-raw/` buiten de `demo/`-submap — die staat in `.gitignore`.
