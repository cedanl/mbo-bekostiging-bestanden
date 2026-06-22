# Databestanden

DUO levert drie categorieën bekostigingsbestanden aan MBO-instellingen. Ze overlappen deels in inhoud maar hebben elk een eigen doel en tijdsmoment.

---

## Overzicht

| Bestand | Code | Formaat | Separator | Bestandsnaam |
|---|---|---|---|---|
| Registratieoverzicht | RO | CSV multi-record | `|` of `;` (varieert per instelling) | `RO_BRIN_BEGINDATUM_EINDDATUM.CSV` |
| TBG-i bekostigingsgrondslagen | TBGI | XML | n.v.t. | `TBGI_BRIN_JAAR_DATUM.XML` |
| GRONDSLAG IP MBO | GRONDSLAG | CSV multi-record | `;` | `GRONDSLAG_IP_MBO_BRIN_DATUM_JAAR.csv` |

---

## Wat zit er in elk bestand?

### RO – Registratieoverzicht

Het RO bevat **alle inschrijvingen en diploma's** die geldig zijn in een door de instelling opgegeven selectieperiode. Het is een momentopname: de instelling vraagt het aan voor een specifiek datumbereik.

Typisch gebruik: controleren of alle inschrijvingen goed zijn geregistreerd, vergelijken met het eigen systeem.

→ [Volledige beschrijving RO](ro.md)

### TBGI – Terugmelding BekostigingsGrondslagen individueel

De TBGI is een XML-bestand met de **bekostigingsgrondslagen per student**. Voor elke inschrijving en elk diploma staat er:

- Op welke teldata de student telt (1-10 en 1-2)
- Welke factoren zijn toegepast (BBL/BOL-factor, prijsfactor, verblijfsjaarfactor)
- Wat de bijdrage aan de deelnemerswaarde of diplomawaarde is
- Eventuele signalen (foutmeldingen) uit de DUO-beslisboomcontroles

Bekostigingsjaar T heeft betrekking op deelnames in studiejaar T-2 t/m T-1 en diploma's behaald in kalenderjaar T-2.

→ [Volledige beschrijving TBGI](tbgi.md)

### GRONDSLAG IP MBO – Afslag register-levering

De GRONDSLAG IP is een CSV-bestand met dezelfde structuur als het RO, maar dan aangevuld met **bekostigingsinformatie per inschrijving (BII) en per diploma (BID)**. Peildatum is altijd 1 oktober van het lopende studiejaar.

Privacyverschil: de BSN is hier vervangen door een **PGN** (pseudonummer), en de geboortedatum is vervangen door **vier leeftijden** op vaste meetmomenten.

→ [Volledige beschrijving GRONDSLAG IP MBO](grondslag-ip.md)

---

## Gedeelde recordstructuur

Alle CSV-bestanden zijn opgebouwd uit regels die beginnen met een recordtype-code:

```
VLP  ← altijd eerste regel (voorlooprecord)
PER  ← persoon
ISG  ← inschrijving (per persoon)
ISP  ← inschrijvingsperiode (per inschrijving)
...
SLR  ← altijd laatste regel (sluitrecord)
```

Er zijn **geen kolomkoppen** in de bestanden. De veldvolgorde per recordtype staat beschreven in [Recordtypes](../recordtypes/index.md).

---

## Bestandsnamen decoderen

### RO
```
RO _ 27DV _ 20240731 _ 20260324 .csv
     ^^^^   ^^^^^^^^   ^^^^^^^^
     BRIN   begindatum  einddatum selectieperiode
```

### TBGI
```
TBGI _ 25LX _ 2027 _ 20251124 .XML
       ^^^^   ^^^^   ^^^^^^^^
       BRIN   bekostigingsjaar  aanmaakdatum
```

### GRONDSLAG IP MBO
```
GRONDSLAG_IP_MBO _ 27DV _ 20251119 _ 2025 .csv
                   ^^^^   ^^^^^^^^   ^^^^
                   BRIN   aanmaakdatum  studiejaar
```
