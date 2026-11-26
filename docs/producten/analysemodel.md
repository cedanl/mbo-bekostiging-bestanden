---
icon: lucide/blocks
---

# Analysemodel (star schema)

Het analysemodel is het tweede product van de tool: de leveringen samengevoegd tot dimensies en feiten. Het eerste product is de [brondata per levering](brondata.md).

## Wat je krijgt

| | Analysemodel |
|---|---|
| Map | `data/03-output/<scenario>/star/datamodel/` |
| Wat | Dimensies en feiten over alle leveringen |
| Keuzes | Inhoudelijk: canonicalisatie, hoofdinschrijving, peildatum, niveau-aanvulling, … ([Ontwerpkeuzes](../ontwerpkeuzes.md)) |
| Gegarandeerd | Grain en relaties per tabel ([Datamodel](../datamodel.md)); status in `quality.json` |
| Status | `quality.json` → `summary.status`; in de app bij het analysemodel op Analysemodel en in het dashboard |
| Beperkingen | JR/DR zijn indicatief: alleen de eigen leveringen (#118, #119) |
| Voor wie | Wie direct wil analyseren met de keuzes van deze tool |

## Fasering

`stack > canonicaliseer > transform (pseudonimiseer, koppel) > enrich > schooljaar > star` levert het analysemodel. De stappen schrijven een `quality.json`.

## De tabellen

Alle prepared-mappen worden gecombineerd tot Parquet-bestanden in `data/03-output/star/datamodel/`. Het analysemodel heeft vijftien tabellen: drie dimensies, acht feiten en vier metatabellen. Grain, sleutel en omschrijving per tabel staan in het [Datamodel](../datamodel.md#tabellen).

Een `levering`-kolom in elke tabel geeft aan uit welk bronbestand een rij afkomstig is (bijv. `h15/RO_27DV_20240731_20260324`).

De afleidingen (niveau-aanvulling, studiejaar, jaarbegrippen, verrijking met decodeertabellen) staan onder [Afleidingen en verrijking](../datamodel.md#afleidingen-en-verrijking).
