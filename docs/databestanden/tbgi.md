# TBGI – Terugmelding BekostigingsGrondslagen individueel

## Definitie

Het bestand TBG-i (Terugmelding BekostigingsGrondslagen-individueel) bevat de bekostigingsgrondslagen per student voor het aangevraagde **bekostigingsjaar**. DUO levert dit bestand aan de instelling na afloop van de bekostigingsberekening.

**Bestandsnaam:** `TBGI_BRIN_BEKOSTIGINGSJAAR_AANMAAKDATUM.XML`

Voorbeeld: `TBGI_25LX_2027_20251124.XML`

### Tijdsbereik

Een bekostigingsjaar T heeft betrekking op:

- **Inschrijvingen** geldig in studiejaar (1 aug T−2 t/m 31 jul T−1)
- **Diploma's** behaald in kalenderjaar T−2

Voorbeeld: bekostigingsjaar 2027 = inschrijvingen studiejaar 2025–2026, diploma's behaald in 2025.

## Inhoud

- Alle inschrijvingen die in het studiejaar geldig zijn, met per inschrijving:
    - Alle teldata (1-10 en 1-2) met bijbehorende bekostigingsgrondslagen
    - BBL/BOL-factor, prijsfactor, bijdrage aan deelnemerswaarde
    - Alle BPV's die relevant zijn voor bekostiging (alleen BBL)
    - Alle signalen (beslisboomcontroles) met parameters
- Alle diploma's behaald in het kalenderjaar, met:
    - Bijdrage aan diplomawaarde
    - Alle signalen

!!! info "Inschrijving zonder teldata"
    Een inschrijving zonder `<Teldatum>`-elementen betekent: de inschrijving komt niet voor bekostiging in aanmerking (geen geldige inschrijving op 1-10 of 1-2).

## Technisch formaat

| Eigenschap | Waarde |
|---|---|
| Formaat | XML |
| Codering | UTF-8 |
| Root-element | `<Bekostigingsgrondslagen>` |

### XML-structuur

```xml
<Bekostigingsgrondslagen>
  <Inschrijving>
    <BRIN/>
    <Burgerservicenummer/>
    <Onderwijsnummer/>
    <Inschrijvingvolgnummer/>
    <DatumInschrijving/>
    <DatumUitschrijvingGepland/>
    <DatumUitschrijvingWerkelijk/>
    <NiveauHoogstBekostigdeDiploma/>
    <Teldatum>
      <Teldatum/>                          <!-- datum, bijv. 2025-10-01 -->
      <DatumTijdBepalingBekostigingsgrondslagen/>
      <StatusBepalingBekostigingsstatus/>  <!-- V of D -->
      <LeeftijdOpEenAugustusStudiejaar/>
      <Opleidingcode/>
      <Niveau/>
      <Leertraject/>
      <Leerroutefase/>
      <IndicatieBekostigbaar/>
      <Bekostigingsstatus/>
      <InschrijvingVoorCorrectiefactor/>
      <BBLBOLFactor/>
      <PrijsfactorMBO/>
      <AantalBekostigdeVerblijfsjarenMBO/>
      <Verblijfsjaarfactor/>
      <BijdrageInschrijvingAanDeelnemerswaarde/>
      <BekostigingsrelevanteBPV>
        <Inschrijvingvolgnummer/>
        <Volgnummer/>
        <Afsluitdatum/>
        <DatumBegin/>
        <DatumEindGepland/>
        <DatumEindWerkelijk/>
        <Opleidingcode/>
      </BekostigingsrelevanteBPV>
      <Signaal>
        <Signaalvolgnummer/>
        <Signaalcode/>
        <Signaalomschrijving/>
        <Parameter>
          <Parametervolgnummer/>
          <Parameternaam/>
          <Parameterwaarde/>
        </Parameter>
      </Signaal>
    </Teldatum>
  </Inschrijving>
  <Diploma>
    <BRIN/>
    <Burgerservicenummer/>
    <Onderwijsnummer/>
    <Resultaatvolgnummer/>
    <Opleidingcode/>
    <Inschrijvingvolgnummer/>
    <DatumBehaald/>
    <Niveau/>
    <IndicatieSpecialistendiploma/>
    <NiveauHoogstBekostigdeDiploma/>
    <IndicatieHoogstBekostigdeDiplomaIsSpecialist/>
    <DatumTijdBepalingBekostigingsgrondslagen/>
    <StatusBepalingBekostigingsstatus/>
    <Bekostigingsstatus/>
    <BijdrageDiplomawaarde/>
    <Signaal>...</Signaal>
  </Diploma>
</Bekostigingsgrondslagen>
```

