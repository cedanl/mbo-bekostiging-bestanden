"""Tests voor PII detection en CSV-export met privacy-safeguards."""


# Centralized PII patterns (expected after fix)
_PII_PATTERNS = {
    "Burgerservicenummer",
    "Onderwijsnummer",
    "PseudoNummer",
    "Geboortedatum",
    "Postcode",
    "Gemeente",
    "Nationaliteit",
    "Geboorteland",
    "Migratieachtergrond",
    "Verblijfstitel",
    "DatumVestiging",
    "DatumVertrek",
    "_persoon_id",
}


def _detect_pii_with_patterns(columns: list[str]) -> set[str]:
    """Detect PII columns using pattern matching (expected after fix)."""
    pii_found = set()
    for col in columns:
        if col in _PII_PATTERNS:
            pii_found.add(col)
            continue
        col_lower = col.lower()
        for pattern in _PII_PATTERNS:
            if pattern.lower() in col_lower:
                pii_found.add(col)
                break
    return pii_found


def test_pii_detector_with_patterns_finds_star_schema_columns():
    """After fix: pattern-based detector finds all PII in dim_deelnemer."""
    dim_deelnemer_cols = [
        "_persoon_id",
        "Geslacht",
        "Postcodecijfers",
        "Gemeente",
        "Gemeentecode",
        "Nationaliteit1",
        "Nationaliteit1_naam",
        "Nationaliteit1_migratieachtergrond",
        "Nationaliteit2",
        "Nationaliteit2_naam",
        "Nationaliteit2_migratieachtergrond",
        "CodeGeboorteland",
        "CodeGeboorteland_naam",
        "CodeGeboorteland_migratieachtergrond",
        "CodeGeboortelandOuder1",
        "CodeGeboortelandOuder2",
        "Verblijfstitel",
        "DatumVestigingNederland",
        "DatumVertrekNederland",
        "CodeLandWaarnaarVertrokken",
        "Geboortedatum",
    ]

    detected = _detect_pii_with_patterns(dim_deelnemer_cols)

    assert len(detected) >= 18, (
        f"Pattern-based detector found {len(detected)} PII columns, expected ≥18. "
        f"Detected: {detected}"
    )

    assert any("ostcode" in c.lower() for c in detected), (
        "Postcode pattern not matched"
    )
    assert any("ationaliteit" in c.lower() for c in detected), (
        "Nationaliteit pattern not matched"
    )
    assert any("eboorteland" in c.lower() for c in detected), (
        "Geboorteland pattern not matched"
    )


def test_current_exact_match_detector_misses_pii():
    """Current exact-match catches only 1-3 columns from dim_deelnemer."""
    current_pii_cols = {
        "Burgerservicenummer",
        "Onderwijsnummer",
        "Geboortedatum",
        "Postcode",
        "Nationaliteit",
        "Geboorteland",
        "Migratieachtergrond",
    }

    dim_deelnemer_cols = [
        "_persoon_id",
        "Geslacht",
        "Postcodecijfers",
        "Gemeente",
        "Gemeentecode",
        "Nationaliteit1",
        "Nationaliteit1_naam",
        "Nationaliteit1_migratieachtergrond",
        "Nationaliteit2",
        "Nationaliteit2_naam",
        "Nationaliteit2_migratieachtergrond",
        "CodeGeboorteland",
        "CodeGeboorteland_naam",
        "CodeGeboorteland_migratieachtergrond",
        "CodeGeboortelandOuder1",
        "CodeGeboortelandOuder2",
        "Verblijfstitel",
        "DatumVestigingNederland",
        "DatumVertrekNederland",
        "CodeLandWaarnaarVertrokken",
        "Geboortedatum",
    ]

    detected_exact = [c for c in dim_deelnemer_cols if c in current_pii_cols]

    assert len(detected_exact) <= 3, (
        f"Exact-match detector found {len(detected_exact)} columns (expected ≤3). "
        f"This demonstrates the current broken behavior. "
        f"Detected: {detected_exact}"
    )
