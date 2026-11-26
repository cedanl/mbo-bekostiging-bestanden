---
icon: lucide/life-buoy
---

# Problemen oplossen

Elke melding hieronder is gecontroleerd in de code of in de CLI (`mbo`). Staat jouw probleem er niet bij, kijk dan eerst in `quality.json` van de levering of van het analysemodel.

| Symptoom | Oorzaak | Oplossing |
|---|---|---|
| `mbo verwerk: Geen pseudonimisering_salt beschikbaar` (exitcode 1) | `MBO_PSEUDONIMISERING_SALT` is niet gezet | Zet de variabele, zie [Installatie](aan-de-slag.md#installatie). Alleen als je bewust identifiers wilt behouden: `--persoonsverwerking identifiers_behouden` ([Privacy](privacy.md#identifiers-behouden)) |
| `mbo verwerk` eindigt met exitcode 3 | De kwaliteitspoort geeft status `fail`, bijvoorbeeld door parseverlies (een gevulde datum of getal die niet parseert) | Tabellen en rapport staan in `<doel>/diagnose/`; een eerdere versie in de doelmap blijft ongewijzigd (#415). Bekijk `quality.json`. Alleen voor exploratief werk bouwt `--allow-quality-errors` toch door |
| `mbo star` eindigt met exitcode 3 | `quality.json` heeft status `fail` (#289) | Ster en rapport staan in `<output>/diagnose/`; een eerdere publicatie in `<output>/datamodel/` blijft ongewijzigd (#363). Los de errors op, of gebruik `--allow-quality-errors` voor exploratief werk |
| `mbo verwerk: Doelmap … bevat geen eerdere brondata … en zou in zijn geheel worden vervangen` | De doelmap is niet leeg en bevat geen eerdere brondata (geen `quality.json` of `diagnose/`) | Kies een lege map, of een eigen map per levering |
| `mbo verwerk: Onbekend bestandstype` | De bestandsnaam begint niet met `RO`, `TBGI` of `GRONDSLAG` | Gebruik de bestandsnaam zoals DUO die levert, zie [Bestandsnamen decoderen](databestanden/index.md#bestandsnamen-decoderen) |
| Een kapot bronbestand | Het bestand is niet te lezen | Exitcode 1 met een korte melding (#291). In de app staat de fout op Home (#290) |
| `mbo star` weigert brondata | De brondata is van vóór v4.0.0 en bevat nog BSN of onderwijsnummer | Verwerk de leveringen opnieuw met de huidige versie en verwijder de oude mappen, zie [Privacy](privacy.md#brondata-van-voor-v400) |
| Leveringen laten zich niet combineren | Ze zijn met verschillende privacyprofielen verwerkt (pseudonimiseren en identifiers behouden) | Verwerk ze allemaal opnieuw met dezelfde keuze ([Privacy](privacy.md#identifiers-behouden)) |
| Dezelfde persoon krijgt verschillende `_persoon_id`'s | Een pseudoniem is alleen te koppelen met dezelfde salt; ook is een PGN uit GRONDSLAG nooit aan RO of TBGI te koppelen (DUO levert een omgenummerd PGN) | Verwerk alle leveringen met dezelfde salt; zie [Persoon over bronfamilies heen](datamodel.md#persoon-over-bronfamilies-heen) |
| JR of DR lijken verkeerd | Het zijn indicatieve proxy's op basis van alleen de eigen leveringen (#118, #119, #296, #297); geen formele Inspectie-indicatoren | Zie [Ontwerpkeuzes](ontwerpkeuzes.md#jr-en-dr-blijven-proxys) |
| Waarschuwing over onbekende opleidingscodes | De referentiedata is waarschijnlijk verouderd: de data bevat opleidingscodes die de referentie niet kent, in inschrijvingen die beginnen na de dekking van de referentie | `uv run python scripts/update_sbb_koppeltabel.py`; dat werkt ook het manifest bij |