## Gegevensgroepen

### Inschrijving

| Veld | Verplicht | Formaat | Definitie | Voorbeeldwaarde |
|---|---|---|---|---|
| BRIN | Ja | AN4 | Unieke instelling-code | `25LX` |
| Burgerservicenummer | Nee* | AN9 | BSN of ONR is gevuld | — |
| Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN | — |
| Inschrijvingvolgnummer | Ja | AN1..20 | Inschrijvingsreferentie van de instelling | `002` |
| DatumInschrijving | Ja | D `ccyy-mm-dd` | Begin inschrijving | `2024-02-01` |
| DatumUitschrijvingGepland | Ja | D `ccyy-mm-dd` | Geplande einddatum | `2026-01-31` |
| DatumUitschrijvingWerkelijk | Nee | D `ccyy-mm-dd` | Werkelijke einddatum | — |
| NiveauHoogstBekostigdeDiploma | Nee | Zie [Waardenlijsten](../waardenlijsten.md) | Hoogste eerder bekostigde diplomaniveau | — |

### Teldatum (per inschrijving)

| Veld | Verplicht | Formaat | Definitie | Voorbeeldwaarde |
|---|---|---|---|---|
| Teldatum | Ja | D `ccyy-mm-dd` | Meetmoment (bijv. `2025-10-01`) | `2025-10-01` |
| DatumTijdBepalingBekostigingsgrondslagen | Ja | DT | Wanneer grondslagen berekend zijn | `2025-11-21 10:42:29` |
| StatusBepalingBekostigingsstatus | Ja | AN1 | `V` = Voorlopig, `D` = Definitief | `V` |
| LeeftijdOpEenAugustusStudiejaar | Ja | N1..3 | Leeftijd in jaren op 1-8 van het studiejaar | `25` |
| Opleidingcode | Ja | AN5 | CREBO-code | `25748` |
| Niveau | Ja | AN5 | Zie [Waardenlijsten](../waardenlijsten.md) | `MBO-1` |
| Leertraject | Ja | AN2..6 | Zie [Waardenlijsten](../waardenlijsten.md) | `BOL` |
| Leerroutefase | Nee | AN2..3 | Zie [Waardenlijsten](../waardenlijsten.md) | — |
| IndicatieBekostigbaar | Ja | Boolean | Of instelling aanvraagt voor bekostiging | `true` |
| Bekostigingsstatus | Nee | Boolean | Of DUO bekostiging toekent | `true` |
| InschrijvingVoorCorrectiefactor | Ja | Boolean | Telt mee voor correctiefactor 1-10/1-2 | `true` |
| BBLBOLFactor | Nee | N5.2 | Factor voor leertraject (BBL < BOL) | `1` |
| PrijsfactorMBO | Nee | N5.2 | Factor per opleiding | `1` |
| AantalBekostigdeVerblijfsjarenMBO | Nee | N2 | n.v.t. na 01-10-2018 | `0` |
| Verblijfsjaarfactor | Nee | N10.2 | n.v.t. na 01-10-2018 | — |
| BijdrageInschrijvingAanDeelnemerswaarde | Nee | N15.6 | Individuele bijdrage aan deelnemerswaarde | `1` |

### Diploma

