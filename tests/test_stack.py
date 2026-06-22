"""Tests voor stack_prepared (TDD)."""

from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.stack import stack_prepared

# ---------------------------------------------------------------------------
# Randgevallen — geen fixture nodig
# ---------------------------------------------------------------------------


def test_stack_prepared_empty_returns_empty():
    assert stack_prepared([]) == {}


def test_stack_prepared_file_not_found():
    with pytest.raises(FileNotFoundError):
        stack_prepared([Path("bestaat_niet")])


def test_stack_prepared_labels_mismatch_raises():
    """ValueError vóór FileNotFoundError: ongeldige aanroep direct afgewezen."""
    with pytest.raises(ValueError):
        stack_prepared(["a", "b"], labels=["alleen_een"])


# ---------------------------------------------------------------------------
# Basiswerking
# ---------------------------------------------------------------------------


def test_stack_prepared_single_source_tables_present(prepared_dirs):
    result = stack_prepared([prepared_dirs["21CY"]])
    assert "ISG" in result


def test_stack_prepared_two_sources_row_counts(prepared_dirs):
    result = stack_prepared([prepared_dirs["21CY"], prepared_dirs["25LX"]])
    # fixture: 21CY heeft 4 rijen, 25LX heeft 3 rijen
    assert result["ISG"].height == 7


def test_stack_prepared_union_of_tables(prepared_dirs):
    """Alle tabelnamen uit beide bronnen zijn aanwezig in het resultaat."""
    a_tables = {f.stem for f in prepared_dirs["21CY"].glob("*.parquet")}
    b_tables = {f.stem for f in prepared_dirs["IP"].glob("*.parquet")}
    result = stack_prepared([prepared_dirs["21CY"], prepared_dirs["IP"]])
    assert a_tables | b_tables <= result.keys()


# ---------------------------------------------------------------------------
# Leveringskolom
# ---------------------------------------------------------------------------


def test_stack_prepared_levering_column_present(prepared_dirs):
    result = stack_prepared([prepared_dirs["21CY"], prepared_dirs["25LX"]])
    assert "levering" in result["ISG"].columns


def test_stack_prepared_levering_column_is_first(prepared_dirs):
    result = stack_prepared([prepared_dirs["21CY"], prepared_dirs["25LX"]])
    assert result["ISG"].columns[0] == "levering"


def test_stack_prepared_default_labels_are_dirnames(prepared_dirs):
    result = stack_prepared([prepared_dirs["21CY"], prepared_dirs["25LX"]])
    leveringen = set(result["ISG"]["levering"].unique().to_list())
    assert leveringen == {"21CY", "25LX"}


def test_stack_prepared_custom_labels(prepared_dirs):
    result = stack_prepared(
        [prepared_dirs["21CY"], prepared_dirs["25LX"]], labels=["jaar_a", "jaar_b"]
    )
    leveringen = set(result["ISG"]["levering"].unique().to_list())
    assert leveringen == {"jaar_a", "jaar_b"}


def test_stack_prepared_relative_to_labels(prepared_dirs):
    result = stack_prepared(
        [prepared_dirs["21CY"], prepared_dirs["IP"]],
        relative_to=prepared_dirs["base"],
    )
    leveringen = set(result["ISG"]["levering"].unique().to_list())
    assert leveringen == {"h15/21CY", "h17/IP"}


# ---------------------------------------------------------------------------
# Types en schema-drift
# ---------------------------------------------------------------------------


def test_stack_prepared_types_preserved(prepared_dirs):
    """Date-kolommen blijven pl.Date na concat."""
    result = stack_prepared([prepared_dirs["21CY"], prepared_dirs["25LX"]])
    assert result["ISG"]["DatumInschrijving"].dtype == pl.Date


def test_stack_prepared_schema_drift_fills_null(prepared_dirs):
    """RO en GRONDSLAG hebben een ISG met andere kolommen; ontbrekende → null."""
    result = stack_prepared([prepared_dirs["21CY"], prepared_dirs["IP"]])
    isg = result["ISG"]
    assert "Burgerservicenummer" in isg.columns
    assert "PseudoNummer" in isg.columns
