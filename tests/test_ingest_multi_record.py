"""Tests voor generieke multi-record CSV ingest (TDD)."""

from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.ingest import read_multi_record_csv

DEMO_H15 = Path("data/01-raw/demo/h15")
RO_27DV = DEMO_H15 / "RO_27DV_20240731_20260324.csv"


def test_read_multi_record_csv_parses_vlp_brin():
    """Generieke functie leest BRIN correct uit VLP — gedragstest."""
    result = read_multi_record_csv(RO_27DV, "ro")
    assert result["VLP"]["BRIN"][0] == "27DV"


def test_read_multi_record_csv_kolomnamen_komen_uit_schema():
    """Kolomaantal klopt met het schema.

    Kolomnamen hardcoden verifieert niks over parsering.
    """
    result = read_multi_record_csv(RO_27DV, "ro")
    from mbo_bekostiging_bestanden.metadata import load_schema

    schema = load_schema("ro")
    assert result["VLP"].width == len(schema["VLP"]["fields"])
    assert result["ISG"].width == len(schema["ISG"]["fields"])


def test_read_multi_record_csv_file_not_found():
    with pytest.raises(FileNotFoundError):
        read_multi_record_csv("bestaat_niet.csv", "ro")


def test_read_multi_record_csv_unknown_schema_raises():
    with pytest.raises(FileNotFoundError):
        read_multi_record_csv(RO_27DV, "bestaat_niet")


def test_read_multi_record_csv_onbekend_recordtype_faalt(tmp_path):
    """Fail-closed (#257): een onbekend recordtype was voorheen stil overgeslagen."""
    bron = tmp_path / "RO_99XX_20250801_20260731.csv"
    bron.write_text(
        "VLP|99XX|2025-08-01|2026-07-31|2026-08-01\nXYZ|iets\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="XYZ"):
        read_multi_record_csv(bron, "ro")


def test_read_multi_record_csv_gevuld_veld_voorbij_schema_faalt(tmp_path):
    """Fail-closed (#257): een gevuld veld voorbij de schemabreedte was voorheen
    stil afgeknipt."""
    bron = tmp_path / "RO_99XX_20250801_20260731.csv"
    bron.write_text(
        "VLP|99XX|2025-08-01|2026-07-31|2026-08-01\n"
        "ISG|BSN2||1|2025-08-01|2027-07-31|||ONVERWACHT\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ISG"):
        read_multi_record_csv(bron, "ro")


def _ro(tmp_path, *regels: str):
    bron = tmp_path / "RO_99XX_20250801_20260731.csv"
    bron.write_text("\n".join(regels) + "\n", encoding="utf-8")
    return bron


_RO_VLP = "VLP|99XX|2025-08-01|2026-07-31|2026-08-01"


def test_korte_regel_zonder_verplicht_achterveld_faalt(tmp_path):
    """Afgeknipt na DatumInschrijving: DatumUitschrijvingGepland is verplicht (#281)."""
    bron = _ro(tmp_path, _RO_VLP, "ISG|BSN1||1|2025-08-01")
    with pytest.raises(ValueError, match="DatumUitschrijvingGepland"):
        read_multi_record_csv(bron, "ro")


def test_korte_regel_zonder_optionele_achtervelden_wordt_gepad(tmp_path):
    """Nog ingeschreven: DatumUitschrijvingWerkelijk en RedenUitschrijving leeg."""
    from mbo_bekostiging_bestanden.metadata import load_schema

    bron = _ro(tmp_path, _RO_VLP, "ISG|BSN1||1|2025-08-01|2027-07-31")
    result = read_multi_record_csv(bron, "ro")
    assert result["ISG"].width == len(load_schema("ro")["ISG"]["fields"])
    assert result["ISG"]["RedenUitschrijving"].to_list() == [""]


def test_vlp_zonder_laatste_velden_faalt(tmp_path):
    """Audit F-04: een afgeknipte VLP gaf geen exception en geen parseverlies."""
    bron = _ro(tmp_path, "VLP|99XX|2025-08-01")
    with pytest.raises(ValueError, match="VLP"):
        read_multi_record_csv(bron, "ro")


def test_read_multi_record_csv_grondslag_spiegelvelden_zijn_toegestaan(tmp_path):
    """Gedeclareerde spiegelvelden (GRONDSLAG-PER 19-21) zijn geen
    schemaoverschrijding, ook niet als de waarde niet spiegelt (#257 raakt
    alleen fail-closed op écht onbekende/ongedeclareerde overschrijding)."""
    bron = tmp_path / "GRONDSLAG_IP_MBO_99XX_20251119_2025.csv"
    per = "PER;900000001;17;18;19;20;V;1234;;;;6030;6031;6032;6033;01;0001;0002"
    bron.write_text(f"VLP;99XX;2025;20251119;V\n{per};9999;01;0001\n", encoding="utf-8")
    result = read_multi_record_csv(bron, "grondslag")
    assert "PER" in result


def test_niet_utf8_bestand_wordt_als_cp1252_gelezen(tmp_path):
    """#393: byte 0x80 is in cp1252 een euroteken, geen controlekarakter."""
    bron = tmp_path / "RO_99XX_20250801_20260731.csv"
    bron.write_bytes(
        (b"VLP|99XX|2025-08-01|2026-07-31|2026-08-01\n")
        + "ISG|BSN2||€|2025-08-01|2027-07-31|\n".encode("cp1252")
    )
    isg = read_multi_record_csv(bron, "ro")["ISG"]
    assert "€" in isg.row(0)


def test_bestand_met_ongedefinieerde_cp1252_byte_valt_terug_op_latin1(tmp_path):
    """Byte 0x81 bestaat niet in cp1252; latin-1 decodeert elke byte."""
    bron = tmp_path / "RO_99XX_20250801_20260731.csv"
    bron.write_bytes(
        b"VLP|99XX|2025-08-01|2026-07-31|2026-08-01\nISG|BSN2||\x81|2025-08-01|2027-07-31|\n"
    )
    assert "\x81" in read_multi_record_csv(bron, "ro")["ISG"].row(0)
