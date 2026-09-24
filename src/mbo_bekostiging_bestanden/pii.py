"""PII-gevoelige kolomdetectie.

Pattern matching omdat het star schema kolommen hernoemt:
- Postcode → Postcodecijfers, Postcodecijfers_*
- Nationaliteit → Nationaliteit1, Nationaliteit1_naam, *_migratieachtergrond
- Geboorteland → CodeGeboorteland, CodeGeboorteland_naam, CodeGeboortelandOuder*
- DatumVestiging* , DatumVertrek*, CodeLandWaarnaarVertrokken etc.
"""

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
    "Geslacht",
    "Vertrokken",
    "_persoon_id",  # Hashed ID is still person-bound
}


def detect_pii_columns(columns: list[str]) -> list[str]:
    """Detecteer PII-gevoelige kolommen via pattern matching.

    Handelt exact matches (BSN, ONr) en pattern matches (Postcode* → Postcodecijfers).
    Case-insensitive substring matching.
    """
    pii_found = []
    for col in columns:
        # Exact match eerst
        if col in _PII_PATTERNS:
            pii_found.append(col)
            continue
        # Pattern match: pattern is substring van kolomnaam (case-insensitive)
        col_lower = col.lower()
        for pattern in _PII_PATTERNS:
            if pattern.lower() in col_lower:
                pii_found.append(col)
                break
    return pii_found