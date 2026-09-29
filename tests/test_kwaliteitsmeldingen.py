"""Meldingen uit ``quality.json`` met ernst, voor dashboard én statustelling (#202).

Eén functie bepaalt per bevinding de ernst; de ``summary`` in ``quality.json``
telt precies die meldingen. Zo kunnen UI en status niet uit elkaar lopen.
"""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mbo_bekostiging_bestanden.pipeline import run_star
from mbo_bekostiging_bestanden.quality import kwaliteitsmeldingen

# AppTest.from_file lost een relatief pad op t.o.v. de working directory,
# niet t.o.v. dit testbestand (versiegevoelig sinds streamlit 1.64, #262).
_APP_PAGES = Path(__file__).parents[1] / "app" / "pages"

RAPPORT = {
    "deliveries": [
        {"levering": "L1", "warnings": ["SLR ontbreekt"], "errors": ["kapot"]},
        {"levering": "L2", "warnings": [], "errors": []},
    ],
    "star": {
        "orphaned_facts": {
            "fact_bpv": {
                "total_rows": 4,
                "orphaned_rows": 2,
                "orphaned_pct": 0.5,
                "explained_rows": 0,
                "explanation": None,
            },
            "fact_bekostiging_diploma": {
                "total_rows": 1,
                "orphaned_rows": 1,
                "orphaned_pct": 1.0,
                "explained_rows": 1,
                "explanation": "los van inschrijvingen",
            },
        },
        "key_duplicates": {},
        "niveau_issues": {"unknown_code": 0, "sbb_without_level": 0, "total": 0},
        "overlapping_deliveries": [],
        "join_keuzes": [
            {
                "koppeling": "DIP",
                "sleutel": "k",
                "meervoudige_sleutels": 1,
                "weggelaten_rijen": 1,
            }
        ],
        "leveringen_zonder_schooljaar": [],
        "canonicalisatie": {"vervangen_inschrijvingen": 0},
    },
}


def _per_ernst(meldingen) -> dict[str, list[str]]:
    uit: dict[str, list[str]] = {}
    for m in meldingen:
        uit.setdefault(m.ernst, []).append(f"{m.bron}: {m.tekst}")
    return uit


def test_meldingen_krijgen_ernst_en_bron():
    per_ernst = _per_ernst(kwaliteitsmeldingen(RAPPORT))
    assert any(t.startswith("L1: kapot") for t in per_ernst["error"])
    assert any("fact_bpv" in t for t in per_ernst["error"])
    assert any(t.startswith("L1: SLR") for t in per_ernst["warning"])
    assert any("DIP" in t for t in per_ernst["warning"])
    assert any("los van inschrijvingen" in t for t in per_ernst["info"])


def test_summary_telt_precies_de_meldingen(demo_prepared, tmp_path):
    prepared, dirs = demo_prepared
    run_star(dirs, tmp_path, relative_to=prepared)
    rapport = json.loads((tmp_path / "quality.json").read_text(encoding="utf-8"))
    per_ernst = _per_ernst(kwaliteitsmeldingen(rapport))
    assert rapport["summary"]["total_errors"] == len(per_ernst.get("error", []))
    assert rapport["summary"]["total_warnings"] == len(per_ernst.get("warning", []))


@pytest.fixture(scope="module")
def demo_star_dir(demo_prepared, tmp_path_factory):
    prepared, dirs = demo_prepared
    doel = tmp_path_factory.mktemp("star")
    run_star(dirs, doel, relative_to=prepared)
    return doel


def test_dashboard_toont_kwaliteitsstatus(demo_star_dir):
    app = AppTest.from_file(str(_APP_PAGES / "dashboard.py"), default_timeout=60)
    app.session_state["resultaten_dir"] = demo_star_dir
    app.run()
    assert not app.exception
    teksten = [w.value for w in app.warning]
    assert any("Kwaliteitsstatus: warn" in t for t in teksten)


def test_resultaten_toont_brondata_uit_schijf_fallback_zonder_sessie(
    demo_prepared, monkeypatch
):
    """Verse sessie zonder ``prepared_dirs``: Brondata-sectie valt terug op
    een scan van ``prepared_dir()`` op schijf, net als het analysemodel via
    ``vind_star_dir`` (#263)."""
    import _utils

    basis, _ = demo_prepared
    monkeypatch.setattr(_utils, "prepared_dir", lambda: basis)

    app = AppTest.from_file("app/pages/resultaten.py", default_timeout=60)
    app.run()

    assert not app.exception
    koppen = [h.value for h in app.subheader]
    assert any(k.startswith("Brondata per levering") for k in koppen)


def test_resultaten_toont_beide_lagen_zonder_pii_in_preview(
    demo_prepared, demo_star_dir
):
    """Brondata en analysemodel zijn gelijkwaardige secties; de preview toont
    standaard geen persoonsgegevens (#213)."""
    from mbo_bekostiging_bestanden.pii import detect_pii_columns

    _, dirs = demo_prepared
    app = AppTest.from_file(str(_APP_PAGES / "resultaten.py"), default_timeout=60)
    app.session_state["resultaten_dir"] = demo_star_dir
    app.session_state["prepared_dirs"] = [str(d) for d in dirs]
    app.run()
    assert not app.exception
    koppen = [h.value for h in app.subheader]
    assert any(k.startswith("Analysemodel") for k in koppen)
    assert any(k.startswith("Brondata per levering") for k in koppen)
    for tabel in app.dataframe:
        assert detect_pii_columns(list(tabel.value.columns)) == []


def test_verouderde_kolommen_staan_als_info_in_quality_json(demo_star):
    """Release N van #201: afnemers zien welke kolommen verdwijnen, zonder dat
    de status verandert (geen warning)."""
    from mbo_bekostiging_bestanden.quality import ERNST_INFO, compile_quality_report

    rapport = compile_quality_report(demo_star)
    verouderd = rapport["star"]["verouderde_kolommen"]
    assert "_actief_1_oktober" in verouderd["fact_inschrijving"]
    assert "fact_inschrijving_schooljaar" not in verouderd

    [melding] = [
        m for m in kwaliteitsmeldingen(rapport) if "verouderd" in m.tekst.lower()
    ]
    assert melding.ernst == ERNST_INFO
    assert "fact_inschrijving_schooljaar" in melding.tekst


def test_resultaten_filtert_detailfeit_op_koppelstatus(demo_star_dir):
    """Rijen die op de eerste periode terugvielen, apart te bekijken (#121)."""
    app = AppTest.from_file(str(_APP_PAGES / "resultaten.py"), default_timeout=60)
    app.session_state["resultaten_dir"] = demo_star_dir
    app.run()
    [tabelkeuze] = [s for s in app.selectbox if "fact_bpv" in s.options]
    tabelkeuze.select("fact_bpv").run()

    [filter_] = [m for m in app.multiselect if m.label == "Koppelstatus"]
    filter_.select("binnen_periode").run()

    assert not app.exception
    [tabel] = [t for t in app.dataframe if "_periode_koppel_status" in t.value.columns]
    assert set(tabel.value["_periode_koppel_status"]) == {"binnen_periode"}
