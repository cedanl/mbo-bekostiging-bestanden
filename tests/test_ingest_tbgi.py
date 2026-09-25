"""Tests voor TBGI XML ingest (TDD)."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.decode import decode_tbgi
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


def test_read_tbgi_bpv_is_eigen_tabel():
    """BekostigingsrelevanteBPV staat in een eigen tabel, niet op Teldatum (#126)."""
    result = read_tbgi(TBGI)
    assert not [c for c in result["Teldatum"].columns if c.startswith("BPV_")]
    for expected in ["Teldatum", "Volgnummer", "Afsluitdatum", "Opleidingcode"]:
        assert expected in result["BekostigingsrelevanteBPV"].columns


def test_read_tbgi_lege_bpv_placeholder_geeft_geen_rij():
    """De demo heeft alleen een BPV-element vol xsi:nil: dat is géén BPV."""
    assert read_tbgi(TBGI)["BekostigingsrelevanteBPV"].is_empty()


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


def test_read_tbgi_lege_signaal_placeholders_geven_geen_rij():
    """De demo-signalen bestaan alleen uit xsi:nil-velden: geen echte signalen."""
    assert read_tbgi(TBGI)["Signaal"].is_empty()


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


# ---------------------------------------------------------------------------
# Meervoudige BPV's en parameters (#126)
# ---------------------------------------------------------------------------
# PvE 4.8.2 §16.1: "Alle BPV's [...] die voldoen aan de eisen voor bekostiging"
# per inschrijving, en "alle parameters met hun waarde" per signaal.

_TBGI_MEERVOUDIG = """<?xml version="1.0" encoding="utf-8"?>
<Bekostigingsgrondslagen xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Inschrijving>
    <BRIN>25LX</BRIN>
    <Burgerservicenummer>111111110</Burgerservicenummer>
    <Inschrijvingvolgnummer>C1</Inschrijvingvolgnummer>
    <Teldatum>
      <Teldatum>2025-10-01</Teldatum>
      <BekostigingsrelevanteBPV>
        <Inschrijvingvolgnummer>C1</Inschrijvingvolgnummer>
        <Volgnummer>1</Volgnummer>
        <DatumBegin>2025-08-01</DatumBegin>
      </BekostigingsrelevanteBPV>
      <BekostigingsrelevanteBPV>
        <Inschrijvingvolgnummer>C0</Inschrijvingvolgnummer>
        <Volgnummer>2</Volgnummer>
        <DatumBegin>2025-09-01</DatumBegin>
      </BekostigingsrelevanteBPV>
      <Signaal>
        <Signaalvolgnummer>A1</Signaalvolgnummer>
        <Signaalcode>S1</Signaalcode>
        <Parameter>
          <Parametervolgnummer>P1</Parametervolgnummer>
          <Parameternaam>naam1</Parameternaam>
        </Parameter>
        <Parameter>
          <Parametervolgnummer>P2</Parametervolgnummer>
          <Parameternaam>naam2</Parameternaam>
        </Parameter>
      </Signaal>
      <Signaal>
        <Signaalvolgnummer>A2</Signaalvolgnummer>
        <Signaalcode>S2</Signaalcode>
      </Signaal>
    </Teldatum>
  </Inschrijving>
</Bekostigingsgrondslagen>
"""


@pytest.fixture
def tbgi_meervoudig(tmp_path: Path) -> dict[str, pl.DataFrame]:
    pad = tmp_path / "TBGI_25LX_2027_20251124.XML"
    pad.write_text(_TBGI_MEERVOUDIG, encoding="utf-8")
    return read_tbgi(pad)


def test_alle_bpvs_per_teldatum_worden_ingelezen(tbgi_meervoudig):
    bpv = tbgi_meervoudig["BekostigingsrelevanteBPV"]
    assert bpv.select(
        "Burgerservicenummer",
        "Inschrijvingvolgnummer",
        "Teldatum",
        "InschrijvingvolgnummerBPV",
        "Volgnummer",
    ).rows() == [
        ("111111110", "C1", "2025-10-01", "C1", "1"),
        ("111111110", "C1", "2025-10-01", "C0", "2"),
    ]


def test_teldatum_grain_blijft_een_rij_per_teldatum(tbgi_meervoudig):
    assert tbgi_meervoudig["Teldatum"].height == 1


def test_alle_parameters_per_signaal_worden_ingelezen(tbgi_meervoudig):
    signaal = tbgi_meervoudig["Signaal"]
    assert signaal.select(
        "Signaalvolgnummer", "Parametervolgnummer", "Parameternaam"
    ).rows() == [("A1", "P1", "naam1"), ("A1", "P2", "naam2"), ("A2", None, None)]


def test_alfanumerieke_volgnummers_overleven_decode(tbgi_meervoudig):
    """Signaal- en parametervolgnummers zijn AN1..2 (PvE §16.5.4/5), geen getal."""
    signaal = decode_tbgi(tbgi_meervoudig)["Signaal"]
    assert signaal["Signaalvolgnummer"].to_list() == ["A1", "A1", "A2"]
    assert signaal["Parametervolgnummer"].to_list() == ["P1", "P2", None]


def test_bpv_datums_worden_gedecodeerd(tbgi_meervoudig):
    bpv = decode_tbgi(tbgi_meervoudig)["BekostigingsrelevanteBPV"]
    assert bpv["DatumBegin"].to_list() == [date(2025, 8, 1), date(2025, 9, 1)]
