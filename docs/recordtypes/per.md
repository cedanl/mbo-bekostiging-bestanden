# PER – Persoonsgegevens

Het PER-record bevat de persoonsgegevens van de student. Per persoon is er precies één PER-record, waaronder alle overige records voor die persoon volgen.

## RO-variant

In het RO staan de werkelijke BSN/ONR en geboortedatum.

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `PER` |
| 2 | Burgerservicenummer | Nee* | AN9 | 9-cijferig BSN, voldoet aan elfproef; voorloopnullen altijd aanwezig |
| 3 | Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN; 9 cijfers, elfproef |
| 4 | Geboortedatum | Ja | D `ccyy-mm-dd` | Dag of dag+maand kan onbekend zijn (gevuld met `00`) |
| 5 | Geslacht | Ja | AN1 | Zie waardenlijst |

*Ofwel BSN ofwel ONR is gevuld, nooit beide.

**Geslacht waardenlijst:**

| Waarde | Betekenis |
|---|---|
| `M` | Man |
| `V` | Vrouw |
| `O` | Vastgesteld onbekend |

**Voorbeeld:**
```
PER|BSN1||1987-11-23|V
```
*(BSN is gemaskeerd als `BSN1` in demo-data; ONR-veld is leeg.)*

## GRONDSLAG IP-variant

In de GRONDSLAG is de BSN vervangen door een **PGN** (pseudonummer) en de geboortedatum door **vier leeftijden** op vaste momenten in het studiejaar. Aanvullende persoonskenmerken zijn wel aanwezig.

| Pos | Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|---|
| 1 | Recordsoort | Ja | AN3 | Waarde `PER` |
| 2 | PGN | Ja | N9 | Pseudonummer; vervangt BSN voor privacy |
| 3 | Leeftijd 1 | Ja | N2 | Leeftijd op 1-8 van het studiejaar |
| 4 | Leeftijd 2 | Ja | N2 | Leeftijd op 1-10 van het studiejaar |
| 5 | Leeftijd 3 | Ja | N2 | Leeftijd op 1-2 van het studiejaar |
| 6 | Leeftijd 4 | Ja | N2 | Leeftijd op 1-8 van het volgend studiejaar |
| 7 | Geslacht | Ja | AN1 | `M`, `V`, of `O` |
| 8 | Postcodecijfers | Ja | N4 | Postcode (4 cijfers); speciale waarden zie tabel |
| 9 | Datum overlijden | Nee | D `ccyymmdd` | Overlijdensdatum |
| 10 | Datum vestiging in Nederland | Nee | D `ccyymmdd` | |
| 11 | Datum vertrek uit Nederland | Nee | D `ccyymmdd` | |
| 12 | Code geboorteland | Nee | AN4 | GBA-landcode |
| 13 | Code geboorteland ouder 1 | Nee | AN4 | GBA-landcode |
| 14 | Code geboorteland ouder 2 | Nee | AN4 | GBA-landcode |
| 15 | Code land waarnaar vertrokken | Nee | AN4 | GBA-landcode |
| 16 | Verblijfstitel | Nee | AN2 | GBA-verblijfstitelcode |
| 17 | Nationaliteit 1 | Nee | AN4 | GBA-nationaliteitscode (tabel 32) |
| 18 | Nationaliteit 2 | Nee | AN4 | GBA-nationaliteitscode (tabel 32) |
| 19 | *(niet in spec)* | — | AN4 | In demo-data zelfde waarde als Postcodecijfers (pos 8) |
| 20 | *(niet in spec)* | — | AN2 | In demo-data zelfde waarde als Verblijfstitel (pos 16) |
| 21 | *(niet in spec)* | — | AN4 | In demo-data zelfde waarde als Nationaliteit 1 (pos 17) |

!!! warning "Extra velden in leveringsdata"
    De PvE-spec v4.8.3 beschrijft 18 velden (incl. recordsoort). In de werkelijke leveringen bevatten PER-records echter **21 velden** — drie extra velden op posities 19–21 die niet in de spec zijn gedocumenteerd. De waarden spiegelen postcode, verblijfstitel en nationaliteit 1. Een parser die strict 18 velden verwacht zal hierop breken; gebruik lenient parsing (lees alle aanwezige velden op basis van separator-count).

**Speciale postcode-waarden:**

| Waarde | Betekenis |
|---|---|
| `0010` | België |
| `0020` | Duitsland |
| `0030` | Ander land (niet NL, BE, DE) |
| `0040` | Geen vaste woon- of verblijfplaats |

**Voorbeeld:**
```
PER;BSN1;37;37;38;37;V;7425;;;;6030;6030;6030;;;0001;;7425;;0001;
```
