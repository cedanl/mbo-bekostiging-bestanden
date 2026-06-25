"""Tests voor generieke multi-record CSV ingest (TDD)."""

from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.ingest import read_multi_record_csv

DEMO_H15 = Path("data/01-raw/demo/h15")
RO_27DV = DEMO_H15 / "RO_27DV_20240731_20260324.csv"


def test_read_multi_record_csv_parses_vlp_brin():
    """Generieke functie leest BRIN correct uit VLP — gedragstest."""
    result = read_multi_record_csv(RO_27DV, "ro")
    assert result["VLP"]["BRIN"][0] == "27DV"


def test_read_multi_record_csv_kolomnamen_komen_uit_schema():
    """Kolomaantal klopt met het schema — kolomnamen hardcoden verifieert niks over parsering."""
    result = read_multi_record_csv(RO_27DV, "ro")
    from mbo_bekostiging_bestanden.metadata import load_schema
    schema = load_schema("ro")
    assert result["VLP"].width == len(schema["VLP"]["fields"])
    assert result["ISG"].width == len(schema["ISG"]["fields"])


def test_read_multi_record_csv_file_not_found():
    with pytest.raises(FileNotFoundError):
        read_multi_record_csv("bestaat_niet.csv", "ro")


def test_read_multi_record_csv_unknown_schema_raises():
    with pytest.raises(FileNotFoundError):
        read_multi_record_csv(RO_27DV, "bestaat_niet")
