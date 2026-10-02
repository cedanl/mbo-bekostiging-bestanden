"""Brondata en analysemodel zijn twee producten, elk met een eigen status (#285).

De app toonde beide als tabellenlijst; alleen het analysemodel had een status
(in het dashboard). Nu draagt ook elk leveringsrapport van de brondata zijn
status, en zetten de pagina's Werkbare data en Analysemodel bij elk product de
map en de status.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mbo_bekostiging_bestanden.pipeline import run_star
from mbo_bekostiging_bestanden.quality import QualityReport, kwaliteitsstatus

_PAGINAS = Path(__file__).parents[1] / "app" / "pages"


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
def sessie(demo_prepared, tmp_path_factory) -> dict[str, object]:
    prepared, dirs = demo_prepared
    ster = tmp_path_factory.mktemp("ster")
    run_star(dirs, ster, relative_to=prepared)
    return {
        "prepared_dirs": [str(d) for d in dirs],
        "resultaten_dir": str(ster),
        "star_pad": str(ster),
    }


def _bijschriften(pagina: str, sessie: dict[str, object]) -> list[str]:
    app = AppTest.from_file(str(_PAGINAS / pagina), default_timeout=120)
    for sleutel, waarde in sessie.items():
        app.session_state[sleutel] = waarde
    app.run()
    assert not app.exception
    return [c.value for c in app.caption]


def test_analysemodel_toont_map_en_status(sessie):
    bijschriften = _bijschriften("analysemodel.py", sessie)
    assert any("Analysemodel" in b and "status" in b for b in bijschriften)
    assert not any(b.startswith("Brondata") for b in bijschriften)


def test_werkbare_data_toont_map_en_status(sessie):
    bijschriften = _bijschriften("werkbare_data.py", sessie)
    assert any("Brondata" in b and "pass" in b for b in bijschriften)
    assert not any(b.startswith("Analysemodel") for b in bijschriften)
