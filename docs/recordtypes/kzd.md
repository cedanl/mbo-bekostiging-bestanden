# KZD – Keuzedeel

Het KZD-record bevat het resultaat van een **keuzedeel**. Dit kan horen bij een diploma of als los onderdeel aanwezig zijn.

## RO-variant

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `KZD` |
| 2 | Burgerservicenummer | Nee* | AN9 | BSN van de student |
| 3 | Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN |
| 4 | Resultaatvolgnummer diploma | Nee | AN1..20 | Koppeling naar DIP; alleen bij diploma-KZD |
| 5 | Opleidingcode diploma | Nee | AN5 | Opleiding van het diploma; alleen bij diploma-KZD |
| 6 | Resultaatvolgnummer | Ja | AN1..20 | Eigen volgnummer van dit KZD-record |
| 7 | Code keuzedeel | Ja | AN5 | Unieke identificatie van het keuzedeel |
| 8 | Datum resultaat | Nee | D `ccyy-mm-dd` | Alleen bij los keuzedeel |
| 9 | Resultaat | Ja | AN1..12 | `Behaald` of `Niet behaald` |
| 10 | Certificaat | Nee | AN1 | `J` = certificaat, `N` = niet; alleen bij los keuzedeel |
| 11 | Inschrijvingvolgnummer | Nee | AN1..20 | Alleen bij los keuzedeel |
| 12 | Onderwijsaanbieder | Nee | AN7 | RIO-code `nnnAnnn` |

*Ofwel BSN ofwel ONR is gevuld.

**Voorbeeld (KZD bij diploma):**
```
KZD|BSN1||8286771|25655|8286772|K0067||Behaald|||
```

## GRONDSLAG IP-variant

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `KZD` |
| 2 | PGN | Ja | N9 | Pseudonummer van de student |
| 3 | BRIN | Ja | AN4 | Instelling |
| 4 | Resultaatvolgnummer diploma | Nee | AN1..20 | Koppeling naar DIP; leeg bij los KZD |
| 5 | Resultaatvolgnummer | Ja | AN1..20 | Eigen volgnummer |
| 6 | Code keuzedeel | Ja | AN5 | Unieke identificatie |
| 7 | Resultaat | Nee | AN70 | `BEHAALD` of `NIET BEHAALD` |
| 8 | Certificaat | Ja | AN1 | `1` = certificaat, `0` = niet; alleen bij los KZD |
| 9 | Datum resultaat | Nee | D `ccyymmdd` | Alleen bij los keuzedeel |
| 10 | Inschrijvingvolgnummer | Nee | AN1..20 | Alleen bij los keuzedeel |
| 11 | Onderwijsaanbieder | Nee | AN7 | RIO-code `nnnAnnn` |

**Voorbeeld:**
```
KZD;BSN1;27DV;8286771;8286772;K0067;BEHAALD;;;;
```

## Resultaat waardenlijst

| Waarde (RO) | Waarde (GRONDSLAG) | Betekenis |
|---|---|---|
| `Behaald` | `BEHAALD` | Keuzedeel succesvol afgerond |
| `Niet behaald` | `NIET BEHAALD` | Keuzedeel niet gehaald |
