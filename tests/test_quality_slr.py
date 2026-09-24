"""Tests voor SLR-reconciliatie tri-state status."""

import polars as pl

from mbo_bekostiging_bestanden.quality import (
    QualityReport,
    check_slr_reconciliation,
    slr_status_icoon,
)


def test_slr_status_is_tri_state():
    """SLR status moet tri-state zijn: match/mismatch/unknown."""
    report = QualityReport(levering="test", schema_type="ro")
    assert hasattr(report, "slr_status"), (
        "QualityReport must have slr_status attribute"
    )
    assert report.slr_status in ["match", "mismatch", "unknown"]


def test_missing_slr_returns_unknown_status():
    """Ontbrekende SLR record → status 'unknown'."""
    frames = {
        "VLP": pl.DataFrame({"Recordsoort": ["RO"]}),
        "PER": pl.DataFrame({"dummy": [1]}),
    }

    report = check_slr_reconciliation(frames, "test_levering")
    assert report.slr_status == "unknown"


def test_slr_mapping_includes_ise_bii_bid():
    """SLR mapping moet ISE, BII, BID bevatten."""
    frames = {
        "VLP": pl.DataFrame({"Recordsoort": ["VLP"]}),
        "SLR": pl.DataFrame({
            "AantalBII": [100],
            "AantalBID": [50],
            "AantalISE": [20],
        }),
        "BII": pl.DataFrame({"dummy": [1] * 100}),
        "BID": pl.DataFrame({"dummy": [1] * 50}),
        "ISE": pl.DataFrame({"dummy": [1] * 20}),
    }

    report = check_slr_reconciliation(frames, "grondslag_test")
    expected_types = {"BII", "BID", "ISE"}
    found_types = set(report.slr_checks.keys()) & expected_types
    assert len(found_types) >= 1, (
        f"SLR reconciliation should check BII/BID/ISE. Found: {found_types}"
    )


def test_slr_match_status_when_numbers_agree():
    """SLR match: expected == actual → status 'match'."""
    frames = {
        "VLP": pl.DataFrame({"Recordsoort": ["RO"]}),
        "SLR": pl.DataFrame({
            "AantalPER": [10],
            "AantalISP": [20],
        }),
        "PER": pl.DataFrame({"dummy": [1] * 10}),
        "ISP": pl.DataFrame({"dummy": [1] * 20}),
    }

    report = check_slr_reconciliation(frames, "ro_match")
    assert report.slr_status == "match", (
        f"Expected 'match', got {report.slr_status}"
    )


def test_slr_match_levert_geen_ok_waarschuwing():
    """Een geslaagde check zet 'SLR-reconciliatie: OK' niet in warnings.

    Regressie #81: de OK-melding verscheen óók in `warnings`, waardoor de UI
    naast de groene ✅-status een ⚠️-regel toonde. Warnings zijn gereserveerd
    voor problemen; `slr_status == "match"` is zelf al het signaal.
    """
    frames = {
        "VLP": pl.DataFrame({"Recordsoort": ["RO"]}),
        "SLR": pl.DataFrame({
            "AantalPER": [10],
            "AantalISP": [20],
        }),
        "PER": pl.DataFrame({"dummy": [1] * 10}),
        "ISP": pl.DataFrame({"dummy": [1] * 20}),
    }

    report = check_slr_reconciliation(frames, "ro_match")
    assert report.slr_status == "match"
    assert "SLR-reconciliatie: OK" not in report.warnings


def test_slr_mismatch_status():
    """SLR mismatch: expected != actual → status 'mismatch'."""
    frames = {
        "VLP": pl.DataFrame({"Recordsoort": ["RO"]}),
        "SLR": pl.DataFrame({
            "AantalPER": [100],
            "AantalISP": [50],
        }),
        "PER": pl.DataFrame({"dummy": [1] * 10}),
        "ISP": pl.DataFrame({"dummy": [1] * 50}),
    }

    report = check_slr_reconciliation(frames, "ro_mismatch")
    assert report.slr_status == "mismatch", (
        f"Expected 'mismatch', got {report.slr_status}"
    )


def test_slr_status_icoon_dekt_tri_state():
    """slr_status → icoon; onbekende/ontbrekende status valt veilig terug op ⚠️."""
    assert slr_status_icoon("match") == "✅"
    assert slr_status_icoon("mismatch") == "❌"
    assert slr_status_icoon("unknown") == "⚠️"


def test_slr_status_icoon_valt_veilig_terug():
    """None of onbekende waarde mag nooit crashen en toont ⚠️."""
    assert slr_status_icoon(None) == "⚠️"
    assert slr_status_icoon("niet-bestaand") == "⚠️"


def test_grondslag_bestand_krijgt_schema_type_grondslag():
    """GRONDSLAG-files mogen niet als 'ro' gelabeld worden.

    Regressie: de oude check zocht "GRONDSLAG" in ``VLP.Recordsoort``, maar die
    kolom bevat altijd "VLP".  Het onderscheid zit in de aanwezigheid van
    GRONDSLAG-only recordtypes (BII/BID).
    """
    frames = {
        "VLP": pl.DataFrame({"Recordsoort": ["VLP"], "Bekostiging": ["V"]}),
        "SLR": pl.DataFrame({"AantalBII": [1]}),
        "BII": pl.DataFrame({"dummy": [1]}),
    }

    report = check_slr_reconciliation(frames, "grondslag_test")

    assert report.schema_type == "grondslag", (
        f"Expected 'grondslag', got {report.schema_type!r}"
    )


def test_ro_bestand_krijgt_schema_type_ro():
    """RO-files zonder GRONDSLAG-only records worden 'ro'."""
    frames = {
        "VLP": pl.DataFrame({"Recordsoort": ["VLP"]}),
        "SLR": pl.DataFrame({"AantalPER": [1]}),
        "PER": pl.DataFrame({"dummy": [1]}),
    }

    report = check_slr_reconciliation(frames, "ro_test")

    assert report.schema_type == "ro"
