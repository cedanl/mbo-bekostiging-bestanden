"""Alle tabellen van een pagina in één keer downloaden (zip met CSV's)."""

import io
import zipfile
from pathlib import Path

import polars as pl
import pytest
from _tabellen import maak_zip_met_csvs


@pytest.fixture
def tabellen(tmp_path) -> dict[str, Path]:
    persoon = tmp_path / "persoon.parquet"
    pl.DataFrame(
        {"_persoon_id": ["a", "b"], "Opleidingcode": ["1", "2"]}
    ).write_parquet(persoon)
    feit = tmp_path / "feit.parquet"
    pl.DataFrame({"x": [1, 2, 3]}).write_parquet(feit)
    return {"lev1 / persoon": persoon, "feit": feit}


def _lees(data: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n).decode() for n in z.namelist()}


def test_zip_bevat_een_csv_per_tabel(tabellen):
    inhoud = _lees(maak_zip_met_csvs(tabellen, verberg_pii=False))

    assert sorted(inhoud) == ["feit.csv", "lev1/persoon.csv"]
    assert inhoud["feit.csv"].splitlines() == ["x", "1", "2", "3"]


def test_zip_verbergt_persoonsgegevens_op_verzoek(tabellen):
    verborgen = _lees(maak_zip_met_csvs(tabellen, verberg_pii=True))
    volledig = _lees(maak_zip_met_csvs(tabellen, verberg_pii=False))

    assert "_persoon_id" not in verborgen["lev1/persoon.csv"]
    assert "Opleidingcode" in verborgen["lev1/persoon.csv"]
    assert "_persoon_id" in volledig["lev1/persoon.csv"]


def test_zip_van_geen_tabellen_is_een_lege_zip():
    assert _lees(maak_zip_met_csvs({}, verberg_pii=True)) == {}
