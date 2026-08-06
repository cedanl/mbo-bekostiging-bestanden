# ISE – Extra ondersteuning

Het ISE-record registreert een periode van **extra ondersteuning** (bijzondere ondersteuning) bij een inschrijving.

## RO-variant en GRONDSLAG IP-variant

De velden zijn grotendeels gelijk; het verschil zit in de identificerende velden (BSN vs PGN) en datumformaat.

=== "RO"

    | Pos | Veld | Verplicht | Formaat | Definitie | Voorbeeldwaarde |
    |---|---|---|---|---|---|
    | 1 | Recordsoort | Ja | AN3 | Waarde `ISE` | `ISE` |
    | 2 | Burgerservicenummer | Nee* | AN9 | BSN van de student | — |
    | 3 | Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN | — |
    | 4 | Inschrijvingvolgnummer | Ja | AN1..20 | Koppeling naar het ISG-record | `C3` |
    | 5 | Datum begin | Ja | D `ccyy-mm-dd` | Begindatum extra ondersteuning (inclusief) | `2023-09-01` |
    | 6 | Datum eind | Nee | D `ccyy-mm-dd` | Einddatum extra ondersteuning (inclusief) | `2024-01-31` |

    **Voorbeeld:**
    ```
    ISE|BSN1||C3|2023-09-01|2024-01-31
    ```

=== "GRONDSLAG IP"

    | Pos | Veld | Verplicht | Formaat | Definitie | Voorbeeldwaarde |
    |---|---|---|---|---|---|
    | 1 | Recordsoort | Ja | AN3 | Waarde `ISE` | `ISE` |
    | 2 | PGN | Ja | N9 | Pseudonummer van de student | — |
    | 3 | BRIN | Ja | AN4 | Instelling van inschrijving | `27DV` |
    | 4 | Inschrijvingsvolgnummer | Ja | AN1..20 | Koppeling naar het ISG-record | `C3` |
    | 5 | Datum begin extra ondersteuning | Ja | D `ccyymmdd` | Begindatum | `20230901` |
    | 6 | Datum eind extra ondersteuning | Nee | D `ccyymmdd` | Einddatum | `20240131` |

    **Voorbeeld:**
    ```
    ISE;BSN1;27DV;C3;20230901;20240131
    ```
