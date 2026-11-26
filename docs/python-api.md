---
icon: lucide/code
---

# Python-API en kwaliteitsrapport

Gebruik de pipeline vanuit Python in plaats van de [CLI](aan-de-slag.md#cli) of de [app](aan-de-slag.md#interactieve-app). Deze pagina beschrijft ook het `quality.json` dat elke run schrijft, hoe je het analysemodel in Excel gebruikt en hoe je de tests draait.

## Eén bestand verwerken

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
| `status` | Status van de brondata van deze levering: `fail` bij errors, `warn` bij alleen warnings, anders `pass`; dezelfde regel als `summary.status` van het analysemodel (#285) |
| `slr_status` / `slr_details` | Gelezen recordaantallen tegen de controletotalen in het sluitrecord (`match`, `mismatch` of `unknown`). Een `mismatch` is een onvolledige levering en dus een `error` (#413) |
| `parseverlies` | Per recordtype en kolom het aantal gevulde bronwaarden dat na typering leeg is (ongeldige datum of getal); een error, dus exitcode 3 tenzij `--allow-quality-errors` (#390) |
| `onbekende_datums` | Per recordtype en kolom het aantal datums met jaar `0000`: null in de output, precisie `onbekend`; een warning (#391) |
| `conformiteit` | Wat de uitkomst betekent, naast of ze klopt (#331): `pve_versie` (gebruikte PvE-bronversie), `pve_bron_integriteit` (`pass`/`fail`: manifest-hash en upstream-check, #299), `pve_inhoudelijke_conformiteit` (`niet_beoordeeld`: veld- en businessregelconformiteit nog niet formeel afgetekend, #364), `indicatoren` (per JR/DR een `status`, `formeel_gebruik` (`uitgesloten`, besluit #296) en `afwijkingen`; nu `proxy`, want JR/DR zijn geen formele Inspectie-indicatoren, #296/#297/#369), `privacyprofiel` (`gepseudonimiseerd`, sinds v4.0.0 ook voor brondata (#173); `brondata` komt alleen voor in rapporten van vóór v4.0.0) en `pgn_stabiliteit` (#128) |
| `regelinventaris` | Bij TBGI (XML): `onbekende_xml_elementen`, per groep en tagnaam het aantal XML-elementen dat het schema niet kent (warning, #324; de elementen zelf staan als ruwe XML met hun plaats in de brondatatabel `OnbekendeXML`, #420); en `onleesbare_xml_velden`, schemavelden met een genest element en zonder eigen waarde, met aantal en plaats (bijv. `Diploma[1]/Opleidingcode`): de waarde is niet ingelezen, een error (#421). Bij CSV: per kolom het aantal regels waarin een positie buiten het PvE (bijv. `Postcodecijfers_positie19`) verschilt van het veld dat ze meestal herhaalt; betekenis onbekend, de waarde staat in de brondata (#260). Een onbekend recordtype, een gevuld veld voorbij het schema of een ontbrekend verplicht achterveld wordt niet gerapporteerd — de ingest breekt daar meteen op (fail-closed, #257, #281), vóórdat `quality.json` geschreven wordt |
| `domeinafwijkingen` | Per recordtype en veld het aantal (`aantal`) waarden buiten hun waardedomein, bij een veld uit `verplichte_velden` van het schema (PvE "Verplicht: Ja") inclusief lege waarden (apart als `leeg`, altijd `error`, #320, #419; ook een verplicht veld zonder domein staat er dan in) (patroon of waardenlijst uit `metadata/waardenlijsten.toml`, per veld gekoppeld via `domeinen` in het schema) en de ernst (`ernst`: `error` of `warning`, per domein ingesteld). Waarden binnen het domein maar buiten hun geldigheidsperiode (`buiten_geldigheid`) en tijdgebonden waarden zonder peildatum (`zonder_peildatum`) staan ernaast, tellen niet mee in `aantal` en geven alleen een `warning` (#325, #360). Een afwijking wijst vaak op een verschoven veldindeling, bijv. een DUO-versie die een positie weglaat; voor structurele velden (BRIN, Studiejaar) staat de ernst op `error` (#238) |
| `warnings` / `errors` | Leesbare meldingen; de app toont ze op Home |
| `bronbestand` | Het ruwe bestand: `naam` (geen pad), `sha256` en `pve_versie`: de PvE-versie van de schema's waarmee het is ingelezen (`metadata/pve_bron.json`), niet een versie uit het bestand zelf (#300, #298) |

De `quality.json` van `run_star` legt in `provenance` vast waarmee de run is gemaakt: `pakketversie`, `git_commit` (leeg buiten een checkout van dit project) en `referentiemanifest_sha256`. De bronbestanden staan per levering onder `deliveries[].bronbestand` en als kolommen in `meta_leveringen`. Er staan geen paden of persoonsgegevens in (#300).

De `quality.json` van `run_star` bevat daarnaast `star.dekking`: per levering en recordtype het aantal ingelezen records (`ingelezen`) tegen het aantal rijen in het analysemodel (`bereikt`, in `feit`). De aantallen hoeven niet gelijk te zijn: canonicalisatie en koppelingen halen rijen weg. Maar een gevuld recordtype waarvan niets het model bereikt, wordt niet doorvertaald. Dat is een `error` voor bekostigingsrecords (BII, BID, TBG-i Teldatum en Diploma) en anders een `warning` (#295). DIP, ISE en ISG hebben geen eigen feit maar vullen kolommen van `fact_inschrijving`: `bereikt` telt dan de rijen waarin die kolommen gevuld zijn, en 0 is een `warning` (#326). Recordtypes zonder eigen feit en zonder kolommen (VLP, SLR, PER, TBG-i Inschrijving/Signaal/BekostigingsrelevanteBPV) staan er met een `verklaring` in plaats van een telling. Een onbekend recordtype krijgt een `warning`.

`star.periode_koppelstatus` telt per detail-feit hoe de rijen aan hun inschrijvingsperiode hangen (#121). Rijen die op de eerste periode terugvielen (datum leeg, vóór de eerste periode of geen datumkolom) geven een `info`-melding. In Resultaten kun je een detail-feit filteren op `_periode_koppel_status`.

`star.referentiedata` noemt per referentietabel de bron, de datum van opname, de dekking en de sha256 (#132). Er komt een `warning` als een bestand afwijkt van `metadata/referentiedata.json`. Er komt er ook een als de data opleidingscodes bevat die de referentie niet kent, in inschrijvingen die beginnen ná de dekking van de referentie. Dan is de referentie waarschijnlijk verouderd: werk haar bij met `uv run python scripts/update_sbb_koppeltabel.py`, dat ook het manifest bijwerkt.

## Star schema bouwen

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

## Star schema lezen (zonder herverwerking)

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

## Leveringen stapelen (laag-niveau)

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

Schema-drift (bijv. `BRIN` wel in GRONDSLAG-ISG maar niet in RO-ISG)
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
slaat de fase die het analysemodel bouwt af (zie [Privacy en pseudonimisering](privacy.md#wat-is-pseudonimisering-in-deze-tool)).
