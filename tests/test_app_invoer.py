"""Bestanden selecteren naast de vaste invoermap (#436).

Een selectie wordt buiten de repo bewaard en is alleen de bron voor de
verwerking; deze helpers houden die werkmap gelijk aan de gekozen bestanden.
"""

from pathlib import Path

import _invoer
import pytest


def _selectie(*namen_inhoud: tuple[str, bytes]) -> list[tuple[str, bytes]]:
    return list(namen_inhoud)


def test_schrijft_gekozen_bestanden_in_de_selectiemap(tmp_path):
    doel = _invoer.synchroniseer_selectie(_selectie(("RO_a.csv", b"abc")), tmp_path)

    assert doel == tmp_path / _invoer.SELECTIEMAP
    assert (doel / "RO_a.csv").read_bytes() == b"abc"


def test_verwijdert_bestanden_die_niet_meer_gekozen_zijn(tmp_path):
    """Anders belandt een eerder gekozen bestand ongemerkt in de verwerking."""
    _invoer.synchroniseer_selectie(
        _selectie(("RO_a.csv", b"1"), ("RO_b.csv", b"2")), tmp_path
    )
    doel = _invoer.synchroniseer_selectie(_selectie(("RO_b.csv", b"2")), tmp_path)

    assert sorted(p.name for p in doel.iterdir()) == ["RO_b.csv"]


def test_herschrijft_een_gewijzigd_bestand_met_dezelfde_naam(tmp_path):
    _invoer.synchroniseer_selectie(_selectie(("RO_a.csv", b"oud")), tmp_path)
    doel = _invoer.synchroniseer_selectie(_selectie(("RO_a.csv", b"nieuw!")), tmp_path)

    assert (doel / "RO_a.csv").read_bytes() == b"nieuw!"


def test_ongewijzigde_selectie_schrijft_niet_opnieuw(tmp_path):
    """Grote DUO-bestanden: een rerun van Streamlit mag ze niet steeds wegschrijven."""
    doel = _invoer.synchroniseer_selectie(_selectie(("RO_a.csv", b"abc")), tmp_path)
    mtime = (doel / "RO_a.csv").stat().st_mtime_ns

    _invoer.synchroniseer_selectie(_selectie(("RO_a.csv", b"abc")), tmp_path)

    assert (doel / "RO_a.csv").stat().st_mtime_ns == mtime


@pytest.mark.parametrize(
    "naam", ["../ontsnapt.csv", "/abs/ontsnapt.csv", "a/../../x", "..", "a/.."]
)
def test_bestandsnaam_kan_de_selectiemap_niet_verlaten(tmp_path, naam):
    doel = _invoer.synchroniseer_selectie(_selectie((naam, b"x")), tmp_path)

    gevonden = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert all(p.is_relative_to(doel) for p in gevonden)
    assert not (tmp_path.parent / "ontsnapt.csv").exists()


def test_lege_selectie_laat_een_lege_map_achter(tmp_path):
    _invoer.synchroniseer_selectie(_selectie(("RO_a.csv", b"1")), tmp_path)
    doel = _invoer.synchroniseer_selectie([], tmp_path)

    assert list(doel.iterdir()) == []
    assert isinstance(doel, Path)
