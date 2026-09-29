# Datamodel

De ETL produceert een star schema: drie dimensietabellen, zeven feittabellen en
één metadata-tabel. Het star schema staat in `<output>/datamodel/` en is de
enige output van de pipeline. Interne analysetabellen worden niet naar schijf
geschreven.

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
| `dim_deelnemer` | Persoon | `_persoon_id` | Persoonskenmerken (geslacht, geboorteland, gemeente …). `Geboortedatum_precisie` (`dag`/`maand`/`jaar`) geeft aan of dag of maand onbekend was (`00` in de bron); de datum is dan de 1e van de maand/het jaar |
| `dim_opleiding` | Opleiding | `Opleidingcode` | CREBO-attributen incl. S-BB koppeltabel |
| `dim_instelling` | Instelling | `BRIN` | Naam en vestigingsplaats van elke BRIN in de feiten (ook als die alleen in de bekostiging voorkomt) |
| `fact_inschrijving` | ISP-inschrijvingsperiode, of TBGI-inschrijving zonder ISP | `_inschrijving_periode_id` | Centrale feittabel op periode-grain (bronreconstructie); bevat periode-attributen en aggregaten. `Bron` = `ISP` (RO/GRONDSLAG-periode) of `TBGI` (inschrijving die alleen in TBG-i staat, #196). De jaargebonden vlaggen hierin zijn verouderd: gebruik `fact_inschrijving_schooljaar` |
| `fact_inschrijving_schooljaar` | Persoon × instelling × inschrijving × schooljaar | `BRIN` + `_persoon_id` + `Inschrijvingvolgnummer` + `Schooljaar` | Eén rij per schooljaar waarin een inschrijving op de peildatum (1 oktober) actief is, met hoofdinschrijving, telling, bekostigd, JR, DR en Entree. FK `_inschrijving_periode_id` wijst de periode aan die de peildatum dekt |
| `fact_bpv` | BPV-overeenkomst | `_persoon_id` + `Inschrijvingvolgnummer` + `Volgnummer` | Alle BPV-periodes per inschrijving |
| `fact_kzd` | Keuzedeel-resultaat | `_persoon_id` + `Inschrijvingvolgnummer` + `Resultaatvolgnummer` | KZD-resultaten per inschrijving; `Behaald` (bool) is exact bepaald uit de waardenlijst (`Behaald`/`Niet behaald`), null bij een onbekende waarde |
| `fact_amo` | AMO-resultaat | `_persoon_id` + `Inschrijvingvolgnummer` + `Resultaatvolgnummer` | AMvB-onderdelen per inschrijving |
| `fact_geo` | GEO-examenonderdeel | `_persoon_id` + `Inschrijvingvolgnummer` + `CodeGeneriekExamenonderdeel` | Eindcijfers IE/CE per onderdeel in long format |
| `fact_bekostiging` | GRONDSLAG BII, TBGI Teldatum | `_persoon_id` + `Inschrijvingvolgnummer` + `Teldatum` | Bekostigingsgrondslagen per inschrijving per teldatum (1-10 / 1-2); `Bron` = `BII` of `TBGI` |
| `fact_bekostiging_diploma` | GRONDSLAG BID, TBGI Diploma | `_persoon_id` + `Inschrijvingvolgnummer` + `Resultaatvolgnummer` | Diplomawaarde-bijdragen (`BijdrageDiplomawaarde`) per behaald diploma; `Bron` = `BID` of `TBGI`. Een BID neemt `Inschrijvingvolgnummer`, `Opleidingcode` en `DatumBehaald` (= `DatumResultaat`) over van het DIP-record met hetzelfde `Resultaatvolgnummer` (#258) |
| `meta_leveringen` | Leveringsbestand | `levering` | Elke verwerkte levering, met VLP + SLR metadata (leveringsdatum, aantallen zoals `AantalBII`/`AantalBID`) waar het bestand die heeft; bij TBGI (XML) zijn die velden leeg. Observatievenster (#211): `Peilgrens` (laatste waarneembare datum), `Peilgrens_bron` (`DatumEindePeriode`, `DatumAanmaak` of bij TBGI `Teldatum`) en `Laatste_peildatum` (laatste 1 oktober die de levering kan waarnemen). Zelfde `levering`-labels als in de feiten en `quality.json` |
| `meta_koppelkeuzes` | Koppeling | `koppeling` | Per links-join (PER, ISG, VLP, ISE, DIP, GEO, BID.DIP, meta_leveringen): hoeveel sleutels meer dan één kandidaat hadden en hoeveel rijen daardoor wegvielen. De keuze hangt nooit af van de rijvolgorde; bij DIP wint de meest recente `DatumResultaat` (#209) |
| `meta_referentiedata` | Referentiebestand | `bestand` | Herkomst van de referentietabellen in `metadata/` uit `metadata/referentiedata.json` (#132): `bron`, `opgenomen` (datum van opname in de repo), `dekking_tot` (laatste datum waarvoor de lijst de opleidingen dekt; alleen bekend voor de S-BB-lijsten), `sha256`, `rijen`, en `afwijkend` als het bestand op schijf een andere inhoud heeft dan het manifest. `crebo.csv` en de andere CSV's zijn in #19 zonder herkomst opgenomen: hun `bron` is `onbekend` |
| `meta_canonicalisatie` | Leveringspaar | `levering`, `vervangen_door`, `reden` | Vervangen leveringen: aantal inschrijvingen en ISP-perioden dat door een recentere levering is vervangen; leeg zonder overlap |

**S-BB-attributen in `dim_opleiding`.** `Opleiding_geldig_van`/`Opleiding_geldig_tot` zijn de
looptijd van de kwalificatie in de S-BB-crebolijst, niet van de prijsfactor: een verlopen
code is voor inschrijvingen uit die looptijd gewoon correct. `Opleiding_prijsfactor` is de
referentiewaarde uit die lijst. De prijsfactor waarmee DUO werkelijk bekostigt, staat per
teldatum als `PrijsfactorMBO` in `fact_bekostiging`; gebruik die voor bekostigingsanalyses.

Alle detail-feiten zijn zonder fan-out joinbaar met `fact_inschrijving` via `_inschrijving_periode_id`.
Die sleutel wijst per detailrij de ISP-periode aan waarin de referentiedatum valt
(`DatumBegin` voor BPV, `DatumResultaat` voor KZD/AMO/GEO, `Teldatum` voor bekostiging,
`DatumBehaald` voor bekostiging_diploma); valt die datum vóór de eerste periode of ontbreekt
hij, dan geldt de eerste periode. Rijen zonder bijbehorende inschrijving hebben een lege sleutel.
Bij TBGI-only input (geen ISP) is elke TBGI-inschrijving één periode vanaf `DatumInschrijving`;
de sleutel en de koppelregel zijn verder gelijk, zodat het schema in beide routes uniform is.

**Bekostiging over leveringen heen.** TBGI-bekostiging komt altijd uit een andere levering dan
de RO-inschrijvingen. `fact_bekostiging` en `fact_bekostiging_diploma` koppelen daarom eerst
binnen hun eigen levering (bijv. BII in GRONDSLAG) en daarna — alleen als er een passende
inschrijving is — via `(BRIN, _persoon_id, Inschrijvingvolgnummer)` aan de ISP-periode waarin de
`Teldatum` (resp. `DatumBehaald`) valt. Staat dezelfde periode in meerdere leveringen, dan wint de
levering die alfabetisch als laatste komt (leveringsnamen eindigen op hun datums). Zonder
passende inschrijving blijft de sleutel leeg en meldt Home de rij als niet-gekoppeld.
Joinen op alleen `(levering, _persoon_id, Inschrijvingvolgnummer)` dupliceert rijen zodra een
inschrijving meerdere ISP-perioden heeft.
`Inschrijvingvolgnummer` is alleen uniek per persoon binnen een instelling (PvE §16.5.1), dus
nooit zonder persoon joinen. Bij TBGI neemt het inlezen de BSN/ONr van de ouder-`<Inschrijving>`
(of `<Diploma>`) daarom al over op elke Teldatum- en Signaal-rij.
**Persoon over bronfamilies heen.** `_persoon_id` is een pseudoniem van *soort + nummer*
(PGN, BSN of ONr). GRONDSLAG levert een door DUO omgenummerd PGN in plaats van het BSN
(PvE 4.8.2 §17.1); een GRONDSLAG-student koppelt daarom nooit op persoon aan RO of TBGI.
RO en TBGI (beiden BSN/ONr) koppelen wel. Of het PGN over studiejaren gelijk blijft, is nog
niet door DUO bevestigd (#128); tot die tijd zijn persoonskoppelingen tussen
GRONDSLAG-leveringen van verschillende jaren niet gegarandeerd.
**Centrale laag over bronnen heen (#196).** `fact_inschrijving` bevat de ISP-perioden (RO, GRONDSLAG) én
de TBGI-inschrijvingen die daar níet al in staan (zelfde `BRIN × _persoon_id × Inschrijvingvolgnummer`).
Een inschrijving met ISP-perioden is rijker en blijft de parent; TBGI vult alleen aan, bijv. een student die
niet in de meegeleverde RO-bestanden staat. In `fact_inschrijving_schooljaar` telt een TBGI-rij in de
schooljaren van haar 1-oktober-teldata (#197).

**Relatiecontract per detail-feit.** Rijen zonder bijbehorende inschrijving worden gemeld
(`quality.controleer_koppelingen`, `quality.json` → `star.orphaned_facts`):

| Feit | Parent | Wees-rij is |
|---|---|---|
| `fact_bpv`, `fact_kzd`, `fact_amo`, `fact_geo` | ISP-periode via `_inschrijving_periode_id` | error |
| `fact_bekostiging` | inschrijving (ISP of TBGI) waarin de `Teldatum` valt | error |
| `fact_bekostiging_diploma` | inschrijving van het diploma, **optioneel bij `Bron` = `TBGI`** | `BID`: error (het DIP-record ontbreekt). `TBGI`: **verklaard** (geen error): TBG-i voor bekostigingsjaar T levert de diploma's van kalenderjaar T-2 los van de inschrijvingen van studiejaar T-2 (PvE §16.1); een diploma zonder inschrijving in de levering is normaal |
| `fact_inschrijving_schooljaar` | periode via `_inschrijving_periode_id` | error |

Uniciteitscontracten (elke schending is een error in `quality.json` → `star.key_duplicates`, en een melding
op de Home-pagina via `quality.controleer_sleuteluniciteit`):

| Contract | Uniek op |
|---|---|
| `fact_inschrijving` | `_inschrijving_periode_id` |
| `fact_inschrijving_schooljaar` | `BRIN × _persoon_id × Inschrijvingvolgnummer × Schooljaar` |
| `hoofdinschrijving_per_schooljaar` | `BRIN × _persoon_id × Schooljaar`, alleen rijen met `_hoofdinschrijving` |

Twee ISP-rijen van één inschrijving met dezelfde `DatumBegin` zijn een bronfout: beide dekken dezelfde
peildatum. De ster ontdubbelt dat niet stil; de geschonden contracten maken het zichtbaar (#200).

---

## Grain en Deduplicatie

**Interne kolommen.** Kolommen die met `_` beginnen zijn afgeleid door de pipeline (vlaggen, sleutels, herkomst),
geen DUO-velden. `_persoon_id` en `_inschrijving_periode_id` zijn sleutels; `_niveau_herkomst` en `Bron` leggen de
herkomst vast. Hulpkolommen die alleen tijdens de bouw bestaan (`_schooljaren_actief`, `_bron`, `_rij`) en de
persoons-identifiers (BSN, onderwijsnummer, PGN) komen niet in de ster.

**Tellingseenheid (grain).** Elke feitstabel hoort uniek te zijn per zijn eigen grain-kolommen (zie tabel "Grain" hierboven).
`fact_inschrijving` heeft de grain van een **ISP-periode**; een periode kan meerdere schooljaren dekken. Jaargebonden tellingen staan in `fact_inschrijving_schooljaar` (één rij per
`persoon × instelling × inschrijving × schooljaar`).

Een *levering* is een bronbestand van DUO (bijv. `RO_27DV_20240731.csv` of `GRONDSLAG_IP_MBO_27DV_20251119.csv`),
**geen** tellingseenheid. Dezelfde inschrijving kan in meerdere leveringen staan (herlevering, correctie, overlappende
periode).

**Canonicalisatie.** Een inschrijving is `BRIN × _persoon_id × Inschrijvingvolgnummer`. Staat die in meerdere
leveringen, dan telt alleen de **meest recente levering**:

1. hoogste `DatumAanmaak` uit het VLP-record van de levering;
2. bij gelijke of ontbrekende aanmaakdatum: de alfabetisch laatste leveringsnaam.

Alle rijen van die inschrijving uit oudere leveringen vallen weg — in ISP (dus vóór alle indicatoren) én in de
detailfeiten (`fact_bpv`, `fact_kzd`, `fact_amo`, `fact_geo`, bekostiging), zodat detailrijen altijd bij de gekozen
levering horen. Dit gebeurt in `_bouw_analysetabellen()` via `canonicalisatie.py`.

- **Per inschrijving, niet per levering:** een inschrijving die alleen in de oudere levering staat, blijft staan.
- **BRIN hoort bij de sleutel:** een inschrijvingvolgnummer is niet instellingsoverstijgend uniek.
- **Bronfamilies blijven gescheiden:** `_persoon_id` bevat het identifierdomein (PGN/BSN/ONR, #128), dus RO- en
  GRONDSLAG-inschrijvingen worden nooit samengevoegd.
- **Zonder volledige sleutel geen canonicalisatie:** rijen zonder BRIN, persoon of inschrijvingvolgnummer (bijv. een
  KZD/GEO-rij die niet via DIP aan een inschrijving te koppelen is) worden niet als dubbel aangemerkt.

**Voorbeeld:** dezelfde inschrijving in `RO_27DV_20240731.csv` (aangemaakt 2024-08-01) en `RO_27DV_20250801.csv`
(aangemaakt 2025-08-02): alle ISP-perioden en detailrijen van die inschrijving komen uit `RO_27DV_20250801`.

**Lineage.** Welke leveringen zijn vervangen, door welke en waarom (`recentere_aanmaakdatum` of `leveringsnaam`) staat
in de star-tabel `meta_canonicalisatie` en samengevat in `quality.json` onder `star.canonicalisatie`, met de toegepaste
regel en de aantallen vervangen inschrijvingen en ISP-perioden.

`check_overlapping_deliveries()` in `quality.py` controleert achteraf of `fact_inschrijving` nog een inschrijving
(`BRIN × _persoon_id × Inschrijvingvolgnummer`) uit meerdere leveringen bevat. Dat is dubbeltelling en maakt de
status `fail`.

`fact_bekostiging` en `fact_bekostiging_diploma` zijn ook joinbaar met `dim_instelling` via `BRIN`.
De bekostigingsrelevante BPV's (0..n per teldatum) en de TBGI-signalen (één rij per
parameter) staan als `BekostigingsrelevanteBPV` en `Signaal` in de prepared-output van een
TBGI-levering, niet in het star schema: ze zouden de teldatum-grain van `fact_bekostiging`
vermenigvuldigen.

### Indicatoren per schooljaar (`fact_inschrijving_schooljaar`)

Schooljaar `t` loopt van 1-8-t t/m 31-7-(t+1); de peildatum is **1-10-t**. Eén rij per inschrijving per schooljaar
waarvan een ISP-periode de peildatum dekt. Deze tabel is de bron voor tellingen, JR en DR.

| Kolom | Definitie |
|---|---|
| `Schooljaar`, `Peildatum` | Schooljaar `t` en peildatum 1-10-t |
| *Welke jaren* | Elk `t` met `DatumBegin ≤ 1-10-t ≤ einde`. Einde = `_periode_einde` (volgende periode − 1 dag, `DatumEind` of `DatumUitschrijvingWerkelijk`, de vroegste), **begrensd door de peildatum van de levering** (VLP `DatumEindePeriode`, anders `DatumAanmaak`). Een levering die geen enkele peildatum van haar perioden kan waarnemen (bijv. een GRONDSLAG-levering aangemaakt vóór 1 oktober) levert geen schooljaarrijen; `quality.json` → `star.leveringen_zonder_schooljaar` meldt dat als waarschuwing. Zonder einde en zonder peildatum: alleen het eerste schooljaar |
| *TBGI-inschrijvingen* | TBGI levert inschrijvingen, geen ISP-perioden. Een TBGI-inschrijving telt **alleen in de schooljaren van haar 1-oktober-`Teldatum`** (#197); `DatumInschrijving` bepaalt het schooljaar niet, een teldatum 1-2 is geen peildatum, en een inschrijving zonder teldatum telt niet (PvE §16: niet in aanmerking op 1-10 of 1-2) |
| `_hoofdinschrijving` | Precies één per deelnemer × instelling × schooljaar, **over leveringen heen**: hoogste niveau, dan laagste CREBO, dan meest recente `DatumBegin`, dan inschrijvingvolgnummer. Zonder bekend niveau nooit hoofdinschrijving |
| `_telling` | Gelijk aan `_hoofdinschrijving`: telt de deelnemer één keer per instelling per schooljaar |
| `_bekostigd` | `IndicatieBekostigbaar = J` van de periode die de peildatum dekt |
| `_gediplomeerd_in_jaar` | `DIP_DatumResultaat` valt in het schooljaar zelf (1-8-t t/m 31-7-(t+1)) |
| `_jr_noemer` / `_jr_teller` | Noemer = `_telling`; teller = noemer én gediplomeerd in het jaar |
| `_dr_noemer` / `_dr_teller` | Noemer = hoofdinschrijving, niveau ≥ 2, de persoon staat in `t+1` bij geen enkele instelling in de dataset ingeschreven (#118), **en** `t+1` is waarneembaar (1-10-(t+1) ligt vóór de laatste leveringspeildatum van de eigen instelling). Een overstap naar een instelling buiten de dataset telt als uitstroom (`quality.json` → `dr_scope`). Teller = noemer met een diploma op niveau ≥ 2 (via de opleidingscode van het diploma) bij de eigen instelling, behaald vanaf 1-8-(t-5) en vóór 1-10-(t+1); één uitkomst per rij, ook bij meerdere diploma's (#119) |

Invariant (getest op de star-output en bewaakt in `quality.json`): precies één `_hoofdinschrijving` per `BRIN × _persoon_id × Schooljaar`.

### Indicatoren in fact_inschrijving (verouderd)

!!! warning "Verouderd — verdwijnt in v4.0.0"
    Deze vlaggen staan op periode-grain: één Boolean voor een periode die meerdere schooljaren kan dekken. Ze missen
    tussenliggende schooljaren (#193) en gebruiken een verschoven diplomavenster (#194). Gebruik
    `fact_inschrijving_schooljaar`.

    **Besluit (#201):** `fact_inschrijving_schooljaar` is de enige bron voor jaargebonden vlaggen en indicatoren;
    `fact_inschrijving` blijft periode-grain. Migratiepad: de eerstvolgende release markeert de kolommen
    (`transform.VEROUDERDE_KOLOMMEN`, in `quality.json` → `star.verouderde_kolommen` en als info-melding) en de app
    leest ze niet meer; v4.0.0 verwijdert ze, samen met hun berekening in `transform.py`. Dat geldt ook voor de
    run-afhankelijke opbrengstjaar-kolommen (`Opbrengstjaar_*`, `_driejaars_teljaar`, `_num_opbrengstjaar_3jr`).

| Vlag | Definitie |
|---|---|
| `_actief_1_oktober` | De **ISP-periode** dekt 1 oktober van het studiejaar: `DatumBegin ≤ 1-10 ≤ _periode_einde`, met `_periode_einde` = vroegste van volgende `DatumBegin` − 1, `DatumEind` en `DatumUitschrijvingWerkelijk` (#163) |
| `_hoofdinschrijving` | Eén inschrijving per deelnemer × studiejaar bij deze instelling: hoogste niveau, dan laagste CREBO, dan meest recente periode |
| `_gediplomeerd_in_jaar` | Diploma behaald in het studiejaar |
| `_jr_noemer` / `_jr_teller` | Populatie en teller voor Jaarresultaat (JR) |
| `_dr_noemer` / `_dr_teller` | Populatie en teller voor Diplomaresultaat (DR) |
| `_entree_doorstroom` / `_entree_uitstroom` | Niveau-1 doorstroom- en uitstroomcategorieën op periode-grain (een student met meerdere perioden telt meermaals); in `fact_inschrijving_schooljaar` staan `_entree_noemer`/`_entree_doorstroom`/`_entree_uitstroom` op schooljaar-grain (#306) |
| `_hoogste_niveau` / `_laagste_CREBO` | Hoogste niveau (en daarbinnen laagste CREBO) per levering × BRIN × persoon **over de hele historiek**, niet per schooljaar |
| `_niveau_herkomst` | Waar `Niveau` vandaan komt: `bron`, `crebo` (`crebo.csv`), `sbb` (S-BB-koppeltabel), `sbb_nvt` (S-BB kent de code zonder niveau) of `onbekend`. Rijen zonder niveau vallen buiten JR/DR; Home meldt ze (`quality.controleer_niveau`). |

### Relatie met QlikView-referentiemodel

| QlikView | Deze ETL | Status |
|---|---|---|
| `Facttabel` | `fact_inschrijving` | Geïmplementeerd |
| `Studiesucces` JR | `_jr_noemer` / `_jr_teller` in `fact_inschrijving_schooljaar` | Geïmplementeerd |
| `Studiesucces` DR | `_dr_noemer` / `_dr_teller` in `fact_inschrijving_schooljaar` | Indicatief: zesjaarsvenster en diplomaniveau (#119), maar alleen diploma's en uitstroom binnen de leveringen in de dataset (#118) |
| `Studiesucces` SR | — | Vereist 6-jaar inschrijvingshistorie buiten eigen leveringen; buiten scope |
| `CREBOs` | `dim_opleiding` | Geïmplementeerd |
| `Deelnemers` | `dim_deelnemer` | Geïmplementeerd |
| `Organisatie` | — | Instellingsspecifiek (teams, kostenplaatsen); extensiepunt |
| `VSV startsets` | — | Vereist aparte DUO-levering; buiten scope |
