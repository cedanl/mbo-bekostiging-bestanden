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


def test_read_multi_record_csv_korte_regel_wordt_nog_gepad(tmp_path):
    """Buiten scope van #257: optionele achtervelden zijn nog niet expliciet
    gemarkeerd in het schema, dus korte regels worden (nog) gepad, niet
    afgekeurd — zie vervolgissue over optionele-veldmarkering."""
    bron = tmp_path / "RO_99XX_20250801_20260731.csv"
    bron.write_text(
        "VLP|99XX|2025-08-01|2026-07-31|2026-08-01\nISG|BSN1||1|2025-08-01\n",
        encoding="utf-8",
    )
    from mbo_bekostiging_bestanden.metadata import load_schema

    result = read_multi_record_csv(bron, "ro")
    assert result["ISG"].width == len(load_schema("ro")["ISG"]["fields"])


def test_read_multi_record_csv_grondslag_spiegelvelden_zijn_toegestaan(tmp_path):
    """Gedeclareerde spiegelvelden (GRONDSLAG-PER 19-21) zijn geen
    schemaoverschrijding, ook niet als de waarde niet spiegelt (#257 raakt
    alleen fail-closed op écht onbekende/ongedeclareerde overschrijding)."""
    bron = tmp_path / "GRONDSLAG_IP_MBO_99XX_20251119_2025.csv"
    per = "PER;900000001;17;18;19;20;V;1234;;;;6030;6031;6032;6033;01;0001;0002"
    bron.write_text(f"VLP;99XX;2025;20251119;V\n{per};9999;01;0001\n", encoding="utf-8")
    result = read_multi_record_csv(bron, "grondslag")
    assert "PER" in result
