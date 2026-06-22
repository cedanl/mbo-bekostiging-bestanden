# ISG – Inschrijving

Het ISG-record bevat de inschrijvingsgegevens van een student bij een instelling. Per inschrijving is er één ISG-record; een student kan meerdere inschrijvingen hebben.

## RO-variant

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `ISG` |
| 2 | Burgerservicenummer | Nee* | AN9 | BSN van de student |
| 3 | Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN |
| 4 | Inschrijvingvolgnummer | Ja | AN1..20 | Door instelling toegekend volgnummer |
| 5 | Datum inschrijving | Ja | D `ccyy-mm-dd` | Eerste dag inschrijving (inclusief) |
| 6 | Datum uitschrijving gepland | Ja | D `ccyy-mm-dd` | Geplande laatste dag (inclusief) |
| 7 | Datum uitschrijving werkelijk | Nee | D `ccyy-mm-dd` | Werkelijke laatste dag (inclusief) |
| 8 | Reden uitschrijving | Nee | AN2 | Code voor reden uitschrijving; zie [Waardenlijsten](../waardenlijsten.md) |

*Ofwel BSN ofwel ONR is gevuld.

**Voorbeeld:**
```
ISG|BSN1||C3|2023-01-30|2025-01-29|2025-01-16|08
```

## GRONDSLAG IP-variant

In de GRONDSLAG heeft ISG een extra BRIN-veld (de instelling waarvoor de inschrijving geldt) en datumaantallen in compact formaat.

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `ISG` |
| 2 | PGN | Ja | N9 | Pseudonummer van de student |
| 3 | BRIN | Ja | AN4 | Instelling van inschrijving |
| 4 | Inschrijvingsvolgnummer | Ja | AN1..20 | Door instelling toegekend volgnummer |
| 5 | Datum inschrijving | Ja | D `ccyymmdd` | Eerste dag inschrijving |
| 6 | Datum uitschrijving gepland | Ja | D `ccyymmdd` | Geplande laatste dag |
| 7 | Datum uitschrijving werkelijk | Nee | D `ccyymmdd` | Werkelijke laatste dag |
| 8 | Reden uitschrijving | Nee | AN2..70 | Code voor reden uitschrijving |

**Voorbeeld:**
```
ISG;BSN1;27DV;C3;20230130;20250129;20250116;08
```

## Reden uitschrijving

Zie [Waardenlijsten → Reden uitschrijving](../waardenlijsten.md#reden-uitschrijving).
