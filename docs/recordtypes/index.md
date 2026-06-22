# Recordtypes

Alle CSV-bestanden (RO en GRONDSLAG IP MBO) zijn opgebouwd uit records zonder kolomkoppen. Het eerste veld van elke regel is altijd de **recordtype-code**.

## Overzicht

| Code | Naam | RO | GRONDSLAG | Beschrijving |
|---|---|---|---|---|
| `VLP` | Voorlooprecord | ✓ | ✓ | Eerste record; bestandskop |
| `PER` | Persoonsgegevens | ✓ | ✓ | BSN/ONR (RO) of PGN + leeftijden (GRONDSLAG) |
| `ISG` | Inschrijving | ✓ | ✓ | Inschrijvingsdatum, uitschrijvingsdatum, reden |
| `ISP` | Inschrijvingsperiode | ✓ | ✓ | Opleiding, leertraject, niveau per periode |
| `ISE` | Extra ondersteuning | ✓ | ✓ | Periodes extra ondersteuning |
| `BPV` | BPV | ✓ | ✓ | Beroepspraktijkvormingsovereenkomst |
| `BII` | Bekostigingsinformatie inschrijving | | ✓ | Teldatum, factoren, deelnemerswaarde |
| `DIP` | Diploma | ✓ | ✓ | Opleiding, behaaldatum, bekostigbaarheidsindicatie |
| `BID` | Bekostigingsinformatie diploma | | ✓ | Niveau, factoren, diplomawaarde |
| `AMO` | AMvB-onderdeel | ✓ | ✓ | Examenonderdeel bij diploma of los |
| `GEO` | Generiek examenonderdeel | ✓ | ✓ | Taal- en rekenresultaten |
| `KZD` | Keuzedeel | ✓ | ✓ | Keuzedeelresultaten |
| `SLR` | Sluitrecord | ✓ | ✓ | Laatste record; tellingen per recordtype |

## Veldnotatie

In de spec worden veldformaten aangegeven als:

| Notatie | Betekenis |
|---|---|
| `AN5..5` | Alfanumeriek, exact 5 tekens |
| `AN1..20` | Alfanumeriek, 1 t/m 20 tekens |
| `N12` | Numeriek, maximaal 12 cijfers |
| `D` (ccyy-mm-dd) | Datum, ISO-formaat |
| `Boolean` | `true` / `false` (XML) of `J`/`N` of `1`/`0` (CSV) |

## Veldvolgorde

In de CSV-bestanden bepaalt de **positie** de betekenis — er zijn geen kolomnamen. Lege optionele velden worden als lege string geleverd (`;;`).

## Consistente velden

De volgende velden komen in bijna elk recordtype voor en hebben altijd dezelfde betekenis:

| Veld | Betekenis |
|---|---|
| Recordsoort | Altijd het eerste veld; geeft het recordtype aan |
| Burgerservicenummer (BSN) | 9-cijferig, voldoet aan de elfproef; leeg als ONR gebruikt wordt |
| Onderwijsnummer (ONR) | 9-cijferig alternatief voor BSN; leeg als BSN gebruikt wordt |
| PGN | Pseudonummer in GRONDSLAG; vervangt BSN voor privacy |
| BRIN | 2 cijfers + 2 hoofdletters; unieke instelling-identificatie |
| Inschrijvingvolgnummer | Door instelling toegekend volgnummer voor de inschrijving |
| Resultaatvolgnummer | Door instelling toegekend volgnummer voor het resultaat |
| Opleidingcode | 5-cijferige CREBO-code |
