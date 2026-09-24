"""Tests voor de gedeelde app-helpers in ``app/_utils.py`` (issues #88, #95)."""

from pathlib import Path

import _utils
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "pad_functie", [_utils.raw_dir, _utils.prepared_dir, _utils.output_dir]
)
def test_datapaden_zijn_absoluut_en_werkmap_onafhankelijk(
    pad_functie, tmp_path, monkeypatch
):
    verwacht = pad_functie()
    monkeypatch.chdir(tmp_path)
    assert pad_functie() == verwacht
    assert verwacht.is_absolute()
    assert verwacht.is_relative_to(PROJECT_ROOT)


def test_star_dir_ligt_onder_output_dir():
    assert _utils.star_dir().parent == _utils.output_dir()


def _maak_star(pad: Path) -> Path:
    datamodel = pad / "datamodel"
    datamodel.mkdir(parents=True)
    (datamodel / "fact_inschrijving.parquet").touch()
    return pad


def test_vind_star_dir_kiest_eerste_sessiepad_met_datamodel(tmp_path, monkeypatch):
    monkeypatch.setattr(_utils, "star_dir", lambda: _maak_star(tmp_path / "schijf"))
    sessie = {
        "resultaten_dir": str(tmp_path / "leeg"),
        "star_pad": str(_maak_star(tmp_path / "sessie")),
    }
    assert _utils.vind_star_dir(sessie) == tmp_path / "sessie"


def test_vind_star_dir_valt_terug_op_schijf_zonder_sessie(tmp_path, monkeypatch):
    """Dieplink: een verse sessie vindt het eerder gebouwde star schema op schijf."""
    schijf = _maak_star(tmp_path / "schijf")
    monkeypatch.setattr(_utils, "star_dir", lambda: schijf)
    assert _utils.vind_star_dir({}) == schijf


def test_vind_star_dir_zonder_datamodel_geeft_none(tmp_path, monkeypatch):
    monkeypatch.setattr(_utils, "star_dir", lambda: tmp_path / "bestaat_niet")
    assert _utils.vind_star_dir({"star_pad": None}) is None
