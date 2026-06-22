"""Tests voor automatische bestandstype-detectie en run_auto_pipeline (TDD)."""

from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.pipeline import detect_bestandstype, run_auto_pipeline

DEMO_H15 = Path("data/01-raw/demo/h15")
DEMO_H16 = Path("data/01-raw/demo/h16")
DEMO_H17 = Path("data/01-raw/demo/h17")
RO = DEMO_H15 / "RO_27DV_20240731_20260324.csv"
GRONDSLAG = DEMO_H17 / "GRONDSLAG_IP_MBO_27DV_20251119_2025.csv"
TBGI = DEMO_H16 / "TBGI_25LX_2027_20251124.XML"


# ---------------------------------------------------------------------------
# detect_bestandstype
# ---------------------------------------------------------------------------


def test_detect_bestandstype_ro():
    assert detect_bestandstype(RO) == "ro"


def test_detect_bestandstype_grondslag():
    assert detect_bestandstype(GRONDSLAG) == "grondslag"


def test_detect_bestandstype_tbgi():
    assert detect_bestandstype(TBGI) == "tbgi"


def test_detect_bestandstype_unknown():
    assert detect_bestandstype(Path("onbekend.csv")) is None


def test_detect_bestandstype_accepts_string():
    assert detect_bestandstype(str(RO)) == "ro"


def test_detect_bestandstype_case_insensitive():
    """Bestandsnaam in lowercase wordt ook herkend."""
    lower = Path("ro_27dv_20240731_20260324.csv")
    assert detect_bestandstype(lower) == "ro"


# ---------------------------------------------------------------------------
# run_auto_pipeline
# ---------------------------------------------------------------------------


def test_run_auto_pipeline_ro_contains_recordtypes(tmp_path):
    frames = run_auto_pipeline(RO, tmp_path)
    assert {"VLP", "PER", "ISG", "SLR"} <= frames.keys()


def test_run_auto_pipeline_grondslag_contains_recordtypes(tmp_path):
    frames = run_auto_pipeline(GRONDSLAG, tmp_path)
    assert {"VLP", "PER", "ISG", "SLR"} <= frames.keys()


def test_run_auto_pipeline_unknown_raises_value_error(tmp_path):
    with pytest.raises(ValueError, match="Onbekend bestandstype"):
        run_auto_pipeline(Path("onbekend.csv"), tmp_path)


def test_run_auto_pipeline_writes_parquet(tmp_path):
    frames = run_auto_pipeline(RO, tmp_path)
    written = {f.stem for f in tmp_path.glob("*.parquet")}
    assert written == set(frames.keys())


def test_run_auto_pipeline_matches_direct_call(tmp_path):
    """run_auto_pipeline geeft dezelfde recordtypes als de directe pipeline."""
    from mbo_bekostiging_bestanden.pipeline import run_pipeline

    frames_auto = run_auto_pipeline(RO, tmp_path / "auto")
    frames_direct = run_pipeline(RO, tmp_path / "direct")
    assert set(frames_auto.keys()) == set(frames_direct.keys())
