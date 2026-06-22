# Waardenlijsten

Overzicht van alle gecodeerde waarden in de bekostigingsbestanden.

---

## Niveau

Geldt voor: `ISP.Niveau`, `DIP.Niveau`, `BID.Niveau`, `TBGI.Niveau`

| Waarde | Betekenis |
|---|---|
| `MBO-1` | MBO Assistent / Entreeopleiding |
| `MBO-2` | MBO Basisberoepsopleiding |
| `MBO-3` | MBO Vakopleiding |
| `MBO-4` | MBO Middenkaderopleiding of Specialistenopleiding |

---

## Leertraject

Geldt voor: `ISP.Leertraject`, `TBGI.Leertraject`

| Waarde | Betekenis | Geldig van | Geldig t/m |
|---|---|---|---|
| `BOL` | Beroepsopleidende leerweg | 01-08-1997 | — |
| `BOL_DT` | Beroepsopleidende leerweg in deeltijd | 01-08-1997 | 31-07-2023 |
| `BBL` | Beroepsbegeleidende leerweg | 01-08-1997 | — |
| `OVO` | Overig onderwijs | 01-08-1997 | — |
| `EX` | Examendeelnemer | 01-08-1997 | — |
| `ODT` | Overig onderwijs niet-diploma gericht | 01-01-2019 | — |

!!! info "BOL vs BBL"
    - **BOL** (Beroepsopleidende leerweg): student volgt onderwijs op school, met stage. Factor is hoger dan BBL.
    - **BBL** (Beroepsbegeleidende leerweg): student werkt bij leerbedrijf en gaat 1 dag per week naar school. Vereist BPV-overeenkomst.

---

## Leerroute

Geldt voor: `ISP.Leerroute`

| Waarde | Betekenis | Geldig van |
|---|---|---|
| `DLP` | Doorlopende leerroute vmbo–mbo | 01-08-2020 |

*(Andere waarden worden door DUO gespecificeerd per bekostigingsjaar)*

---

## Leerroutefase

Geldt voor: `ISP.Leerroutefase`, `TBGI.Leerroutefase`

| Waarde | Betekenis | Geldig van |
|---|---|---|
| `VO` | Het onderwijs wordt gevolgd in de VO-fase | 01-08-2020 |
| `MBO` | Het onderwijs wordt gevolgd in de MBO-fase | 01-08-2020 |

---

## Geslacht

Geldt voor: `PER.Geslacht`

| Waarde | Betekenis |
|---|---|
| `M` | Man |
| `V` | Vrouw |
| `O` | Vastgesteld onbekend |

---

## Reden uitschrijving

Geldt voor: `ISG.RedenUitschrijving`

| Waarde | Betekenis |
|---|---|
| `01` | Geslaagd / diploma behaald |
| `02` | Eigen verzoek |
| `03` | Overplaatsing naar andere instelling |
| `04` | Niet meer verschenen |
| `05` | Overlijden |
| `06` | Andere reden |
| `07` | Verwijdering |
| `08` | Administratief uitgeschreven |
| `09` | Verlies recht op bekostiging |
| `10` | Afgerond zonder diploma |

!!! note
    De volledige en actuele lijst is vastgelegd in de DUO-registratiestandaard. Niet alle codes zijn in de demo-data aanwezig.

---

## Status bepaling bekostigingsstatus

Geldt voor: `BII`, `BID`, `TBGI.StatusBepalingBekostigingsstatus`

| Waarde | Betekenis |
|---|---|
| `V` | Voorlopig – berekening kan nog wijzigen |
| `D` | Definitief – bekostiging is vastgesteld |

---

## Bekostiging (VLP GRONDSLAG)

Geldt voor: `VLP.Bekostiging` in GRONDSLAG IP MBO

| Waarde | Betekenis |
|---|---|
| `V` | Voorlopige bekostigingslevering |
| `D` | Definitieve bekostigingslevering |

---

## Indicatie bekostigbaar

Geldt voor: `ISP.IndicatieBekostigbaar`, `DIP.IndicatieBekostigbaar`

| Waarde (RO) | Waarde (GRONDSLAG) | Betekenis |
|---|---|---|
| `J` | `1` | Instelling vraagt bekostiging aan |
| `N` | `0` | Instelling vraagt geen bekostiging aan |

---

## Certificaat (KZD, AMO)

| Waarde (RO) | Waarde (GRONDSLAG) | Betekenis |
|---|---|---|
| `J` | `1` | Certificaat uitgereikt |
| `N` | `0` | Geen certificaat |

---

## Resultaat keuzedeel (KZD)

| Waarde (RO) | Waarde (GRONDSLAG) | Betekenis |
|---|---|---|
| `Behaald` | `BEHAALD` | Keuzedeel met goed gevolg afgerond |
| `Niet behaald` | `NIET BEHAALD` | Keuzedeel niet gehaald |

---

## Vrijstelling generiek examenonderdeel (GEO)

Geldt voor: `GEO.VrijstellingGeneriekExamenonderdeel`

| Waarde | Betekenis |
|---|---|
| `MBO` | Vrijstelling op grond van eerder behaald MBO-diploma |
| `HBO` | Vrijstelling op grond van eerder behaald HBO-diploma |
| `VWO` | Vrijstelling op grond van eerder behaald VWO-diploma |
| `KZDL` | Vrijstelling op grond van keuzedelen landelijk |

*(niet uitputtend; actuele lijst in DUO-registratiestandaard)*

---

## Niveauwaarden hoogst bekostigde diploma

Geldt voor: `TBGI.NiveauHoogstBekostigdeDiploma`, `BID.NiveauHoogstBekostigdeDiploma`

Zelfde waardenlijst als [Niveau](#niveau), plus leeg (student heeft nog geen eerder bekostigd diploma).
