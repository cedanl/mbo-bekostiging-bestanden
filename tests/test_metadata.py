"""Tests voor metadata-module (TDD)."""

import pytest

from mbo_bekostiging_bestanden.metadata import load_schema


def test_load_schema_returns_dict():
    assert isinstance(load_schema("ro"), dict)


def test_load_schema_default_is_ro():
    assert load_schema() == load_schema("ro")


def test_load_schema_filters_scalar_entries():
    """schema_version en andere scalars mogen niet in de output voorkomen."""
    schema = load_schema("ro")
    for key, value in schema.items():
        assert isinstance(value, dict), f"{key!r} is geen recordtype-dict"


def test_load_schema_contains_vlp():
    assert "VLP" in load_schema("ro")


def test_load_schema_vlp_has_required_keys():
    vlp = load_schema("ro")["VLP"]
    assert "fields" in vlp
    assert "date_fields" in vlp
    assert "int_fields" in vlp


def test_load_schema_unknown_raises():
    with pytest.raises(FileNotFoundError):
        load_schema("bestaat_niet")


def test_load_schema_vlp_single_row():
    assert load_schema("ro")["VLP"].get("single_row") is True


def test_load_schema_slr_single_row():
    assert load_schema("ro")["SLR"].get("single_row") is True


def test_load_schema_per_not_single_row():
    assert not load_schema("ro")["PER"].get("single_row", False)


def test_load_schema_is_cached():
    """Herhaalde aanroep geeft hetzelfde object terug (geen herhaalde schijflezing)."""
    assert load_schema("ro") is load_schema("ro")
