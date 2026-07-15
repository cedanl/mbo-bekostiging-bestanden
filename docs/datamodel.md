# Datamodel

De ETL levert twee outputformaten: een platte OBT en een dimensionaal model
(star schema). Beide bevatten dezelfde data; het star schema splitst de
dimensie-attributen af in aparte tabellen.

---

## OBT (standaard)

Eén brede tabel (`obt_inschrijvingen.parquet`) op ISP-grain met alle
dimensie-attributen, berekende vlaggen en aggregaten erin gebakken.
Ideaal voor directe analyse in Excel, Python of Power BI zonder joins.

Aanvullende detailtabellen: `detail_bpv`, `detail_kzd_amo`,
`detail_bekostiging`, `meta_leveringen`.

## Star schema (optioneel)

Geëxporteerd naar `datamodel/` wanneer `run_obt(..., star=True)`.

```
                    ┌──────────────────┐
                    │  dim_deelnemer   │
                    ├──────────────────┤
                    │ _persoon_id (PK) │
                    │ Geboortedatum    │
                    │ Geslacht         │
                    │ Postcodecijfers  │
                    │ Gemeente         │
                    │ Nationaliteit1*  │
                    │ CodeGeboorteland*│
                    │ ...              │
                    └────────┬─────────┘
                             │
┌──────────────────┐         │         ┌──────────────────┐
│  dim_opleiding   │         │         │  dim_instelling  │
├──────────────────┤         │         ├──────────────────┤
│ Opleidingcode(PK)│    ┌────┴────┐    │ BRIN (PK)        │
│ Niveau           │    │  fact_  │    │ Instelling_naam  │
│ Opleiding_naam   ├────┤inschri- ├────┤ Instelling_plaats│
│ Opleiding_domein │    │ jving   │    └──────────────────┘
│ Opleiding_subgrp │    ├─────────┤
│ Opleiding_dossier│    │ levering│
│ Opleiding_leerweg│    │_pers_id │◄── FK naar dim_deelnemer
│ Opl_sectorkamer  │    │Oplcode  │◄── FK naar dim_opleiding
└──────────────────┘    │BRIN     │◄── FK naar dim_instelling
                        │Studiejr │
                        │ ─vlaggen─│
                        │_telling  │
                        │_actief.. │
                        │_jr_*     │
                        │_entree_* │
                        │ ─aggr──  │
                        │BPV_*     │
                        │KZD_*     │
                        │GEO_*     │
                        └─────────┘
```

### Tabellen

| Tabel | Grain | Sleutel | Kolommen |
|---|---|---|---|
| `dim_deelnemer` | Persoon | `_persoon_id` | ~21 |
| `dim_opleiding` | Opleiding | `Opleidingcode` | ~8 |
| `dim_instelling` | Instelling | `BRIN` | 3 |
| `fact_inschrijving` | ISP (inschrijvingsperiode) | `_persoon_id` + `Opleidingcode` + `BRIN` + `levering` | ~92 |

### Relatie met QlikView-referentiemodel

Het referentiemodel (zie `ondersteunend-materiaal/`) bevat twee fact-tabellen:

| QlikView | Deze ETL | Status |
|---|---|---|
| `Facttabel` | `fact_inschrijving` | Geïmplementeerd |
| `Studiesucces` (JR/DR/SR) | — | DR/SR vereist cohortlogica over meerdere jaren; gedeferd |
| `CREBOs` | `dim_opleiding` | Geïmplementeerd |
| `Deelnemers` | `dim_deelnemer` | Geïmplementeerd |
| `Organisatie` | — | Instellingsspecifiek (teams, kostenplaatsen); extensiepunt |
| `VSV startsets` | — | Vereist aparte DUO-levering; buiten scope |
