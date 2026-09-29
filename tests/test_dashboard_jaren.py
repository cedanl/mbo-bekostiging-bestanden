"""Dashboard met alleen TBG-i: het jaar van de teldatum is kiesbaar (#240).

De TBGI-pseudo-periode begint op ``DatumInschrijving`` (demo: 2023), maar de
inschrijving telt in het schooljaar van haar ``Teldatum`` (2025). Een selector
op het periodejaar filterde de schooljaar- en bekostigingsfeiten leeg.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline, run_star

# Absoluut pad: AppTest lost relatieve paden versiegevoelig op (#262).
_DASHBOARD = str(Path(__file__).parents[1] / "app" / "pages" / "dashboard.py")
_TBGI = Path("data/01-raw/demo/h16")


@pytest.fixture(scope="module")
def tbgi_star_dir(tmp_path_factory) -> Path:
    prepared = tmp_path_factory.mktemp("prepared")
    dirs = []
    for bron in sorted(_TBGI.iterdir()):
        run_auto_pipeline(bron, prepared / "h16" / bron.stem)
        dirs.append(prepared / "h16" / bron.stem)
    doel = tmp_path_factory.mktemp("star")
    run_star(dirs, doel, relative_to=prepared)
    return doel


@pytest.fixture(scope="module")
def dashboard(tbgi_star_dir) -> AppTest:
    app = AppTest.from_file(_DASHBOARD, default_timeout=120)
    app.session_state["resultaten_dir"] = tbgi_star_dir
    app.run()
    assert not app.exception
    return app


def _metric(app: AppTest, label: str) -> int:
    [waarde] = [m.value for m in app.metric if m.label == label]
    return int(waarde.replace(",", ""))


def test_teldatumjaar_is_kiesbaar(dashboard):
    [selector] = [p for p in dashboard.sidebar.button_group if p.label == "Schooljaar"]
    assert 2025 in selector.options or "2025" in [str(o) for o in selector.options]


def test_tbgi_only_metrics_zijn_niet_nul(dashboard):
    assert _metric(dashboard, "Studenten op 1 oktober") > 0
    assert _metric(dashboard, "Actief op 1-oktober") > 0
