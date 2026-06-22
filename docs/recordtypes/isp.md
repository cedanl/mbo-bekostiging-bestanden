# ISP – Inschrijvingsperiode

Het ISP-record beschrijft een **periode** binnen een inschrijving, met de opleidingsgegevens die in die periode gelden. Een inschrijving kan meerdere ISP-records hebben (bijv. bij opleiding- of niveauwijziging).

## RO-variant

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `ISP` |
| 2 | Burgerservicenummer | Nee* | AN9 | BSN van de student |
| 3 | Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN |
| 4 | Inschrijvingvolgnummer | Ja | AN1..20 | Koppeling naar het ISG-record |
| 5 | Datum begin | Ja | D `ccyy-mm-dd` | Begindatum van de periode (inclusief) |
| 6 | Opleidingcode | Ja | AN5 | 5-cijferige CREBO-code |
| 7 | Leertraject | Ja | AN2..6 | Zie [Waardenlijsten](../waardenlijsten.md#leertraject) |
| 8 | Niveau | Nee | AN5 | Zie [Waardenlijsten](../waardenlijsten.md#niveau) |
| 9 | Indicatie bekostigbaar | Ja | AN1 | `J` = bekostigbaar, `N` = niet |
| 10 | Locatiecode VSV | Nee | AN12 | NHR-vestigingsnummer van de onderwijslocatie |
| 11 | Onderwijsaanbieder | Nee | AN7 | RIO-code, formaat `nnnAnnn` |
| 12 | Onderwijslocatie | Nee | AN7 | RIO-code, formaat `nnnXnnn` |
| 13 | Leerroute | Nee | AN3 | Zie [Waardenlijsten](../waardenlijsten.md#leerroute) |
| 14 | Leerroutefase | Nee | AN2..3 | Zie [Waardenlijsten](../waardenlijsten.md#leerroutefase) |

*Ofwel BSN ofwel ONR is gevuld.

**Voorbeeld:**
```
ISP|BSN1||C3|2023-01-30|25655|BBL||J||100A501|101X591||
```

## GRONDSLAG IP-variant

In de GRONDSLAG heeft ISP een extra BRIN-veld én een Datum eind veld.

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `ISP` |
| 2 | PGN | Ja | N9 | Pseudonummer van de student |
| 3 | BRIN | Ja | AN4 | Instelling van inschrijving |
| 4 | Inschrijvingsvolgnummer | Ja | AN1..20 | Koppeling naar het ISG-record |
| 5 | Datum begin | Ja | D `ccyymmdd` | Begindatum van de periode |
| 6 | Datum eind | Nee | D `ccyymmdd` | Einddatum van de periode |
| 7 | Opleidingcode | Ja | AN5 | 5-cijferige CREBO-code |
| 8 | Niveau | Nee | AN5 | Zie [Waardenlijsten](../waardenlijsten.md#niveau) |
| 9 | Leertraject | Ja | AN6 | Zie [Waardenlijsten](../waardenlijsten.md#leertraject) |
| 10 | Locatiecode VSV | Nee | AN12 | NHR-vestigingsnummer |
| 11 | Indicatie bekostigbaar | Ja | B | `1` = bekostigbaar, `0` = niet |
| 12 | Onderwijsaanbieder | Nee | AN7 | RIO-code `nnnAnnn` |
| 13 | Onderwijslocatie | Nee | AN7 | RIO-code `nnnXnnn` |
| 14 | Leerroute | Nee | AN3 | Zie [Waardenlijsten](../waardenlijsten.md#leerroute) |
| 15 | Leerroutefase | Nee | AN3 | Zie [Waardenlijsten](../waardenlijsten.md#leerroutefase) |

**Voorbeeld:**
```
ISP;BSN1;27DV;C3;20230130;20250116;25655;;BBL;;1;100A501;101X591;;
```
