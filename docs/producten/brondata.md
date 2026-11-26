---
icon: lucide/file-input
---

# Brondata per levering

De brondata is het eerste product van de tool: elk DUO-bestand per recordtype, getrouw aan de levering. Het tweede product is het [analysemodel](analysemodel.md).

## Wat je krijgt

| | Brondata per levering |
|---|---|
| Map | `data/02-prepared/<map>/<levering>/` |
| Wat | Elk DUO-bestand per recordtype |
| Keuzes | Alleen technisch (typering, notaties) |
| Gegarandeerd | Kolommen en volgorde volgens het PvE; een onbekend recordtype of gevuld veld voorbij het schema breekt de ingest (fail-closed, #257) in plaats van stil te worden genegeerd |
| Status | Per levering in `quality.json` → `status`; in de app bij de brondata op Werkbare data |
| Beperkingen | Gepseudonimiseerd (`_persoon_id` in plaats van BSN/ONr/PGN, #173), maar nog persoonsgegevens; zie [opslag en retentie](../privacy.md#wat-zit-er-nog-wel-in-de-uitvoer) |
| Voor wie | Wie eigen keuzes wil maken of een levering wil controleren |

## Fasering

`ingest > decode > validate > export` levert de brondata. De stappen schrijven een `quality.json`.

## Opbouw van de uitvoer

Elk ruw bestand wordt genormaliseerd naar één Parquet-bestand per recordtype:

```
data/02-prepared/demo/h15/RO_27DV_20240731_20260324/
├── VLP.parquet    ← bestandskop (1 rij)
├── PER.parquet    ← personen
├── ISG.parquet    ← inschrijvingen
├── ISP.parquet    ← inschrijvingsperiodes
├── BPV.parquet    ← BPV-overeenkomsten
├── DIP.parquet    ← diploma's
├── GEO.parquet    ← generieke examenonderdelen
├── KZD.parquet    ← keuzedelen
└── SLR.parquet    ← sluitrecord (tellingen)
```

Datumvelden zijn `Date`, telvelden zijn `Int64`, lege velden zijn `null` (geen lege strings).