| Veld | Verplicht | Formaat | Definitie | Voorbeeldwaarde |
|---|---|---|---|---|
| BRIN | Ja | AN4 | Instelling waar diploma behaald | `25LX` |
| Burgerservicenummer | Nee* | AN9 | BSN of ONR is gevuld | — |
| Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN | — |
| Resultaatvolgnummer | Ja | AN1..20 | Diploma-referentie van de instelling | `1362433` |
| Opleidingcode | Ja | AN5 | CREBO-code | `25297` |
| Inschrijvingvolgnummer | Ja | AN1..20 | Gekoppelde inschrijving | `001` |
| DatumBehaald | Ja | D `ccyy-mm-dd` | Datum diploma behaald | `2025-06-17` |
| Niveau | Ja | AN5 | Zie [Waardenlijsten](../waardenlijsten.md) | `MBO-4` |
| IndicatieSpecialistendiploma | Ja | Boolean | Is het een specialistendiploma | `false` |
| NiveauHoogstBekostigdeDiploma | Ja | AN5 | Hoogste eerder bekostigde niveau | — |
| IndicatieHoogstBekostigdeDiplomaIsSpecialist | Ja | Boolean | Hoogste eerder behaalde is specialist | — |
| DatumTijdBepalingBekostigingsgrondslagen | Ja | DT | Wanneer grondslagen berekend | `2025-07-07 07:13:15` |
| StatusBepalingBekostigingsstatus | Ja | AN1 | `V` = Voorlopig, `D` = Definitief | `V` |
| Bekostigingsstatus | Ja | Boolean | Of DUO bekostiging toekent | `true` |
| BijdrageDiplomawaarde | Nee | N15.6 | Individuele bijdrage aan diplomawaarde | `5` |

## Voorbeeld (demo-data 25LX, bekostigingsjaar 2027)

!!! note "Voorbeeld is ingekort"
    Het `<Teldatum>`-blok bevat in werkelijkheid alle 16 elementen uit de veldtabel hierboven (inclusief `Verblijfsjaarfactor`, `LeeftijdOpEenAugustusStudiejaar`, enz.). Het voorbeeld toont een representatieve subset. Zie de demo-XML voor de volledige structuur.

```xml
<?xml version="1.0" encoding="utf-8"?>
<Bekostigingsgrondslagen>
  <Inschrijving>
    <BRIN>25LX</BRIN>
    <Burgerservicenummer>100000000</Burgerservicenummer>
    <Onderwijsnummer xsi:nil="true"/>
    <Inschrijvingvolgnummer>002</Inschrijvingvolgnummer>
    <DatumInschrijving>2024-02-01</DatumInschrijving>
    <DatumUitschrijvingGepland>2026-01-31</DatumUitschrijvingGepland>
    <DatumUitschrijvingWerkelijk xsi:nil="true"/>
    <NiveauHoogstBekostigdeDiploma xsi:nil="true"/>
    <Teldatum>
      <Teldatum>2025-10-01</Teldatum>
      <StatusBepalingBekostigingsstatus>V</StatusBepalingBekostigingsstatus>
      <Opleidingcode>25748</Opleidingcode>
      <Niveau>MBO-1</Niveau>
      <Leertraject>BOL</Leertraject>
      <IndicatieBekostigbaar>true</IndicatieBekostigbaar>
      <Bekostigingsstatus>true</Bekostigingsstatus>
      <BBLBOLFactor>1</BBLBOLFactor>
      <PrijsfactorMBO>1</PrijsfactorMBO>
      <BijdrageInschrijvingAanDeelnemerswaarde>1</BijdrageInschrijvingAanDeelnemerswaarde>
      <!-- overige Teldatum-elementen aanwezig in data: zie veldtabel -->
    </Teldatum>
  </Inschrijving>
  <Diploma>
    <BRIN>25LX</BRIN>
    <Burgerservicenummer>200000000</Burgerservicenummer>
    <Onderwijsnummer xsi:nil="true"/>
    <Inschrijvingvolgnummer>001</Inschrijvingvolgnummer>
    <Resultaatvolgnummer>1362433</Resultaatvolgnummer>
    <Opleidingcode>25297</Opleidingcode>
    <DatumBehaald>2025-06-17</DatumBehaald>
    <Niveau>MBO-4</Niveau>
    <IndicatieSpecialistendiploma>false</IndicatieSpecialistendiploma>
    <NiveauHoogstBekostigdeDiploma xsi:nil="true"/>
    <IndicatieHoogstBekostigdeDiplomaIsSpecialist xsi:nil="true"/>
    <StatusBepalingBekostigingsstatus>V</StatusBepalingBekostigingsstatus>
    <Bekostigingsstatus>true</Bekostigingsstatus>
    <BijdrageDiplomawaarde>5</BijdrageDiplomawaarde>
  </Diploma>
</Bekostigingsgrondslagen>
```
