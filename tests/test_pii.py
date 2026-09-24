"""Tests voor PII-kolomdetectie."""

from mbo_bekostiging_bestanden.pii import detect_pii_columns


def test_exacte_pii_kolommen_worden_herkend():
    kolommen = ["Burgerservicenummer", "Onderwijsnummer", "PseudoNummer", "Geslacht"]
    assert detect_pii_columns(kolommen) == kolommen


def test_patroon_match_via_substring():
    assert "CodeLandWaarnaarVertrokken" in detect_pii_columns(
        ["CodeLandWaarnaarVertrokken"]
    )


def test_niet_pii_kolommen_bijven_gespaard():
    pii = detect_pii_columns(
        ["_persoon_id", "Opleidingcode", "BekostigdeEenheden", "SLR-status", "_bron"]
    )
    assert pii == ["_persoon_id"]