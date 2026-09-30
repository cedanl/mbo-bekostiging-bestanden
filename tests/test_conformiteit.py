"""``quality.json`` zegt wat de uitkomst betekent, niet alleen of ze klopt (#331).

Een run met status ``pass`` kan proxy-indicatoren bevatten; die schijn van
formele conformiteit stond alleen in dashboardtekst.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mbo_bekostiging_bestanden.pipeline import run_star
from mbo_bekostiging_bestanden.quality import (
    INDICATOREN_STATUS,
    QualityReport,
    compile_quality_report,
)

_DASHBOARD = str(Path(__file__).parents[1] / "app" / "pages" / "dashboard.py")


@pytest.fixture(scope="module")
def ster_dir(demo_prepared, tmp_path_factory) -> Path:
    prepared, dirs = demo_prepared
    doel = tmp_path_factory.mktemp("star")
    run_star(dirs, doel, relative_to=prepared)
    return doel


def test_ster_rapport_bevat_conformiteit():
    rapport = compile_quality_report({})
    assert rapport["conformiteit"] == {
        "pve_schema": "niet_beoordeeld",
        "indicatoren": "proxy",
        "privacyprofiel": "gepseudonimiseerd",
    }


def test_indicatorstatus_komt_uit_een_constante():
    assert compile_quality_report({})["conformiteit"]["indicatoren"] == (
        INDICATOREN_STATUS
    )


def test_brondata_rapport_heeft_het_profiel_brondata():
    rapport = QualityReport(levering="L", schema_type="ro")
    assert rapport.as_dict()["privacyprofiel"] == "brondata"


def test_dashboard_toont_de_proxystatus(ster_dir):
    app = AppTest.from_file(_DASHBOARD, default_timeout=120)
    app.session_state["resultaten_dir"] = ster_dir
    app.run()

    assert not app.exception
    assert any("proxy" in c.value for c in app.caption)
