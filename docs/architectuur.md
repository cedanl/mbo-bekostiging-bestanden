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

## Quality leest de ster onafhankelijk

`quality.py` beoordeelt de output van `transform.py`/`star.py`, maar mag die
lagen niet importeren: een kwaliteitscontrole die afhangt van de code die ze
controleert, kan een fout in die code niet onafhankelijk signaleren.

Kolomwaarden die zowel `transform.py` (schrijft ze) als `quality.py` (leest
ze) moeten kennen — zoals de herkomst-codes van de kolom `_niveau_herkomst`
— staan daarom in een eigen, afhankelijkheidsloze module (`niveau.py`, #253)
die beide importeren, in plaats van dat `quality.py` rechtstreeks uit
`transform.py` importeert.
