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


# ---------------------------------------------------------------------------
# Persoon per teldatum en signaal (#125)
# ---------------------------------------------------------------------------
# Inschrijvingvolgnummer is alleen uniek per persoon binnen een instelling
# (PvE 4.8.2 §16.5.1). Teldatum- en Signaal-rijen moeten daarom de BSN/ONr van
# hun eigen ouder-element dragen, niet achteraf via het volgnummer gezocht worden.

_TBGI_GEDEELD_VOLGNUMMER = """<?xml version="1.0" encoding="utf-8"?>
<Bekostigingsgrondslagen xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Inschrijving>
    <BRIN>25LX</BRIN>
    <Burgerservicenummer>111111110</Burgerservicenummer>
    <Onderwijsnummer xsi:nil="true"/>
    <Inschrijvingvolgnummer>C1</Inschrijvingvolgnummer>
    <Teldatum>
      <Teldatum>2025-10-01</Teldatum>
      <Signaal><Signaalcode>S1</Signaalcode></Signaal>
    </Teldatum>
  </Inschrijving>
  <Inschrijving>
    <BRIN>25LX</BRIN>
    <Burgerservicenummer xsi:nil="true"/>
    <Onderwijsnummer>222222220</Onderwijsnummer>
    <Inschrijvingvolgnummer>C1</Inschrijvingvolgnummer>
    <Teldatum>
      <Teldatum>2025-10-01</Teldatum>
    </Teldatum>
  </Inschrijving>
  <Diploma>
    <BRIN>25LX</BRIN>
    <Burgerservicenummer>333333330</Burgerservicenummer>
    <Resultaatvolgnummer>R1</Resultaatvolgnummer>
    <Signaal><Signaalcode>S2</Signaalcode></Signaal>
  </Diploma>
</Bekostigingsgrondslagen>
"""


@pytest.fixture
def tbgi_gedeeld_volgnummer(tmp_path: Path) -> dict[str, pl.DataFrame]:
    pad = tmp_path / "TBGI_25LX_2027_20251124.XML"
    pad.write_text(_TBGI_GEDEELD_VOLGNUMMER, encoding="utf-8")
    return read_tbgi(pad)


def test_teldatum_draagt_persoon_van_eigen_inschrijving(tbgi_gedeeld_volgnummer):
    teldatum = tbgi_gedeeld_volgnummer["Teldatum"]
    assert teldatum.select(
        "Inschrijvingvolgnummer", "Burgerservicenummer", "Onderwijsnummer"
    ).rows() == [("C1", "111111110", None), ("C1", None, "222222220")]


def test_signaal_draagt_persoon_van_eigen_bron(tbgi_gedeeld_volgnummer):
    signaal = tbgi_gedeeld_volgnummer["Signaal"]
    assert signaal.select("Bron", "Signaalcode", "Burgerservicenummer").rows() == [
        ("Inschrijving", "S1", "111111110"),
        ("Diploma", "S2", "333333330"),
    ]
