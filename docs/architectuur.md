# Architectuur

## Grens presentatie–transformatie

`src/mbo_bekostiging_bestanden/` is de kernpackage: ingest, decode, validate,
transform, enrich en star. Alles daarin is Streamlit-onafhankelijk en
publiek herbruikbaar door andere repos die op de output voortbouwen.

`app/` bevat de Streamlit-app zelf én de presentatielogica die alleen de app
gebruikt — code die niet over de kern gaat, maar over hoe de kern getoond
wordt. Herkenbaar aan een onderstrepingsprefix (`_utils.py`, `_chart_docs.py`,
`_tabel_docs.py`) en geïmporteerd via `pythonpath = ["app"]`
(`pyproject.toml`), dus als platte module (`from _utils import ...`),
niet via het pakket.

**Vuistregel:** domeininhoud hoort in de package, presentatie in `app/`. Een
module die alleen opmaakt wat de app toont, hoort in `app/`; een module met
regels die een gebruiker buiten de app ook nodig heeft, hoort in de package, ook
als vooralsnog alleen de app haar importeert.

`indicatoren.py` (normen per niveau, populatieregels, minimumnoemer, oordeel,
Entree) staat daarom in de package (#294), na een periode als
`app/_indicatoren.py` (#253). #253 wilde voorkomen dat `quality` via de
indicatoren van de sterbouw ging afhangen; dat blijft zo, want `indicatoren` is
een leaf-module: ze leest alleen stertabellen en `metadata/normen.toml` en
importeert niets uit de sterbouw (`tests/test_architectuur.py` bewaakt dat).
JR en DR zijn proxy's; formeel gebruik is uitgesloten (#296).

### Het dashboard is een map, geen bestand

`app/_dashboard/` is de enige map in `app/`: het dashboard telt te veel
tabellen om in één bestand te blijven (#301). De page
(`app/pages/dashboard.py`) orkestreert alleen — laden en jaarselectie in
`_dashboard.data`, de weergave per tab in `_dashboard.tab_*`, de gedeelde
grafiekhelpers in `_dashboard.grafieken`. Tegenover de losse modules hierboven
is dit een echt pakket (`from _dashboard import data`), omdat de tabs elkaar
niet importeren maar wel één vocabulary delen.

Een getoonde tabel of grafiek moet reproduceerbaar zijn: de volgorde van
gelijke tellingen wordt daarom overal via `grafieken.sorteer_aantal` bepaald
(aantal aflopend, label oplopend). `group_by` legt zelf geen stabiele
rijvolgorde vast, dus zonder die tweede sleutel wisselde de volgorde per run —
en in een top-N ook welke regels zichtbaar waren.

## Kwaliteitspoort zit in `run_star`, niet in bouwstenen

`pipeline.run_star()` is het enige invoerpunt dat kwaliteitscontrole uitvoert en
`quality.json` schrijft. De afzonderlijke bouwstenen
(`stack_prepared()`, `build_star()`) zijn herbruikbaar en geven geen
kwaliteitsoordeel. Een script of notebook dat deze functies direct aanroept,
rekent verder op ongevalideerde data (zie de docstrings van beide functies).

`run_star` publiceert ook: de ster komt via een staging-map in `datamodel/`,
alleen als de poort dat toelaat (`publicatie.py`, #363). Een afnemer leest
haar met `publicatie.lees_ster`, dat een ster met status `fail` standaard
weigert. De app gebruikt de override: Home moet een fout juist kunnen tonen.

## Privacygrens bij decode

`identiteit.py` (identifierdomeinen, salt, `_persoon_id`) hoort bij de
brondatafase, niet bij de sterbouw: `decode_frames` vervangt de identifiers door
het pseudoniem (#173). De sterbouw krijgt alleen `_persoon_id` en kent geen
BSN, onderwijsnummer of PGN; `stack_prepared` weigert brondata waarin ze nog
staan (van vóór v4.0.0).

## Sterbouw per domein

`transform.py` orkestreert alleen; de analysetabellen worden per domein
gebouwd (#198):

| Module | Verantwoordelijkheid |
|---|---|
| `perioden.py` | periodesleutel, -begin en -einde, studiejaar, koppeling van detailrijen aan hun periode |
| `inschrijvingen.py` | de centrale inschrijvingstabel: ISP-perioden met PER/ISG/VLP/ISE/DIP/GEO, aangevuld met TBGI |
| `details.py` | detailtabellen (BPV, KZD/AMO, GEO, bekostiging) en hun aggregaten per periode |
| `opleidingsniveau.py` | niveau-aanvulling bron → CREBO → S-BB |
| `schooljaar.py` | de schooljaar-grain: peildatum, hoofdinschrijving, JR/DR/Entree |

Een module gebruikt van een andere module alleen publieke namen; een private
naam (`_…`) is geen contract. `tests/test_architectuur.py` bewaakt dat voor
`src/` en `app/`.

## Quality leest de ster onafhankelijk

`quality.py` beoordeelt de output van de sterbouw (`transform.py` en de
domeinmodules hieronder, `schooljaar.py`, `star.py`, `enrich.py`), maar mag die lagen niet importeren,
ook niet via een tussenmodule: een kwaliteitscontrole die afhangt van de code
die ze controleert, kan een fout in die code niet onafhankelijk signaleren.

Kolomnamen, codes en grains die zowel de sterbouw (schrijft ze) als
`quality.py` (leest ze) moeten kennen, staan daarom in afhankelijkheidsloze
modules die beide importeren: `contracts.py` (bron- en koppelstatuscodes,
periodesleutel, business key per detailfeit, schooljaar-grain, DUO-kalender;
#365) en `niveau.py` (herkomst-codes van `_niveau_herkomst`, #253).
`tests/test_architectuur.py` volgt de imports van `quality.py` transitief en
faalt zodra er een pad naar de sterbouw ontstaat.
