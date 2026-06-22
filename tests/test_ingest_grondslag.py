"""Tests voor GRONDSLAG IP MBO ingest (TDD)."""

from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.ingest import read_grondslag

DEMO_H17 = Path("data/01-raw/demo/h17")
GRONDSLAG = DEMO_H17 / "GRONDSLAG_IP_MBO_27DV_20251119_2025.csv"


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------


def test_read_grondslag_all_values_are_dataframes():
    """Alle waarden in het resultaat zijn Polars DataFrames — geen strings of None."""
    result = read_grondslag(GRONDSLAG)
    assert result
    for rt, df in result.items():
        assert isinstance(df, pl.DataFrame), f"{rt} is geen DataFrame"


def test_read_grondslag_file_not_found():
    with pytest.raises(FileNotFoundError):
        read_grondslag("bestaat_niet.csv")


# ---------------------------------------------------------------------------
# Verplichte recordtypes aanwezig
# ---------------------------------------------------------------------------


def test_read_grondslag_contains_required_recordtypes():
    result = read_grondslag(GRONDSLAG)
    required = {"VLP", "PER", "ISG", "ISP", "BPV", "DIP", "GEO", "KZD", "SLR"}
    missing = required - result.keys()
    assert not missing, f"Ontbrekende recordtypes: {missing}"


def test_read_grondslag_vlp_has_one_row():
    assert read_grondslag(GRONDSLAG)["VLP"].height == 1


def test_read_grondslag_slr_has_one_row():
    assert read_grondslag(GRONDSLAG)["SLR"].height == 1


# ---------------------------------------------------------------------------
# Kolomnamen
# ---------------------------------------------------------------------------


def test_read_grondslag_vlp_columns():
    result = read_grondslag(GRONDSLAG)
    assert result["VLP"].columns == [
        "Recordsoort",
        "BRIN",
        "Studiejaar",
        "DatumAanmaak",
        "BekostigingsType",
    ]


def test_read_grondslag_per_columns():
    result = read_grondslag(GRONDSLAG)
    assert result["PER"].columns[:8] == [
        "Recordsoort",
        "PseudoNummer",
        "Leeftijd1",
        "Leeftijd2",
        "Leeftijd3",
        "Leeftijd4",
        "Geslacht",
        "Postcodecijfers",
    ]


def test_read_grondslag_slr_has_grondslag_specific_fields():
    """GRONDSLAG SLR bevat AantalBII en AantalBID — anders dan RO SLR."""
    cols = read_grondslag(GRONDSLAG)["SLR"].columns
    assert "AantalBII" in cols
    assert "AantalBID" in cols


# ---------------------------------------------------------------------------
# Inhoud
# ---------------------------------------------------------------------------


def test_read_grondslag_vlp_brin():
    assert read_grondslag(GRONDSLAG)["VLP"]["BRIN"][0] == "27DV"


def test_read_grondslag_per_count():
    result = read_grondslag(GRONDSLAG)
    assert result["PER"].height == 10
