# BPV – Beroepspraktijkvorming

Het BPV-record bevat een **praktijkovereenkomst** (POK) van een BBL-student bij een erkend leerbedrijf. Een inschrijving kan meerdere BPV-records hebben.

## RO-variant

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `BPV` |
| 2 | Burgerservicenummer | Nee* | AN9 | BSN van de student |
| 3 | Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN |
| 4 | Inschrijvingvolgnummer | Ja | AN1..20 | Koppeling naar het ISG-record |
| 5 | Volgnummer | Ja | AN1..20 | Door instelling toegekend volgnummer voor de POK |
| 6 | Afsluitdatum | Ja | D `ccyy-mm-dd` | Datum waarop de POK is opgesteld |
| 7 | Datum begin | Ja | D `ccyy-mm-dd` | Startdatum BPV |
| 8 | Datum einde gepland | Ja | D `ccyy-mm-dd` | Geplande einddatum BPV |
| 9 | Datum einde werkelijk | Nee | D `ccyy-mm-dd` | Werkelijke einddatum BPV |
| 10 | Omvang | Nee | N1..4 | Totaal aantal uren BPV |
| 11 | LeerbedrijfID | Ja | N9 | SBB-nummer van het leerbedrijf (100000000–999999999) |
| 12 | Opleidingcode | Nee | AN5 | CREBO-code van de BPV-opleiding |
| 13 | Code keuzedeel | Nee | AN5 | Keuzedeel-code als BPV bij keuzedeel hoort |

*Ofwel BSN ofwel ONR is gevuld.

**Voorbeeld:**
```
BPV|BSN1||C3|C1|2023-01-07|2023-02-01|2025-01-29|2024-08-30|2163|100018965|25655|
```

## GRONDSLAG IP-variant

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `BPV` |
| 2 | PGN | Ja | N9 | Pseudonummer van de student |
| 3 | BRIN | Ja | AN4 | Instelling van inschrijving |
| 4 | Inschrijvingsvolgnummer | Ja | AN1..20 | Koppeling naar het ISG-record |
| 5 | Volgnummer | Ja | AN1..20 | Door instelling toegekend volgnummer voor de POK |
| 6 | Afsluitdatum | Ja | D `ccyymmdd` | Datum waarop de POK is opgesteld |
| 7 | Datum begin | Ja | D `ccyymmdd` | Startdatum BPV |
| 8 | Datum einde gepland | Ja | D `ccyymmdd` | Geplande einddatum BPV |
| 9 | Datum einde werkelijk | Nee | D `ccyymmdd` | Werkelijke einddatum BPV |
| 10 | Omvang | Ja | N10 | Totaal aantal uren BPV |
| 11 | LeerbedrijfID | Ja | N10 | SBB-nummer van het leerbedrijf |
| 12 | Opleidingcode | Nee | AN5 | CREBO-code van de BPV-opleiding |
| 13 | Code keuzedeel | Nee | AN5 | Keuzedeel-code |

**Voorbeeld:**
```
BPV;BSN1;27DV;C3;C1;20230107;20230201;20250129;20240830;2163;100018965;25655;
```

## Toelichting afsluitdatum

De afsluitdatum is de datum waarop de praktijkovereenkomst is **opgesteld**, niet noodzakelijkerwijs de datum waarop alle handtekeningen gezet zijn.
