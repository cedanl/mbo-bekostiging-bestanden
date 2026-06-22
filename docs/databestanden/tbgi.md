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

| Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|
| BRIN | Ja | AN4 | Unieke instelling-code |
| Burgerservicenummer | Nee* | AN9 | BSN of ONR is gevuld |
| Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN |
| Inschrijvingvolgnummer | Ja | AN1..20 | Inschrijvingsreferentie van de instelling |
| DatumInschrijving | Ja | D `ccyy-mm-dd` | Begin inschrijving |
| DatumUitschrijvingGepland | Ja | D `ccyy-mm-dd` | Geplande einddatum |
| DatumUitschrijvingWerkelijk | Nee | D `ccyy-mm-dd` | Werkelijke einddatum |
| NiveauHoogstBekostigdeDiploma | Nee | Zie [Waardenlijsten](../waardenlijsten.md) | Hoogste eerder bekostigde diplomaniveau |

### Teldatum (per inschrijving)

| Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|
| Teldatum | Ja | D `ccyy-mm-dd` | Meetmoment (bijv. `2025-10-01`) |
| DatumTijdBepalingBekostigingsgrondslagen | Ja | DT | Wanneer grondslagen berekend zijn |
| StatusBepalingBekostigingsstatus | Ja | AN1 | `V` = Voorlopig, `D` = Definitief |
| LeeftijdOpEenAugustusStudiejaar | Ja | N1..3 | Leeftijd in jaren op 1-8 van het studiejaar |
| Opleidingcode | Ja | AN5 | CREBO-code |
| Niveau | Ja | AN5 | Zie [Waardenlijsten](../waardenlijsten.md) |
| Leertraject | Ja | AN2..6 | Zie [Waardenlijsten](../waardenlijsten.md) |
| Leerroutefase | Nee | AN2..3 | Zie [Waardenlijsten](../waardenlijsten.md) |
| IndicatieBekostigbaar | Ja | Boolean | Of instelling aanvraagt voor bekostiging |
| Bekostigingsstatus | Nee | Boolean | Of DUO bekostiging toekent |
| InschrijvingVoorCorrectiefactor | Ja | Boolean | Telt mee voor correctiefactor 1-10/1-2 |
| BBLBOLFactor | Nee | N5.2 | Factor voor leertraject (BBL < BOL) |
| PrijsfactorMBO | Nee | N5.2 | Factor per opleiding |
| AantalBekostigdeVerblijfsjarenMBO | Nee | N2 | n.v.t. na 01-10-2018 |
| Verblijfsjaarfactor | Nee | N10.2 | n.v.t. na 01-10-2018 |
| BijdrageInschrijvingAanDeelnemerswaarde | Nee | N15.6 | Individuele bijdrage aan deelnemerswaarde |

### Diploma

| Veld | Verplicht | Formaat | Definitie |
|---|---|---|---|
| BRIN | Ja | AN4 | Instelling waar diploma behaald |
| Burgerservicenummer | Nee* | AN9 | BSN of ONR is gevuld |
| Onderwijsnummer | Nee* | AN9 | Alternatief voor BSN |
| Resultaatvolgnummer | Ja | AN1..20 | Diploma-referentie van de instelling |
| Opleidingcode | Ja | AN5 | CREBO-code |
| Inschrijvingvolgnummer | Ja | AN1..20 | Gekoppelde inschrijving |
| DatumBehaald | Ja | D `ccyy-mm-dd` | Datum diploma behaald |
| Niveau | Ja | AN5 | Zie [Waardenlijsten](../waardenlijsten.md) |
| IndicatieSpecialistendiploma | Ja | Boolean | Is het een specialistendiploma |
| NiveauHoogstBekostigdeDiploma | Ja | AN5 | Hoogste eerder bekostigde niveau |
| IndicatieHoogstBekostigdeDiplomaIsSpecialist | Ja | Boolean | Hoogste eerder behaalde is specialist |
| DatumTijdBepalingBekostigingsgrondslagen | Ja | DT | Wanneer grondslagen berekend |
| StatusBepalingBekostigingsstatus | Ja | AN1 | `V` = Voorlopig, `D` = Definitief |
| Bekostigingsstatus | Ja | Boolean | Of DUO bekostiging toekent |
| BijdrageDiplomawaarde | Nee | N15.6 | Individuele bijdrage aan diplomawaarde |

## Voorbeeld (demo-data 25LX, bekostigingsjaar 2027)

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
    </Teldatum>
  </Inschrijving>
  <Diploma>
    <BRIN>25LX</BRIN>
    <Burgerservicenummer>200000000</Burgerservicenummer>
    <Resultaatvolgnummer>1362433</Resultaatvolgnummer>
    <Opleidingcode>25297</Opleidingcode>
    <DatumBehaald>2025-06-17</DatumBehaald>
    <Niveau>MBO-4</Niveau>
    <IndicatieSpecialistendiploma>false</IndicatieSpecialistendiploma>
    <StatusBepalingBekostigingsstatus>V</StatusBepalingBekostigingsstatus>
    <Bekostigingsstatus>true</Bekostigingsstatus>
    <BijdrageDiplomawaarde>5</BijdrageDiplomawaarde>
  </Diploma>
</Bekostigingsgrondslagen>
```
