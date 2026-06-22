"""Tests voor TBGI XML ingest (TDD)."""

from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.ingest import read_tbgi

DEMO_H16 = Path("data/01-raw/demo/h16")
TBGI = DEMO_H16 / "TBGI_25LX_2027_20251124.XML"


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------


def test_read_tbgi_all_values_are_dataframes():
    result = read_tbgi(TBGI)
    assert result
    for tabel, df in result.items():
        assert isinstance(df, pl.DataFrame), f"{tabel} is geen DataFrame"


def test_read_tbgi_file_not_found():
    with pytest.raises(FileNotFoundError):
        read_tbgi("bestaat_niet.xml")


# ---------------------------------------------------------------------------
# Verplichte tabellen aanwezig
# ---------------------------------------------------------------------------


def test_read_tbgi_contains_required_tables():
    result = read_tbgi(TBGI)
    required = {"Inschrijving", "Teldatum", "Diploma", "Signaal"}
    missing = required - result.keys()
    assert not missing, f"Ontbrekende tabellen: {missing}"


def test_read_tbgi_inschrijving_has_one_row():
    assert read_tbgi(TBGI)["Inschrijving"].height == 1


def test_read_tbgi_teldatum_has_one_row():
    assert read_tbgi(TBGI)["Teldatum"].height == 1


def test_read_tbgi_diploma_has_one_row():
    assert read_tbgi(TBGI)["Diploma"].height == 1


# ---------------------------------------------------------------------------
# Kolomnamen
# ---------------------------------------------------------------------------


def test_read_tbgi_inschrijving_columns():
    cols = read_tbgi(TBGI)["Inschrijving"].columns
    for expected in [
        "BRIN",
        "Burgerservicenummer",
        "Inschrijvingvolgnummer",
        "DatumInschrijving",
        "DatumUitschrijvingGepland",
    ]:
        assert expected in cols, f"{expected} ontbreekt in Inschrijving"


def test_read_tbgi_teldatum_has_bpv_columns():
    """BekostigingsrelevanteBPV-velden staan geprefixed in Teldatum."""
    cols = read_tbgi(TBGI)["Teldatum"].columns
    for expected in ["BPV_Afsluitdatum", "BPV_DatumBegin", "BPV_Opleidingcode"]:
        assert expected in cols, f"{expected} ontbreekt in Teldatum"


def test_read_tbgi_signaal_has_bron_column():
    """Signaal heeft een Bron-kolom ('Inschrijving' of 'Diploma')."""
    cols = read_tbgi(TBGI)["Signaal"].columns
    assert "Bron" in cols


# ---------------------------------------------------------------------------
# Inhoud
# ---------------------------------------------------------------------------


def test_read_tbgi_inschrijving_brin():
    assert read_tbgi(TBGI)["Inschrijving"]["BRIN"][0] == "25LX"


def test_read_tbgi_diploma_brin():
    assert read_tbgi(TBGI)["Diploma"]["BRIN"][0] == "25LX"


def test_read_tbgi_diploma_resultaatvolgnummer():
    assert read_tbgi(TBGI)["Diploma"]["Resultaatvolgnummer"][0] == "1362433"


def test_read_tbgi_teldatum_opleidingcode():
    assert read_tbgi(TBGI)["Teldatum"]["Opleidingcode"][0] == "25748"


def test_read_tbgi_signaal_row_count():
    """Demo-bestand heeft 2 signalen (1 per teldatum, 1 per diploma)."""
    assert read_tbgi(TBGI)["Signaal"].height == 2


def test_read_tbgi_signaal_bron_values():
    """Bron-kolom bevat uitsluitend 'Inschrijving' of 'Diploma'."""
    bron = set(read_tbgi(TBGI)["Signaal"]["Bron"].to_list())
    assert bron <= {"Inschrijving", "Diploma"}


def test_read_tbgi_null_fields_are_utf8():
    """xsi:nil-elementen (bijv. Onderwijsnummer) zijn Utf8, niet Null."""
    df = read_tbgi(TBGI)["Inschrijving"]
    null_typed = [c for c in df.columns if str(df[c].dtype) == "Null"]
    assert null_typed == [], f"Kolommen met pl.Null dtype: {null_typed}"
