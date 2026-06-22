"""Tests voor RO-export (TDD)."""

from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.decode import decode_ro
from mbo_bekostiging_bestanden.export import export_ro
from mbo_bekostiging_bestanden.ingest import read_ro

DEMO_H15 = Path("data/01-raw/demo/h15")
RO_27DV = DEMO_H15 / "RO_27DV_20240731_20260324.csv"


def test_export_ro_creates_parquet_files(tmp_path):
    frames = decode_ro(read_ro(RO_27DV))
    export_ro(frames, tmp_path)
    parquet_files = list(tmp_path.glob("*.parquet"))
    assert len(parquet_files) == len(frames)


def test_export_ro_creates_output_dir(tmp_path):
    target = tmp_path / "nieuw" / "pad"
    frames = decode_ro(read_ro(RO_27DV))
    export_ro(frames, target)
    assert target.exists()


def test_export_ro_filenames_match_recordtypes(tmp_path):
    frames = decode_ro(read_ro(RO_27DV))
    export_ro(frames, tmp_path)
    written = {f.stem for f in tmp_path.glob("*.parquet")}
    assert written == set(frames.keys())


def test_export_ro_parquet_preserves_types(tmp_path):
    frames = decode_ro(read_ro(RO_27DV))
    export_ro(frames, tmp_path)

    vlp = pl.read_parquet(tmp_path / "VLP.parquet")
    assert vlp["DatumAanmaak"].dtype == pl.Date

    slr = pl.read_parquet(tmp_path / "SLR.parquet")
    assert slr["AantalPER"].dtype == pl.Int64


def test_export_ro_parquet_row_counts(tmp_path):
    frames = decode_ro(read_ro(RO_27DV))
    export_ro(frames, tmp_path)

    for rt, df in frames.items():
        written = pl.read_parquet(tmp_path / f"{rt}.parquet")
        assert written.height == df.height, f"{rt}: rijcount verschilt na export"
