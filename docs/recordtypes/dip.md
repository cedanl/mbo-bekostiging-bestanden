# DIP – Diploma

Het DIP-record bevat de gegevens van een behaald diploma. Een student kan meerdere diploma's hebben.

## RO-variant

Er bestaan twee layouts; de ingest herkent ze per regel (positie 7 leeg en een
indicatie bekostigbaar op 8, of die indicatie direct op 7) en legt de keuze vast
in `quality.json` → `layoutvarianten` (#321). Een regel die op geen van beide
past, breekt de ingest.

**Praktijk** (alle bekende leveringen, demo):

| Pos | Veld | Verplicht | Formaat | Definitie | Voorbeeldwaarde |
|---|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `DIP` | `DIP` |
| 2 | Burgerservicenummer | Nee* | AN9 | BSN van de student | — |
| 3 | Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN | — |
| 4 | Resultaatvolgnummer | Ja | AN1..20 | Door instelling toegekend volgnummer voor het diploma | `8286771` |
| 5 | Opleidingcode | Ja | AN5 | CREBO-code van de opleiding | `25655` |
| 6 | Datum resultaat | Ja | D `ccyy-mm-dd` | Datum waarop het diploma behaald is | `2025-01-16` |
| 7 | *(niet in spec)* | — | — | Staat niet in het PvE (4.8.2 en 4.8.3) maar is aanwezig in alle bekende leveringen; altijd leeg; een gevulde waarde past op geen layout | — |
| 8 | Indicatie bekostigbaar | Ja | AN1 | `J` = bekostigbaar, `N` = niet | `J` |
| 9 | Inschrijvingvolgnummer | Nee | AN1..20 | Koppeling naar de bijbehorende inschrijving | `C3` |
| 10 | Onderwijsaanbieder | Nee | AN7 | RIO-code `nnnAnnn` | `100A501` |

*Ofwel BSN ofwel ONR is gevuld.

**Voorbeeld:**
```
DIP|BSN1||8286771|25655|2025-01-16||J|C3|100A501
```

**Officieel** (PvE §15.5.7): negen velden, zonder positie 7; `Indicatie
bekostigbaar` staat op 7, `Inschrijvingvolgnummer` op 8 en `Onderwijsaanbieder`
op 9. In de uitvoer blijft de kolom `_onbekend` leeg.

```
DIP|BSN1||8286771|25655|2025-01-16|J|C3|100A501
```

## GRONDSLAG IP-variant

| Pos | Veld | Verplicht | Formaat | Definitie | Voorbeeldwaarde |
|---|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `DIP` | `DIP` |
| 2 | PGN | Ja | N9 | Pseudonummer van de student | — |
| 3 | BRIN | Ja | AN4 | Instelling waar diploma behaald | `27DV` |
| 4 | Resultaatvolgnummer | Ja | AN1..20 | Door instelling toegekend volgnummer | `8286771` |
| 5 | Opleidingcode | Ja | AN5 | CREBO-code | `25655` |
| 6 | Datum resultaat | Ja | D `ccyymmdd` | Datum diploma behaald | `20250116` |
| 7 | Indicatie bekostigbaar | Nee | B | `1` = bekostigbaar, `0` = niet | `1` |
| 8 | Inschrijvingvolgnummer | Nee | AN1..20 | Koppeling naar bijbehorende inschrijving | `C3` |
| 9 | Onderwijsaanbieder | Nee | AN7 | RIO-code `nnnAnnn` | `100A501` |

**Voorbeeld:**
```
DIP;BSN1;27DV;8286771;25655;20250116;1;C3;100A501
```
