# BII – Bekostigingsinformatie Inschrijving

Het BII-record bevat de **bekostigingsinformatie voor een inschrijving op een specifieke teldatum**. Dit record is uniek voor de GRONDSLAG IP MBO en komt niet voor in het RO.

BII-records volgen direct na het ISG-block (na ISP, ISE en BPV-records) van de betreffende inschrijving. Per inschrijving kunnen er meerdere BII-records zijn (één per teldatum).

!!! info "Twee teldata"
    DUO telt inschrijvingen op twee momenten per studiejaar:
    - **1 oktober** (teldatum 1-10) – hoofdtelling
    - **1 februari** (teldatum 1-2) – controletelling voor de correctiefactor

## Velden (GRONDSLAG IP)

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `BII` |
| 2 | PGN | Ja | N9 | Pseudonummer van de student |
| 3 | BRIN | Ja | AN4 | Instelling van inschrijving |
| 4 | Inschrijvingsvolgnummer | Ja | AN1..20 | Koppeling naar het ISG-record |
| 5 | Teldatum | Ja | D `ccyymmdd` | Meetmoment (1-10 of 1-2 van het studiejaar) |
| 6 | DatumTijd bepaling bekostigingsgrondslagen | Ja | DT15 | Tijdstip waarop DUO de grondslagen heeft berekend |
| 7 | Status bepaling bekostigingsstatus | Ja | AN1 | `V` = Voorlopig, `D` = Definitief |
| 8 | Bekostigingsstatus | Nee | AN1 | `J` = bekostigd door DUO, `N` = niet |
| 9 | Inschrijving voor correctiefactor | Ja | AN1 | `J` / `N` – telt mee voor de correctiefactor 1-10/1-2 |
| 10 | BBL BOL factor | Nee | N5 (2 dec.) | Vermenigvuldigingsfactor voor leertraject |
| 11 | Prijsfactor MBO | Nee | N5 (2 dec.) | Vermenigvuldigingsfactor voor de opleiding |
| 12 | Aantal bekostigde verblijfsjaren MBO | Nee | N2 | Niet meer van toepassing na 01-10-2018 |
| 13 | Verblijfsjaarfactor | Nee | N10 (2 dec.) | Niet meer van toepassing na 01-10-2018 |
| 14 | Bijdrage inschrijving aan deelnemerswaarde | Nee | N15 (6 dec.) | Individuele bijdrage aan de deelnemerswaarde |

## Factoren uitgelegd

| Factor | Waarde | Uitleg |
|---|---|---|
| BBL BOL factor | BBL < BOL | BBL-studenten wegen lichter mee dan BOL-studenten |
| Prijsfactor MBO | 1.0 – 1.5+ | Per opleiding vastgesteld; hogere prijs voor duurdere opleidingen |
| Deelnemerswaarde | Bijdrage | Product van BBL/BOL-factor × prijsfactor (× verblijfsjaarfactor pre-2018) |

## Bekostigingsstatus vs. IndicatieBekostigbaar

| Veld | Wie vult in | Betekenis |
|---|---|---|
| Indicatie bekostigbaar (ISP) | Instelling | Instelling vraagt bekostiging aan voor deze inschrijving |
| Bekostigingsstatus (BII) | DUO | DUO heeft bekostiging toegekend op deze teldatum |
