---
icon: lucide/shield-check
---

# Privacy en pseudonimisering

De tool werkt met persoonsgegevens uit DUO-bestanden. Deze pagina zegt wat de tool daarmee doet, wat je zelf moet regelen en waar je op moet letten. Alles hieronder staat ook in de rest van deze documentatie en in de code; deze pagina brengt het bij elkaar.

## In het kort

- BSN, onderwijsnummer en PGN worden bij het verwerken vervangen door een pseudoniem, `_persoon_id`.
- De uitvoer blijft persoonsgegevens: pseudoniemen plus kenmerken als geboortedatum en postcodecijfers.
- Zonder salt stopt de verwerking. Gebruik voor alle leveringen in één analysemodel dezelfde salt.
- De ruwe bestanden in `data/01-raw/` zijn de auditbron met de echte identifiers.
- De app is een lokale, single-user analysetool en wordt bewust niet gehost (#82).

## Wat is pseudonimisering in deze tool?

Persoons-identifiers (BSN, Onderwijsnummer, PGN) worden met HMAC-SHA256
gehasht, samen met hun soort: een PGN, BSN en ONr met dezelfde cijfers krijgen
een verschillend `_persoon_id`. Dat vereist een salt, ingesteld via de env-var:

```bash
export MBO_PSEUDONIMISERING_SALT="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
```

Zonder geldige salt faalt de stap die brondata schrijft (`mbo verwerk`, "Verwerk
bestanden" in de app; fail-closed): decode vervangt BSN, onderwijsnummer en PGN
door het pseudoniem `_persoon_id`, zodat ze `02-prepared/` niet bereiken (#173).
Gebruik voor alle leveringen die samen in één analysemodel komen dezelfde salt.

- **Productie:** de salt komt uitsluitend uit de environment (secret manager,
  bijv. via het deploymentplatform). Geen salt in de repo of in
  applicatieconfig opslaan.
- **Lokale demo:** het `export`-commando hierboven genereert een willekeurige
  salt per shell. Bewaar die zelf als je pseudoniemen tussen sessies wilt
  kunnen koppelen.
- **Tests/CI:** gebruiken de vaste, publieke waarde
  `ci-test-key-do-not-use-in-production`. Die is herleidbaar en hoort dus
  nooit bij echte data.
- `app/config.toml` heeft nog een `[security] pseudonimisering_salt`-fallback
  voor oude setups, maar de meegeleverde config bevat bewust géén salt meer.
  Gebruik die fallback niet voor echte data; een echte salt hoort er niet thuis.

## Wat zit er nog wel in de uitvoer?

De brondata (`data/02-prepared/`) bevat geen BSN, onderwijsnummer of PGN meer, alleen
het pseudoniem `_persoon_id` (#173); bij de opt-in modus identifiers behouden (#435) wel. Het blijft persoonsgegevens: pseudoniemen plus
kenmerken als geboortedatum en postcodecijfers. De ruwe bestanden in `data/01-raw/` zijn
de auditbron met de echte identifiers. Ga met beide zorgvuldig om:

- **Opslag:** alleen lokaal, op een schijf met toegangsbeperking van de gebruiker; nooit in git
  (echte data is gitignored), nooit op een gedeelde of gehoste omgeving. De app wordt niet
  gehost (#82).
- **Retentie:** bewaar de brondata niet langer dan nodig om het analysemodel te bouwen.
  Het analysemodel (`03-output/`) bevat geen bronidentifiers en kan zonder de brondata
  worden bewaard; de brondata is opnieuw te maken uit de ruwe bestanden.
- **Verwijderen:** verwijder `02-prepared/` zodra het analysemodel gebouwd en gecontroleerd is.
  Een pseudoniem is alleen te koppelen met dezelfde salt.

## Identifiers behouden

Pseudonimiseren is de standaard. Voor een BI-team dat de DUO-gegevens in een
beveiligde, interne omgeving aan een eigen administratie koppelt, is er een
tweede, expliciete modus:

| Modus | Wanneer | Salt | Uitvoer |
|---|---|---|---|
| **Pseudonimiseren** (standaard) | Je hebt geen persoonskoppeling nodig | Vereist; zonder salt stopt de verwerking | Alleen `_persoon_id`, geen BSN/ONR/PGN |
| **Identifiers behouden** | Je koppelt intern aan een eigen bronbestand, in een vertrouwde omgeving | Niet nodig | BSN, onderwijsnummer en PGN blijven staan; in het analysemodel alleen in `dim_deelnemer` |

Kies de modus op Home ("Hoe moeten persoonsidentifiers worden verwerkt?") of in
de CLI:

```bash
uv run mbo verwerk <bron> <doel> --persoonsverwerking identifiers_behouden
```

- Een ontbrekende salt schakelt de tweede modus **nooit** in: zonder de
  expliciete keuze faalt de verwerking nog steeds.
- Bij identifiers behouden bevat de uitvoer persoonsgegevens. De CLI en de app
  waarschuwen daarvoor; behandel `02-prepared/` en `03-output/` dan als
  persoonsgegevens en deel ze niet.
- `_persoon_id` is in deze modus een ongezouten SHA-256 per identifierdomein:
  een stabiele join-sleutel, geen privacybescherming.
- Het gekozen profiel staat als `privacyprofiel` in `quality.json`. Leveringen
  met verschillende profielen kunnen niet in één analysemodel; verwerk ze dan
  allemaal opnieuw met dezelfde keuze.
- In de app blijven persoonskolommen in preview en download standaard
  verborgen, ook de identifiers.
- De standaardkeuze op Home staat in `app/config.toml` (`[security]
  persoonsverwerking`); de gebruiker kiest altijd zelf.

## Brondata van vóór v4.0.0

Brondata van vóór v4.0.0 bevat nog BSN/onderwijsnummer; `mbo star` weigert die.
  Verwerk de leveringen opnieuw en verwijder de oude mappen.

## Persoonsgegevens in de app

In preview en download zijn persoonskolommen standaard verborgen. Welke kolommen dat zijn, staat bij [de interactieve app](aan-de-slag.md#interactieve-app).
