# SLR / CTR – Sluit- en controletotalen

## SLR – Sluitrecord

Het SLR-record is altijd het **laatste record** in het bestand. Het bevat tellingen van alle recordtypen in het bestand.

### RO-variant

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `SLR` |
| 2 | Totaal aantal personen | Ja | N12 | Aantal PER-records |
| 3 | Totaal aantal deelnames | Ja | N12 | Aantal ISG-records |
| 4 | Totaal aantal deelnameperiodes | Ja | N12 | Aantal ISP-records |
| 5 | Totaal aantal periodes extra ondersteuning | Ja | N12 | Aantal ISE-records |
| 6 | Totaal aantal BPV's | Ja | N12 | Aantal BPV-records |
| 7 | Totaal aantal diploma's | Ja | N12 | Aantal DIP-records |
| 8 | Totaal aantal AMvB-onderdelen | Ja | N12 | Aantal AMO-records |
| 9 | Totaal aantal generieke examenonderdelen | Ja | N12 | Aantal GEO-records |
| 10 | Totaal aantal keuzedelen | Ja | N12 | Aantal KZD-records |

**Voorbeeld:**
```
SLR|16616|19859|31053|2|28260|4696|133|11758|11511
```
*(16.616 personen, 19.859 inschrijvingen, 31.053 inschrijvingsperiodes, 2 ISE, 28.260 BPV's, 4.696 diploma's, 133 AMO, 11.758 GEO, 11.511 KZD)*

### GRONDSLAG IP-variant

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `SLR` |
| 2 | Aantal PER-records | Ja | N10 | |
| 3 | Aantal ISG-records | Ja | N10 | |
| 4 | Aantal ISP-records | Ja | N10 | |
| 5 | Aantal ISE-records | Ja | N10 | |
| 6 | Aantal BPV-records | Ja | N10 | |
| 7 | Aantal BII-records | Ja | N10 | |
| 8 | Aantal DIP-records | Ja | N10 | |
| 9 | Aantal BID-records | Ja | N10 | |
| 10 | Aantal AMO-records | Ja | N10 | |
| 11 | Aantal GEO-records | Ja | N10 | |
| 12 | Aantal KZD-records | Ja | N10 | |

**Voorbeeld:**
```
SLR;14027;15415;23093;1;21410;0;3238;0;86;7302;7622
```
*(14.027 PER, 15.415 ISG, 23.093 ISP, 1 ISE, 21.410 BPV, 0 BII, 3.238 DIP, 0 BID, 86 AMO, 7.302 GEO, 7.622 KZD)*

---

## CTR – Controletotalen (OBO)

Het CTR-record wordt gebruikt in de **OBO** (Overzicht Basis- en diplomagegevens Onderzoek) en heeft een andere structuur dan het SLR.

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `CTR` |
| 2 | Totaal aantal deelnames | Ja | N12 | Aantal ISG-records |
| 3 | Totaal aantal diploma's | Ja | N12 | Aantal DIP-records |
| 4 | Totaal opleidingcodes | Ja | N12 | Totaal opleidingcodes uit ISP-, BPV- en DIP-records |
| 5 | Totaal generaal | Ja | N12 | Som van opleidingcodes + inschrijvingen + bekostigbare ISP+DIP + diploma's |
| 6 | Totaal aantal records ISP en DIP bekostigbaar | Ja | N12 | ISP+DIP-records met indicatie bekostigbaar = J |

!!! note
    CTR wordt alleen in OBO-bestanden gebruikt. RO en GRONDSLAG IP gebruiken SLR.
