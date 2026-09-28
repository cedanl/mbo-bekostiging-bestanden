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
    "DatumOverlijden",
    "Leeftijd",
    "RedenUitschrijving",
    "_persoon_id",  # Hashed ID is still person-bound
}


def detect_pii_columns(columns: list[str]) -> list[str]:
    """Geef de PII-gevoelige kolommen terug, in de volgorde van ``columns``.

    Een kolom is PII als een patroon (case-insensitive) als substring in de
    kolomnaam voorkomt; een exacte naam is daar een bijzonder geval van.
    """
    patronen = [p.lower() for p in _PII_PATTERNS]
    return [col for col in columns if any(p in col.lower() for p in patronen)]


def zichtbare_kolommen(columns: list[str], verberg_pii: bool = True) -> list[str]:
    """Kolommen voor weergave of download; standaard zonder PII (#213)."""
    if not verberg_pii:
        return list(columns)
    pii = set(detect_pii_columns(columns))
    return [col for col in columns if col not in pii]
