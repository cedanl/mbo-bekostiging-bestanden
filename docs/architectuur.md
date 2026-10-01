# Architectuur

## Grens presentatie–transformatie

`src/mbo_bekostiging_bestanden/` is de kernpackage: ingest, decode, validate,
transform, enrich en star. Alles daarin is Streamlit-onafhankelijk en
publiek herbruikbaar door andere repos die op de output voortbouwen.

`app/` bevat de Streamlit-app zelf én de presentatielogica die alleen de app
gebruikt — code die niet over de kern gaat, maar over hoe de kern getoond
wordt. Herkenbaar aan een onderstrepingsprefix (`_utils.py`, `_chart_docs.py`,
`_tabel_docs.py`, `_indicatoren.py`) en geïmporteerd via `pythonpath = ["app"]`
(`pyproject.toml`), dus als platte module (`from _indicatoren import ...`),
niet via het pakket.

**Vuistregel:** een module die alleen door `app/pages/*.py` wordt
geïmporteerd, hoort in `app/`, ook als de logica zelf geen Streamlit
aanroept. `indicatoren.py` verhuisde daarom naar `app/_indicatoren.py`
(#253) — de indicatorberekeningen (JR/DR-normen, oordeel, entree) dienen
uitsluitend het dashboard.

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

## Sterbouw per domein

`transform.py` orkestreert alleen; de analysetabellen worden per domein
gebouwd (#198):

| Module | Verantwoordelijkheid |
|---|---|
| `identiteit.py` | identifierdomeinen, salt, `_persoon_id` (pseudonimisering) |
| `perioden.py` | periodesleutel, -begin en -einde, studiejaar, koppeling van detailrijen aan hun periode |
| `inschrijvingen.py` | de centrale inschrijvingstabel: ISP-perioden met PER/ISG/VLP/ISE/DIP/GEO, aangevuld met TBGI |
| `details.py` | detailtabellen (BPV, KZD/AMO, GEO, bekostiging) en hun aggregaten per periode |
| `opleidingsniveau.py` | niveau-aanvulling bron → CREBO → S-BB |
| `periodevlaggen.py` | jaargebonden vlaggen op periode-grain (legacy, verdwijnt in v4.0.0, #201) |
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
