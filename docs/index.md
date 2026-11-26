---
icon: lucide/house
---

# MBO-bekostigingsbestanden

DUO levert aan MBO-instellingen periodiek bestanden waarmee de instelling kan controleren of haar studenten bekostigd worden en op welke grondslag. Deze bestanden zijn technisch van opzet: meerdere recordtypes per bestand, gecodeerde velden, geen kolomkoppen.

**Deze tool leest die ruwe bestanden in en levert twee producten**, direct bruikbaar in Excel, Python, R of Power BI:

| Product | Voor wie |
|---|---|
| [Brondata per levering](producten/brondata.md): elk DUO-bestand per recordtype, getrouw aan de levering | Wie eigen keuzes wil maken of een levering wil controleren |
| [Analysemodel](producten/analysemodel.md): een star schema dat de leveringen samenvoegt | Wie direct wil analyseren met de keuzes van deze tool |

De data is gepseudonimiseerd (`_persoon_id` in plaats van BSN, onderwijsnummer of PGN), maar blijft persoonsgegevens. Lees [opslag en retentie](aan-de-slag.md#opslag-en-retentie-van-brondata) voordat je de uitvoer deelt.

## Snel starten

Installeer met `uv sync`, zet de pseudonimiserings-salt en start de app of de CLI. De stappen staan in [Aan de slag](aan-de-slag.md). Demo-data staat in [cedanl/duo-mbo-datafiles](https://github.com/cedanl/duo-mbo-datafiles).

## Waar wil je heen?

| Ik wil… | Ga naar |
|---|---|
| de tool installeren en draaien | [Aan de slag](aan-de-slag.md) |
| weten wat de producten bevatten | [Producten](producten/brondata.md) |
| de tabellen en kolommen van het analysemodel kennen | [Datamodel](datamodel.md) |
| weten waarom het analysemodel iets zo doet | [Ontwerpkeuzes](ontwerpkeuzes.md) |
| de inhoud van een DUO-bestand opzoeken | [Databestanden](databestanden/index.md) en [Recordtypes](recordtypes/index.md) |

## Bronnen

- Bestandsbeschrijving DUO PvE MBO-instelling (hoofdstuk 13–17), `bestandsbeschrijving_beknopt.pdf` in deze repo; versie, datum en sha256 staan alleen in `metadata/pve_bron.json`. Een wekelijkse workflow (`pve-upstream`) meldt als duo.nl een andere versie publiceert (#299); hoe je die verwerkt en wat er per versie veranderde, staat in [PvE-versies](pve-wijzigingen.md) (#298)
- Demo-data: [cedanl/duo-mbo-datafiles](https://github.com/cedanl/duo-mbo-datafiles)
