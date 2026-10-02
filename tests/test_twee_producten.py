"""Brondata en analysemodel zijn twee producten, elk met een eigen status (#285).

De app toonde beide als tabellenlijst; alleen het analysemodel had een status
(in het dashboard). Nu draagt ook elk leveringsrapport van de brondata zijn
status, en zet Resultaten bij elk product de map en de status.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mbo_bekostiging_bestanden.pipeline import run_star
from mbo_bekostiging_bestanden.quality import QualityReport, kwaliteitsstatus

_RESULTATEN = str(Path(__file__).parents[1] / "app" / "pages" / "resultaten.py")


@pytest.mark.parametrize(
    ("errors", "warnings", "status"),
    [(0, 0, "pass"), (0, 2, "warn"), (1, 0, "fail"), (1, 3, "fail")],
)
def test_kwaliteitsstatus(errors, warnings, status):
    assert kwaliteitsstatus(errors, warnings) == status


def test_leveringsrapport_draagt_zijn_status():
    rapport = QualityReport(levering="L", schema_type="ro", warnings=["w"])
    assert rapport.as_dict()["status"] == "warn"


def test_brondata_is_gepseudonimiseerd():
    """Sinds #173 bevat ook de brondata geen identifiers meer."""
    rapport = QualityReport(levering="L", schema_type="ro")
    assert rapport.as_dict()["privacyprofiel"] == "gepseudonimiseerd"


@pytest.fixture(scope="module")
def pagina(demo_prepared, tmp_path_factory) -> AppTest:
    prepared, dirs = demo_prepared
    ster = tmp_path_factory.mktemp("ster")
    run_star(dirs, ster, relative_to=prepared)
    app = AppTest.from_file(_RESULTATEN, default_timeout=120)
    app.session_state["prepared_dirs"] = [str(d) for d in dirs]
    app.session_state["resultaten_dir"] = str(ster)
    app.session_state["star_pad"] = str(ster)
    app.run()
    assert not app.exception
    return app


def test_resultaten_toont_per_product_de_status(pagina):
    bijschriften = [c.value for c in pagina.caption]
    assert any("Analysemodel" in b and "status" in b for b in bijschriften)
    assert any("Brondata" in b and "pass" in b for b in bijschriften)
