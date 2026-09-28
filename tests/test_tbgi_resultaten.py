"""Synthetische TBG-i met BPV's en signalen is zichtbaar in Resultaten (#161, #166).

End-to-end: XML → ``run_auto_pipeline`` → brondata → Resultaten-pagina. De
TBG-i-tabellen worden via ``tbgi_schema.toml`` herkend, niet via bestandsnamen.
"""

import shutil
from pathlib import Path

import polars as pl
import pytest
from streamlit.testing.v1 import AppTest

from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline

XML = Path(__file__).parent / "fixtures" / "tbgi_meervoudig.xml"
SECTIE = "tabel_Brondata per levering — TBG-i"


@pytest.fixture(scope="module")
def prepared(tmp_path_factory) -> Path:
    bron = tmp_path_factory.mktemp("raw") / "TBGI_25LX_2027_20251124.XML"
    shutil.copy(XML, bron)
    doel = tmp_path_factory.mktemp("prepared") / bron.stem
    run_auto_pipeline(bron, doel)
    return doel


def test_brondata_bevat_bpv_en_signalen(prepared):
    assert pl.read_parquet(prepared / "BekostigingsrelevanteBPV.parquet").height == 2
    # Eén rij per parameter: signaal A1 heeft er twee, A2 geen.
    assert pl.read_parquet(prepared / "Signaal.parquet").height == 3


@pytest.mark.parametrize(
    ("tabel", "rijen"), [("BekostigingsrelevanteBPV", 2), ("Signaal", 3)]
)
def test_resultaten_toont_tbgi_tabel_met_rijen(prepared, tabel, rijen):
    app = AppTest.from_file("app/pages/resultaten.py", default_timeout=60)
    app.session_state["prepared_dirs"] = [str(prepared)]
    app.run()
    keuze = app.selectbox(key=SECTIE)
    naam = f"{prepared.name} / {tabel}"
    assert naam in keuze.options
    keuze.set_value(naam).run()
    assert not app.exception
    # De TBG-i-sectie staat als laatste op de pagina.
    assert app.dataframe[-1].value.shape[0] == rijen
