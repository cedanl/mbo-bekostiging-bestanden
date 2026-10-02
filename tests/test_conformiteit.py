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
    conformiteit = rapport["conformiteit"]
    assert "pve_versie" in conformiteit
    assert "pve_bron_integriteit" in conformiteit
    assert "pve_inhoudelijke_conformiteit" in conformiteit
    assert conformiteit["privacyprofiel"] == "gepseudonimiseerd"
    assert conformiteit["pgn_stabiliteit"] == "onbekend"
    # Indicatoren bevat per proxy-indicator status en afwijkingen (#369)
    assert "JR" in conformiteit["indicatoren"]
    assert "DR" in conformiteit["indicatoren"]
    assert conformiteit["indicatoren"]["JR"]["status"] == "proxy"


def test_indicatorstatus_komt_uit_een_constante():
    assert compile_quality_report({})["conformiteit"]["indicatoren"] == (
        INDICATOREN_STATUS
    )


def test_formeel_gebruik_van_de_proxys_is_uitgesloten():
    """Besluit #296 (optie B): geen officiële studiesucces-laag; een afnemer
    leest uit ``quality.json`` dat JR/DR niet voor formele verantwoording zijn."""
    for naam in ("JR", "DR"):
        assert INDICATOREN_STATUS[naam]["formeel_gebruik"] == "uitgesloten"


def test_dashboard_meldt_dat_formeel_gebruik_uitgesloten_is(ster_dir):
    app = AppTest.from_file(_DASHBOARD, default_timeout=120)
    app.session_state["resultaten_dir"] = ster_dir
    app.run()

    assert any("formeel gebruik uitgesloten" in c.value for c in app.caption)


def test_brondata_rapport_heeft_het_profiel_brondata():
    rapport = QualityReport(levering="L", schema_type="ro")
    assert rapport.as_dict()["privacyprofiel"] == "brondata"


def test_dashboard_toont_de_proxystatus(ster_dir):
    app = AppTest.from_file(_DASHBOARD, default_timeout=120)
    app.session_state["resultaten_dir"] = ster_dir
    app.run()

    assert not app.exception
    assert any("proxy" in c.value for c in app.caption)


def test_dashboard_noemt_jr_dr_en_oordeel_proxy(ster_dir):
    """Geen kop, kolom of tabel die als formele uitkomst gelezen kan worden (#297)."""
    app = AppTest.from_file(_DASHBOARD, default_timeout=120)
    app.session_state["resultaten_dir"] = ster_dir
    app.run()

    koppen = [h.value for h in app.subheader]
    assert any("JR-proxy" in k for k in koppen)
    assert any("DR-proxy" in k for k in koppen)
    assert any(k.startswith("Proxy-oordeel") for k in koppen)
    assert not any(k.startswith("Berekend oordeel") for k in koppen)
    kolommen = {c for tabel in app.dataframe for c in tabel.value.columns}
    assert {"JR-proxy (%)", "Proxy-oordeel"} <= kolommen
    assert "Percentage" not in kolommen
