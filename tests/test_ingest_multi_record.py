"""Tests voor generieke multi-record CSV ingest (TDD)."""

from pathlib import Path

from mbo_bekostiging_bestanden.ingest import read_multi_record_csv, read_ro

DEMO_H15 = Path("data/01-raw/demo/h15")
RO_27DV = DEMO_H15 / "RO_27DV_20240731_20260324.csv"


def test_read_multi_record_csv_returns_dict():
    result = read_multi_record_csv(RO_27DV, "ro")
    assert isinstance(result, dict)


def test_read_multi_record_csv_same_output_as_read_ro():
    via_generic = read_multi_record_csv(RO_27DV, "ro")
    via_wrapper = read_ro(RO_27DV)
    assert via_generic.keys() == via_wrapper.keys()
    for rt in via_generic:
        assert via_generic[rt].equals(via_wrapper[rt])


def test_read_multi_record_csv_unknown_schema_raises():
    import pytest
    with pytest.raises(FileNotFoundError):
        read_multi_record_csv(RO_27DV, "bestaat_niet")


def test_read_ro_is_still_callable():
    result = read_ro(RO_27DV)
    assert "VLP" in result
