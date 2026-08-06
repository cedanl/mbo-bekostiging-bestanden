# GEO – Generiek examenonderdeel

Het GEO-record bevat de resultaten voor een **generiek examenonderdeel** (taal of rekenen). Dit kan horen bij een diploma of als los onderdeel aanwezig zijn.

## RO-variant

| Pos | Veld | Verplicht | Formaat | Definitie | Voorbeeldwaarde |
|---|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `GEO` | `GEO` |
| 2 | Burgerservicenummer | Nee* | AN9 | BSN van de student | — |
| 3 | Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN | — |
| 4 | Resultaatvolgnummer diploma | Nee | AN1..20 | Koppeling naar DIP; alleen bij diploma-GEO | `8286771` |
| 5 | Opleidingcode diploma | Nee | AN5 | Opleiding van het diploma; alleen bij diploma-GEO | `25655` |
| 6 | Resultaatvolgnummer | Ja | AN1..20 | Eigen volgnummer van dit GEO-record | `8286774` |
| 7 | Code generiek examenonderdeel | Ja | AN4 | Unieke identificatie van het onderdeel | `3005` |
| 8 | Datum resultaat | Nee | D `ccyy-mm-dd` | Alleen bij los GEO-onderdeel | `4-10-2023` |
| 9 | Eindcijfer | Nee | N1..2 | Behaald eindcijfer | `6` |
| 10 | Vrijstelling generiek examenonderdeel | Nee | AN1..4 | Vrijstellingsgrond voor het gehele onderdeel | `MBO` |
| 11 | Cijfer IE | Nee | N2..3 | Cijfer institutioneel examen | `74` |
| 12 | Vrijstelling IE | Nee | AN3 | Vrijstellingsgrond voor IE | `MBO` |
| 13 | Cijfer CE | Nee | N2..3 | Cijfer centraal examen | `51` |
| 14 | Vrijstelling CE | Nee | AN3 | Vrijstellingsgrond voor CE | `MBO` |
| 15 | Inschrijvingvolgnummer | Nee | AN1..20 | Alleen bij los GEO-onderdeel | `2` |
| 16 | Onderwijsaanbieder | Nee | AN7 | RIO-code `nnnAnnn` | `101A741` |

*Ofwel BSN ofwel ONR is gevuld.

**Voorbeeld (GEO bij diploma):**
```
GEO|BSN1||8286771|25655|8286774|3005||6|MBO|74|MBO|51|MBO||
```

## GRONDSLAG IP-variant

In de GRONDSLAG ontbreekt het veld `Opleidingcode diploma`.

| Pos | Veld | Verplicht | Formaat | Definitie | Voorbeeldwaarde |
|---|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `GEO` | `GEO` |
| 2 | PGN | Ja | N9 | Pseudonummer van de student | — |
| 3 | BRIN | Ja | AN4 | Instelling | `27DV` |
| 4 | Resultaatvolgnummer diploma | Nee | AN1..20 | Koppeling naar DIP; leeg bij los GEO | `8286771` |
| 5 | Resultaatvolgnummer | Ja | AN1..20 | Eigen volgnummer | `8286774` |
| 6 | Code generiek examenonderdeel | Ja | AN5 | Unieke identificatie | `3005` |
| 7 | Eindcijfer | Nee | N2 | Behaald eindcijfer | `6` |
| 8 | Vrijstelling generiek examenonderdeel | Nee | AN70 | Vrijstellingsgrond | `MBO` |
| 9 | Cijfer IE | Nee | AN3 | Cijfer institutioneel examen | `74` |
| 10 | Vrijstelling IE | Nee | AN70 | Vrijstellingsgrond IE | `MBO` |
| 11 | Cijfer CE | Nee | AN3 | Cijfer centraal examen | `51` |
| 12 | Vrijstelling CE | Nee | AN70 | Vrijstellingsgrond CE | `MBO` |
| 13 | Datum resultaat | Nee | D `ccyymmdd` | Alleen bij los onderdeel | `20250304` |
| 14 | Inschrijvingvolgnummer | Nee | AN1..20 | Alleen bij los onderdeel | `C3` |
| 15 | Onderwijsaanbieder | Nee | AN7 | RIO-code `nnnAnnn` | `100A500` |

**Voorbeeld (GEO bij diploma):**
```
GEO;BSN1;27DV;8286771;8286774;3005;6;MBO;74;MBO;51;MBO;;;
```

**Voorbeeld (los GEO):**
```
GEO;BSN3;27DV;;8503110;3005;6;;66;;45;;20250304;C3;100A500
```

## Code generiek examenonderdeel

| Code | Onderdeel |
|---|---|
| `3005` | Nederlandse taal (lezen) |
| `3006` | Nederlandse taal (schrijven) |
| `3010` | Rekenen |
| `3013` | Keuzedelen-landelijk (KZDL) |

*(niet uitputtend; codes zijn gebaseerd op CREBO-examenstructuur)*
