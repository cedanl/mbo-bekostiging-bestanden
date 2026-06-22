# BID – Bekostigingsinformatie Diploma

Het BID-record bevat de **bekostigingsinformatie voor een diploma**. Dit record is uniek voor de GRONDSLAG IP MBO en komt niet voor in het RO.

BID-records volgen direct na het bijbehorende DIP-block (na AMO-, GEO- en KZD-records). Per diploma is er maximaal één BID-record.

## Velden (GRONDSLAG IP)

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `BID` |
| 2 | PGN | Ja | N9 | Pseudonummer van de student |
| 3 | BRIN | Ja | AN4 | Instelling waar diploma behaald |
| 4 | Resultaatvolgnummer | Ja | AN1..20 | Koppeling naar het DIP-record |
| 5 | Niveau | Nee | AN5 | Niveau van het diploma; zie [Waardenlijsten](../waardenlijsten.md#niveau) |
| 6 | Indicatie specialistendiploma | Nee | AN1 | `J` = specialistendiploma, `N` = niet |
| 7 | Niveau hoogst bekostigde diploma | Nee | AN5 | Hoogste al eerder bekostigde diplomaniveau; zie [Waardenlijsten](../waardenlijsten.md#niveau) |
| 8 | Indicatie hoogst bekostigde diploma is specialist | Nee | AN1 | `J` / `N` |
| 9 | DatumTijd bepaling bekostigingsgrondslagen | Ja | DT15 | Tijdstip berekening door DUO |
| 10 | Status bepaling bekostigingsstatus | Ja | AN1 | `V` = Voorlopig, `D` = Definitief |
| 11 | Bekostigingsstatus | Nee | AN1 | `J` / `N` |
| 12 | Bijdrage diplomawaarde | Nee | N1 | Individuele bijdrage aan de diplomawaarde |

## Diplomawaarde en niveau

De **diplomawaarde** is het bekostigingsbedrag dat een instelling ontvangt per behaald diploma. Het bedrag is afhankelijk van het niveau van het diploma én het hoogste eerder bekostigde niveau:

- Een student die een diploma behaalt op een niveau dat al eerder bekostigd is, levert minder of geen bijdrage aan de diplomawaarde.
- Een **specialistendiploma** (niveau 4-expert) telt apart van het regulier niveau-4 diploma.
