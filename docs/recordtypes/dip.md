# DIP – Diploma

Het DIP-record bevat de gegevens van een behaald diploma. Een student kan meerdere diploma's hebben.

## RO-variant

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `DIP` |
| 2 | Burgerservicenummer | Nee* | AN9 | BSN van de student |
| 3 | Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN |
| 4 | Resultaatvolgnummer | Ja | AN1..20 | Door instelling toegekend volgnummer voor het diploma |
| 5 | Opleidingcode | Ja | AN5 | CREBO-code van de opleiding |
| 6 | Datum resultaat | Ja | D `ccyy-mm-dd` | Datum waarop het diploma behaald is |
| 7 | *(leeg in demo-data)* | — | — | Extra veld dat in sommige bestanden voorkomt |
| 8 | Indicatie bekostigbaar | Ja | AN1 | `J` = bekostigbaar, `N` = niet |
| 9 | Inschrijvingvolgnummer | Nee | AN1..20 | Koppeling naar de bijbehorende inschrijving |
| 10 | Onderwijsaanbieder | Nee | AN7 | RIO-code `nnnAnnn` |

*Ofwel BSN ofwel ONR is gevuld.

**Voorbeeld:**
```
DIP|BSN1||8286771|25655|2025-01-16||J|C3|100A501
```

## GRONDSLAG IP-variant

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `DIP` |
| 2 | PGN | Ja | N9 | Pseudonummer van de student |
| 3 | BRIN | Ja | AN4 | Instelling waar diploma behaald |
| 4 | Resultaatvolgnummer | Ja | AN1..20 | Door instelling toegekend volgnummer |
| 5 | Opleidingcode | Ja | AN5 | CREBO-code |
| 6 | Datum resultaat | Ja | D `ccyymmdd` | Datum diploma behaald |
| 7 | Indicatie bekostigbaar | Nee | B | `1` = bekostigbaar, `0` = niet |
| 8 | Inschrijvingvolgnummer | Nee | AN1..20 | Koppeling naar bijbehorende inschrijving |
| 9 | Onderwijsaanbieder | Nee | AN7 | RIO-code `nnnAnnn` |

**Voorbeeld:**
```
DIP;BSN1;27DV;8286771;25655;20250116;1;C3;100A501
```
