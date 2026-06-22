"""Tests voor stack_prepared (TDD)."""

from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.stack import stack_prepared

PREPARED = Path("data/02-prepared/demo")
H15_21CY = PREPARED / "h15" / "21CY"
H15_25LX = PREPARED / "h15" / "25LX"
H17_IP = PREPARED / "h17" / "IP"


# ---------------------------------------------------------------------------
# Randgevallen
# ---------------------------------------------------------------------------


def test_stack_prepared_empty_returns_empty():
    assert stack_prepared([]) == {}


def test_stack_prepared_file_not_found():
    with pytest.raises(FileNotFoundError):
        stack_prepared([Path("bestaat_niet")])


# ---------------------------------------------------------------------------
# Basiswerking
# ---------------------------------------------------------------------------


def test_stack_prepared_single_source_tables_present():
    result = stack_prepared([H15_21CY])
    assert {"ISG", "PER", "VLP"} <= result.keys()


def test_stack_prepared_two_sources_row_counts():
    result = stack_prepared([H15_21CY, H15_25LX])
    expected = (
        pl.read_parquet(H15_21CY / "ISG.parquet").height
        + pl.read_parquet(H15_25LX / "ISG.parquet").height
    )
    assert result["ISG"].height == expected


def test_stack_prepared_union_of_tables():
    """Alle tabelnamen uit beide bronnen zijn aanwezig in het resultaat."""
    a = {f.stem for f in H15_21CY.glob("*.parquet")}
    b = {f.stem for f in H17_IP.glob("*.parquet")}
    result = stack_prepared([H15_21CY, H17_IP])
    assert a | b <= result.keys()


# ---------------------------------------------------------------------------
# Leveringskolom
# ---------------------------------------------------------------------------


def test_stack_prepared_levering_column_present():
    result = stack_prepared([H15_21CY, H15_25LX])
    assert "levering" in result["ISG"].columns


def test_stack_prepared_levering_column_is_first():
    result = stack_prepared([H15_21CY, H15_25LX])
    assert result["ISG"].columns[0] == "levering"


def test_stack_prepared_default_labels_are_dirnames():
    result = stack_prepared([H15_21CY, H15_25LX])
    leveringen = set(result["ISG"]["levering"].unique().to_list())
    assert leveringen == {"21CY", "25LX"}


def test_stack_prepared_custom_labels():
    result = stack_prepared([H15_21CY, H15_25LX], labels=["jaar_a", "jaar_b"])
    leveringen = set(result["ISG"]["levering"].unique().to_list())
    assert leveringen == {"jaar_a", "jaar_b"}


def test_stack_prepared_relative_to_labels():
    result = stack_prepared([H15_21CY, H17_IP], relative_to=PREPARED)
    leveringen = set(result["ISG"]["levering"].unique().to_list())
    assert leveringen == {"h15/21CY", "h17/IP"}


def test_stack_prepared_labels_mismatch_raises():
    with pytest.raises(ValueError):
        stack_prepared([H15_21CY, H15_25LX], labels=["alleen_een"])


# ---------------------------------------------------------------------------
# Types en schema-drift
# ---------------------------------------------------------------------------


def test_stack_prepared_types_preserved():
    result = stack_prepared([H15_21CY, H15_25LX])
    assert result["ISG"]["DatumInschrijving"].dtype == pl.Date


def test_stack_prepared_schema_drift_fills_null():
    """RO en GRONDSLAG hebben een ISG met andere kolommen; ontbrekende → null."""
    result = stack_prepared([H15_21CY, H17_IP])
    isg = result["ISG"]
    # RO heeft Burgerservicenummer, GRONDSLAG niet → null voor h17-rijen
    assert "Burgerservicenummer" in isg.columns
    # GRONDSLAG heeft PseudoNummer, RO niet → null voor h15-rijen
    assert "PseudoNummer" in isg.columns
