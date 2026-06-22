"""Tests voor generieke multi-record CSV ingest (TDD)."""

from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.ingest import read_multi_record_csv, read_ro

DEMO_H15 = Path("data/01-raw/demo/h15")
RO_27DV = DEMO_H15 / "RO_27DV_20240731_20260324.csv"


def test_read_multi_record_csv_returns_dict():
    assert isinstance(read_multi_record_csv(RO_27DV, "ro"), dict)


def test_read_multi_record_csv_parses_vlp_brin():
    """Generieke functie leest BRIN correct uit VLP — gedragstest."""
    result = read_multi_record_csv(RO_27DV, "ro")
    assert result["VLP"]["BRIN"][0] == "27DV"


def test_read_multi_record_csv_column_names_from_schema():
    """Kolomnamen komen uit het schema, niet hardcoded in de parser."""
    result = read_multi_record_csv(RO_27DV, "ro")
    assert result["VLP"].columns == [
        "Recordsoort", "BRIN", "DatumBeginPeriode", "DatumEindePeriode", "DatumAanmaak"
    ]


def test_read_multi_record_csv_file_not_found():
    with pytest.raises(FileNotFoundError):
        read_multi_record_csv("bestaat_niet.csv", "ro")


def test_read_multi_record_csv_unknown_schema_raises():
    with pytest.raises(FileNotFoundError):
        read_multi_record_csv(RO_27DV, "bestaat_niet")


def test_read_ro_wrapper_delegates_correctly():
    """read_ro geeft hetzelfde resultaat als read_multi_record_csv(path, 'ro')."""
    assert read_ro(RO_27DV).keys() == read_multi_record_csv(RO_27DV, "ro").keys()
