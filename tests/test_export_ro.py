"""Tests voor RO-export (TDD)."""

from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.decode import decode_ro
from mbo_bekostiging_bestanden.export import export_ro
from mbo_bekostiging_bestanden.ingest import read_ro

DEMO_H15 = Path("data/01-raw/demo/h15")
RO_27DV = DEMO_H15 / "RO_27DV_20240731_20260324.csv"


@pytest.fixture
def frames():
    return decode_ro(read_ro(RO_27DV))


# ---------------------------------------------------------------------------
# Parquet (standaard)
# ---------------------------------------------------------------------------


def test_export_ro_parquet_creates_files(frames, tmp_path):
    export_ro(frames, tmp_path)
    assert len(list(tmp_path.glob("*.parquet"))) == len(frames)


def test_export_ro_parquet_creates_output_dir(frames, tmp_path):
    target = tmp_path / "nieuw" / "pad"
    export_ro(frames, target)
    assert target.exists()


def test_export_ro_parquet_filenames_match_recordtypes(frames, tmp_path):
    export_ro(frames, tmp_path)
    written = {f.stem for f in tmp_path.glob("*.parquet")}
    assert written == set(frames.keys())


def test_export_ro_parquet_preserves_types(frames, tmp_path):
    export_ro(frames, tmp_path)
    vlp = pl.read_parquet(tmp_path / "VLP.parquet")
    assert vlp["DatumAanmaak"].dtype == pl.Date
    slr = pl.read_parquet(tmp_path / "SLR.parquet")
    assert slr["AantalPER"].dtype == pl.Int64


def test_export_ro_parquet_row_counts(frames, tmp_path):
    export_ro(frames, tmp_path)
    for rt, df in frames.items():
        written = pl.read_parquet(tmp_path / f"{rt}.parquet")
        assert written.height == df.height


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def test_export_ro_csv_creates_files(frames, tmp_path):
    export_ro(frames, tmp_path, fmt="csv")
    assert len(list(tmp_path.glob("*.csv"))) == len(frames)


def test_export_ro_csv_filenames_match_recordtypes(frames, tmp_path):
    export_ro(frames, tmp_path, fmt="csv")
    written = {f.stem for f in tmp_path.glob("*.csv")}
    assert written == set(frames.keys())


def test_export_ro_csv_readable(frames, tmp_path):
    export_ro(frames, tmp_path, fmt="csv")
    per = pl.read_csv(tmp_path / "PER.csv")
    assert per.height == frames["PER"].height
    assert "Burgerservicenummer" in per.columns


def test_export_ro_csv_row_counts(frames, tmp_path):
    export_ro(frames, tmp_path, fmt="csv")
    for rt, df in frames.items():
        written = pl.read_csv(tmp_path / f"{rt}.csv")
        assert written.height == df.height


def test_export_ro_invalid_fmt_raises(frames, tmp_path):
    with pytest.raises(ValueError, match="Onbekend formaat"):
        export_ro(frames, tmp_path, fmt="xlsx")  # type: ignore


# ---------------------------------------------------------------------------
# Geen overlap tussen formaten in dezelfde map
# ---------------------------------------------------------------------------


def test_export_ro_no_format_mixing(frames, tmp_path):
    export_ro(frames, tmp_path / "parquet", fmt="parquet")
    export_ro(frames, tmp_path / "csv", fmt="csv")
    assert not list((tmp_path / "parquet").glob("*.csv"))
    assert not list((tmp_path / "csv").glob("*.parquet"))
