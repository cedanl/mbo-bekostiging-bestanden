"""Tests voor RO-ingest (TDD).

Tests zijn opzettelijk in dit volgorde geschreven:
1. Laagste granulariteit (bestand leesbaar, juist type)
2. Structuur (verwachte recordtypes aanwezig)
3. Inhoud (kolomnamen, waarden)
4. Robuustheid (separator-varianten, omgekeerde volgorde)
"""

from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.ingest import read_ro

DEMO_H15 = Path("data/01-raw/demo/h15")
RO_27DV = DEMO_H15 / "RO_27DV_20240731_20260324.csv"  # separator |
RO_25LX = DEMO_H15 / "RO_25LX_20250101_20251231.csv"  # separator ;
RO_21CY = DEMO_H15 / "RO_21CY_20250730_20250731.csv"  # separator ;, VLP als laatste


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------


def test_read_ro_returns_dict():
    result = read_ro(RO_27DV)
    assert isinstance(result, dict)


def test_read_ro_file_not_found():
    with pytest.raises(FileNotFoundError):
        read_ro("bestaat_niet.csv")


# ---------------------------------------------------------------------------
# Structuur
# ---------------------------------------------------------------------------


def test_read_ro_contains_required_recordtypes():
    # ISE en AMO zijn optioneel; demo-bestanden zijn subsets.
    result = read_ro(RO_27DV)
    required = {"VLP", "PER", "ISG", "ISP", "BPV", "DIP", "GEO", "KZD", "SLR"}
    missing = required - result.keys()
    assert not missing, f"Ontbrekende recordtypes: {missing}"


def test_read_ro_vlp_has_one_row():
    for path in [RO_27DV, RO_25LX, RO_21CY]:
        result = read_ro(path)
        assert result["VLP"].height == 1, f"VLP moet 1 rij hebben in {path.name}"


def test_read_ro_slr_has_one_row():
    for path in [RO_27DV, RO_25LX, RO_21CY]:
        result = read_ro(path)
        assert result["SLR"].height == 1, f"SLR moet 1 rij hebben in {path.name}"


# ---------------------------------------------------------------------------
# Kolomnamen
# ---------------------------------------------------------------------------


def test_read_ro_vlp_column_names():
    result = read_ro(RO_27DV)
    assert result["VLP"].columns == [
        "Recordsoort",
        "BRIN",
        "DatumBeginPeriode",
        "DatumEindePeriode",
        "DatumAanmaak",
    ]


def test_read_ro_per_column_names():
    result = read_ro(RO_27DV)
    assert result["PER"].columns == [
        "Recordsoort",
        "Burgerservicenummer",
        "Onderwijsnummer",
        "Geboortedatum",
        "Geslacht",
    ]


def test_read_ro_isg_column_names():
    result = read_ro(RO_27DV)
    assert result["ISG"].columns == [
        "Recordsoort",
        "Burgerservicenummer",
        "Onderwijsnummer",
        "Inschrijvingvolgnummer",
        "DatumInschrijving",
        "DatumUitschrijvingGepland",
        "DatumUitschrijvingWerkelijk",
        "RedenUitschrijving",
    ]


def test_read_ro_slr_column_names():
    result = read_ro(RO_27DV)
    assert result["SLR"].columns == [
        "Recordsoort",
        "AantalPER",
        "AantalISG",
        "AantalISP",
        "AantalISE",
        "AantalBPV",
        "AantalDIP",
        "AantalAMO",
        "AantalGEO",
        "AantalKZD",
    ]


# ---------------------------------------------------------------------------
# Inhoud
# ---------------------------------------------------------------------------


def test_read_ro_vlp_brin_pipe():
    assert read_ro(RO_27DV)["VLP"]["BRIN"][0] == "27DV"


def test_read_ro_vlp_brin_semicolon():
    assert read_ro(RO_25LX)["VLP"]["BRIN"][0] == "25LX"


def test_read_ro_slr_counts_are_integers():
    """SLR-telwaarden moeten parseerbaar zijn als gehele getallen.

    De demo-bestanden zijn subsets: SLR-counts weerspiegelen de volledige export,
    niet de demo-subset. Count-matching hoort in validate.py.
    """
    result = read_ro(RO_27DV)
    slr = result["SLR"].row(0, named=True)
    for col in [
        "AantalPER",
        "AantalISG",
        "AantalISP",
        "AantalISE",
        "AantalBPV",
        "AantalDIP",
        "AantalAMO",
        "AantalGEO",
        "AantalKZD",
    ]:
        int(slr[col])  # mag niet gooien


# ---------------------------------------------------------------------------
# Robuustheid
# ---------------------------------------------------------------------------


def test_read_ro_inverted_file_structure():
    """21CY heeft VLP als laatste en SLR als eerste — volgorde mag niet uitmaken."""
    result = read_ro(RO_21CY)
    assert result["VLP"]["BRIN"][0] == "21CY"
    assert result["SLR"].height == 1


def test_read_ro_all_demo_files_parse():
    for path in [RO_27DV, RO_25LX, RO_21CY]:
        result = read_ro(path)
        assert len(result) > 0, f"Geen records ingelezen uit {path.name}"


def test_read_ro_no_extra_columns_from_padding():
    """Paddingrijen (lege trailing velden) mogen de kolomtelling niet opblazen."""
    result = read_ro(RO_25LX)
    assert result["VLP"].width == 5
    assert result["ISG"].width == 8
