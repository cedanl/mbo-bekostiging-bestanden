# VLP – Voorlooprecord

Het VLP-record is altijd het **eerste record** in het bestand. Het bevat bestandsidentificatie-gegevens.

## RO-variant

**Positievolgorde:**

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `VLP` |
| 2 | BRIN | Ja | AN4 | Unieke instelling-code (2 cijfers + 2 hoofdletters) |
| 3 | Datum begin periode | Ja | D `ccyy-mm-dd` | Begindatum van de selectieperiode |
| 4 | Datum einde periode | Ja | D `ccyy-mm-dd` | Einddatum (inclusief) van de selectieperiode |
| 5 | Datum aanmaak | Ja | D `ccyy-mm-dd` | Datum waarop het bestand is aangemaakt |

**Voorbeeld:**
```
VLP|27DV|2024-07-31|2026-03-24|2026-03-25
```

## GRONDSLAG IP-variant

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `VLP` |
| 2 | BRIN | Ja | AN4 | Unieke instelling-code |
| 3 | Studiejaar | Ja | N4 | Het studiejaar waarop de levering betrekking heeft |
| 4 | Aanmaakdatum | Ja | D `ccyymmdd` | Datum waarop de levering is aangemaakt |
| 5 | Bekostiging | Ja | AN1 | `V` = voorlopig, `D` = definitief |

**Voorbeeld:**
```
VLP;27DV;2025;20251119;V
```
