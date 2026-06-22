# AMO – AMvB-onderdeel

Het AMO-record bevat een **AMvB-onderdeel** (Algemene Maatregel van Bestuur examenonderdeel). Dit kan horen bij een diploma (`DIP`) of als **los onderdeel** (bijv. een certificaat) aanwezig zijn.

## RO-variant

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `AMO` |
| 2 | Burgerservicenummer | Nee* | AN9 | BSN van de student |
| 3 | Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN |
| 4 | Resultaatvolgnummer diploma | Nee | AN1..20 | Koppeling naar DIP; alleen gevuld als AMO bij diploma hoort |
| 5 | Opleidingcode diploma | Nee | AN5 | Opleiding van het diploma; alleen gevuld als AMO bij diploma hoort |
| 6 | Resultaatvolgnummer | Ja | AN1..20 | Eigen volgnummer van dit AMO-record |
| 7 | Code AMvB onderdeel | Ja | AN5 | Unieke identificatie van het AMvB-onderdeel |
| 8 | Datum resultaat | Nee | D `ccyy-mm-dd` | Alleen gevuld bij los AMvB-onderdeel |
| 9 | Certificaat | Nee | AN1 | `J` = certificaat uitgereikt; alleen bij los onderdeel |
| 10 | Inschrijvingvolgnummer | Nee | AN1..20 | Koppeling naar ISG; alleen bij los onderdeel |
| 11 | Onderwijsaanbieder | Nee | AN7 | RIO-code `nnnAnnn` |

*Ofwel BSN ofwel ONR is gevuld.

## GRONDSLAG IP-variant

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `AMO` |
| 2 | PGN | Ja | N9 | Pseudonummer van de student |
| 3 | BRIN | Ja | AN4 | Instelling |
| 4 | Resultaatvolgnummer diploma | Nee | AN1..20 | Koppeling naar DIP; leeg bij los AMO |
| 5 | Resultaatvolgnummer | Ja | AN1..20 | Eigen volgnummer |
| 6 | Code AMvB onderdeel | Ja | AN5 | Unieke identificatie |
| 7 | Certificaat | Nee | N1 | `1` = certificaat; `0` = geen certificaat; alleen bij los onderdeel |
| 8 | Datum resultaat | Nee | D `ccyymmdd` | Alleen bij los onderdeel |
| 9 | Inschrijvingvolgnummer | Nee | AN1..20 | Alleen bij los onderdeel |
| 10 | Onderwijsaanbieder | Nee | AN7 | RIO-code `nnnAnnn` |

## Verschil los vs. bij diploma

| Veld | Bij diploma | Los onderdeel |
|---|---|---|
| Resultaatvolgnummer diploma | Gevuld | Leeg |
| Opleidingcode diploma (RO) | Gevuld | Leeg |
| Datum resultaat | Leeg | Gevuld |
| Certificaat | Leeg | Altijd `J` (RO) / `1` (GRONDSLAG) |
| Inschrijvingvolgnummer | Leeg | Optioneel gevuld |
