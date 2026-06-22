# GEO – Generiek examenonderdeel

Het GEO-record bevat de resultaten voor een **generiek examenonderdeel** (taal of rekenen). Dit kan horen bij een diploma of als los onderdeel aanwezig zijn.

## RO-variant

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `GEO` |
| 2 | Burgerservicenummer | Nee* | AN9 | BSN van de student |
| 3 | Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN |
| 4 | Resultaatvolgnummer diploma | Nee | AN1..20 | Koppeling naar DIP; alleen bij diploma-GEO |
| 5 | Opleidingcode diploma | Nee | AN5 | Opleiding van het diploma; alleen bij diploma-GEO |
| 6 | Resultaatvolgnummer | Ja | AN1..20 | Eigen volgnummer van dit GEO-record |
| 7 | Code generiek examenonderdeel | Ja | AN4 | Unieke identificatie van het onderdeel |
| 8 | Datum resultaat | Nee | D `ccyy-mm-dd` | Alleen bij los GEO-onderdeel |
| 9 | Eindcijfer | Nee | N1..2 | Behaald eindcijfer |
| 10 | Vrijstelling generiek examenonderdeel | Nee | AN1..4 | Vrijstellingsgrond voor het gehele onderdeel |
| 11 | Cijfer IE | Nee | N2..3 | Cijfer institutioneel examen |
| 12 | Vrijstelling IE | Nee | AN3 | Vrijstellingsgrond voor IE |
| 13 | Cijfer CE | Nee | N2..3 | Cijfer centraal examen |
| 14 | Vrijstelling CE | Nee | AN3 | Vrijstellingsgrond voor CE |
| 15 | Inschrijvingvolgnummer | Nee | AN1..20 | Alleen bij los GEO-onderdeel |
| 16 | Onderwijsaanbieder | Nee | AN7 | RIO-code `nnnAnnn` |

*Ofwel BSN ofwel ONR is gevuld.

**Voorbeeld (GEO bij diploma):**
```
GEO|BSN1||8286771|25655|8286774|3005||6|MBO|74|MBO|51|MBO||
```

## GRONDSLAG IP-variant

In de GRONDSLAG ontbreekt het veld `Opleidingcode diploma`.

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `GEO` |
| 2 | PGN | Ja | N9 | Pseudonummer van de student |
| 3 | BRIN | Ja | AN4 | Instelling |
| 4 | Resultaatvolgnummer diploma | Nee | AN1..20 | Koppeling naar DIP; leeg bij los GEO |
| 5 | Resultaatvolgnummer | Ja | AN1..20 | Eigen volgnummer |
| 6 | Code generiek examenonderdeel | Ja | AN5 | Unieke identificatie |
| 7 | Eindcijfer | Nee | N2 | Behaald eindcijfer |
| 8 | Vrijstelling generiek examenonderdeel | Nee | AN70 | Vrijstellingsgrond |
| 9 | Cijfer IE | Nee | AN3 | Cijfer institutioneel examen |
| 10 | Vrijstelling IE | Nee | AN70 | Vrijstellingsgrond IE |
| 11 | Cijfer CE | Nee | AN3 | Cijfer centraal examen |
| 12 | Vrijstelling CE | Nee | AN70 | Vrijstellingsgrond CE |
| 13 | Datum resultaat | Nee | D `ccyymmdd` | Alleen bij los onderdeel |
| 14 | Inschrijvingvolgnummer | Nee | AN1..20 | Alleen bij los onderdeel |
| 15 | Onderwijsaanbieder | Nee | AN7 | RIO-code `nnnAnnn` |

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
