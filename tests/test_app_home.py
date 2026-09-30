"""Home: brondata en analysemodel zijn aparte stappen (#264, #285).

De ster is de dure stap; wie alleen brondata wil, of de ster opnieuw wil
bouwen zonder alle ruwe bestanden opnieuw te verwerken, kan dat los doen —
zoals ``mbo verwerk`` en ``mbo star`` in de CLI.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import mbo_bekostiging_bestanden.pipeline as pipeline

# Absoluut pad: AppTest lost relatieve paden versiegevoelig op (#262).
_HOME = str(Path(__file__).parents[1] / "app" / "pages" / "home.py")
_KERNTABEL = Path("datamodel") / "fact_inschrijving.parquet"


@pytest.fixture
def paden(tmp_path, monkeypatch):
    """Demo-invoer, lege prepared- en output-map."""
    import _utils

    prepared, output = tmp_path / "prepared", tmp_path / "output"
    monkeypatch.setattr(_utils, "prepared_dir", lambda: prepared)
    monkeypatch.setattr(_utils, "output_dir", lambda: output)
    return prepared, output / "star"


def _knop(app: AppTest, label: str):
    [knop] = [b for b in app.button if b.label == label]
    return knop


def _home() -> AppTest:
    app = AppTest.from_file(_HOME, default_timeout=120)
    app.run()
    assert not app.exception
    return app


def test_analysemodel_kan_pas_na_brondata(paden):
    app = _home()
    assert not _knop(app, "Verwerk bestanden").disabled
    assert _knop(app, "Bouw analysemodel").disabled


def test_verwerk_bestanden_bouwt_geen_ster(paden):
    prepared, star = paden
    app = _home()
    _knop(app, "Verwerk bestanden").click().run()

    assert not app.exception
    assert any(prepared.rglob("*.parquet"))
    assert not (star / _KERNTABEL).exists()
    assert not _knop(app, "Bouw analysemodel").disabled


def test_analysemodel_uit_brondata_op_schijf_zonder_herverwerking(
    demo_prepared, paden, monkeypatch
):
    """Verse sessie, brondata al op schijf: alleen de ster wordt gebouwd."""
    import _utils

    _, star = paden
    monkeypatch.setattr(_utils, "prepared_dir", lambda: demo_prepared[0])

    def niet_herverwerken(*_args, **_kwargs):
        raise AssertionError("ruwe bestanden opnieuw verwerkt")

    monkeypatch.setattr(pipeline, "run_auto_pipeline", niet_herverwerken)

    app = _home()
    _knop(app, "Bouw analysemodel").click().run()

    assert not app.exception
    assert (star / _KERNTABEL).exists()
    assert any("analysemodel klaar" in s.value.lower() for s in app.success)


def test_mislukt_bestand_laat_geen_oude_brondata_achter(paden, monkeypatch):
    """Anders belandt een eerdere versie ongemerkt in het analysemodel."""
    prepared, _ = paden
    oud = prepared / "h15" / "RO_21CY_20250730_20250731" / "oud.parquet"
    oud.parent.mkdir(parents=True)  # brondata van een eerdere, geslaagde run
    oud.write_bytes(b"")

    def kapot(raw_file, target, *_args, **_kwargs):
        (Path(target) / "half.parquet").write_bytes(b"")
        raise ValueError("kapot bestand")

    monkeypatch.setattr(pipeline, "run_auto_pipeline", kapot)
    app = _home()
    _knop(app, "Verwerk bestanden").click().run()

    assert not app.exception
    assert not any(prepared.rglob("*.parquet"))
    assert _knop(app, "Bouw analysemodel").disabled


def test_home_toont_fout_i_p_v_succes_bij_quality_fail(
    prepared_met_fout, paden, monkeypatch
):
    """Een ster met status ``fail`` is geen 'klaar' (#290)."""
    import _utils

    monkeypatch.setattr(_utils, "prepared_dir", lambda: prepared_met_fout[0])
    app = _home()
    _knop(app, "Bouw analysemodel").click().run()

    assert not app.exception
    assert not any("analysemodel klaar" in s.value.lower() for s in app.success)
    assert any("kwaliteitsfout" in e.value for e in app.error)


def test_home_toont_succes_bij_schone_run(demo_prepared, paden, monkeypatch):
    import _utils

    monkeypatch.setattr(_utils, "prepared_dir", lambda: demo_prepared[0])
    app = _home()
    _knop(app, "Bouw analysemodel").click().run()

    assert any("analysemodel klaar" in s.value.lower() for s in app.success)
    assert not any("kwaliteitsfout" in e.value for e in app.error)
