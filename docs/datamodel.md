# Datamodel

De ETL produceert een star schema: drie dimensietabellen en zeven feittabellen.
Het star schema staat in `<output>/datamodel/` en is de primaire output van de
pipeline. Het OBT (Object Betrokkenheid Tabel) is een interne tussenstap die
niet naar schijf wordt geschreven.

---

## Star schema

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
                        │_dr_*     │
                        │_entree_* │
                        └─────────┘
```

### Tabellen

| Tabel | Grain | Sleutelkolom(men) | Omschrijving |
|---|---|---|---|
| `dim_deelnemer` | Persoon | `_persoon_id` | Persoonskenmerken (geslacht, geboorteland, gemeente …) |
| `dim_opleiding` | Opleiding | `Opleidingcode` | CREBO-attributen incl. S-BB koppeltabel |
| `dim_instelling` | Instelling | `BRIN` | Naam en vestigingsplaats |
| `fact_inschrijving` | ISP-inschrijvingsperiode | `_persoon_id` + `Opleidingcode` + `BRIN` + `levering` | Centrale feittabel; bevat vlaggen (`_actief_1_oktober`, `_jr_*`, `_dr_*`, `_entree_*`) en aggregaten |
| `fact_bpv` | BPV-overeenkomst | `_persoon_id` + `Inschrijvingvolgnummer` + `Volgnummer` | Alle BPV-periodes per inschrijving |
| `fact_kzd` | Keuzedeel-resultaat | `_persoon_id` + `Inschrijvingvolgnummer` + `Resultaatvolgnummer` | KZD-resultaten per inschrijving |
| `fact_amo` | AMO-resultaat | `_persoon_id` + `Inschrijvingvolgnummer` + `Resultaatvolgnummer` | AMvB-onderdelen per inschrijving |
| `fact_geo` | GEO-examenonderdeel | `_persoon_id` + `Inschrijvingvolgnummer` + `CodeGeneriekExamenonderdeel` | Eindcijfers IE/CE per onderdeel in long format |
| `fact_bekostiging` | TBGI Teldatum | `_persoon_id` + `Inschrijvingvolgnummer` + `Teldatum` | Bekostigingsgrondslagen per inschrijving per teldatum (1-10 / 1-2) |
| `fact_bekostiging_diploma` | TBGI Diploma | `_persoon_id` + `Inschrijvingvolgnummer` + `Resultaatvolgnummer` | Diplomawaarde-bijdragen (`BijdrageDiplomawaarde`) per behaald diploma |

Alle feittabellen zijn joinbaar met `fact_inschrijving` via `(levering, _persoon_id, Inschrijvingvolgnummer)`.
`fact_bekostiging` en `fact_bekostiging_diploma` zijn ook joinbaar met `dim_instelling` via `BRIN`.

### Indicatoren in fact_inschrijving

| Vlag | Definitie |
|---|---|
| `_actief_1_oktober` | Inschrijving actief op 1 oktober (teldatum) |
| `_hoofdinschrijving` | Eerste inschrijving van de deelnemer bij deze instelling |
| `_gediplomeerd_in_jaar` | Diploma behaald in het studiejaar |
| `_jr_noemer` / `_jr_teller` | Populatie en teller voor Jaarresultaat (JR) |
| `_dr_noemer` / `_dr_teller` | Populatie en teller voor Diplomaresultaat (DR) |
| `_entree_doorstroom` / `_entree_uitstroom` | Niveau-1 doorstroom- en uitstroomcategorieën |

### Relatie met QlikView-referentiemodel

| QlikView | Deze ETL | Status |
|---|---|---|
| `Facttabel` | `fact_inschrijving` | Geïmplementeerd |
| `Studiesucces` JR | `_jr_noemer` / `_jr_teller` in `fact_inschrijving` | Geïmplementeerd |
| `Studiesucces` DR | `_dr_noemer` / `_dr_teller` in `fact_inschrijving` | Geïmplementeerd |
| `Studiesucces` SR | — | Vereist 6-jaar inschrijvingshistorie buiten eigen leveringen; buiten scope |
| `CREBOs` | `dim_opleiding` | Geïmplementeerd |
| `Deelnemers` | `dim_deelnemer` | Geïmplementeerd |
| `Organisatie` | — | Instellingsspecifiek (teams, kostenplaatsen); extensiepunt |
| `VSV startsets` | — | Vereist aparte DUO-levering; buiten scope |
