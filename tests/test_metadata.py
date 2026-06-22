"""Tests voor metadata-module (TDD)."""

import pytest

from mbo_bekostiging_bestanden.metadata import load_schema


def test_load_schema_ro_returns_dict():
    schema = load_schema("ro")
    assert isinstance(schema, dict)


def test_load_schema_default_is_ro():
    assert load_schema() == load_schema("ro")


def test_load_schema_ro_contains_vlp():
    assert "VLP" in load_schema("ro")


def test_load_schema_ro_vlp_has_fields():
    assert "fields" in load_schema("ro")["VLP"]


def test_load_schema_unknown_raises():
    with pytest.raises(FileNotFoundError):
        load_schema("bestaat_niet")


def test_load_schema_ro_vlp_single_row():
    assert load_schema("ro")["VLP"].get("single_row") is True


def test_load_schema_ro_slr_single_row():
    assert load_schema("ro")["SLR"].get("single_row") is True


def test_load_schema_ro_per_not_single_row():
    assert not load_schema("ro")["PER"].get("single_row", False)
