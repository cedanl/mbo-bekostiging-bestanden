"""Tests voor PII-kolomdetectie."""

from mbo_bekostiging_bestanden.pii import detect_pii_columns


def test_exacte_pii_kolommen_worden_herkend():
    kolommen = ["Burgerservicenummer", "Onderwijsnummer", "PseudoNummer", "Geslacht"]
    assert detect_pii_columns(kolommen) == kolommen


def test_patroon_match_via_substring():
    assert "CodeLandWaarnaarVertrokken" in detect_pii_columns(
        ["CodeLandWaarnaarVertrokken"]
    )


def test_niet_pii_kolommen_blijven_gespaard():
    pii = detect_pii_columns(
        ["_persoon_id", "Opleidingcode", "BekostigdeEenheden", "SLR-status", "_bron"]
    )
    assert pii == ["_persoon_id"]


def test_alle_kolommen_van_demo_dim_deelnemer_zijn_pii(demo_star):
    """dim_deelnemer bevat uitsluitend persoonskenmerken; elke kolom telt als PII."""
    kolommen = demo_star["dim_deelnemer"].columns
    gemist = set(kolommen) - set(detect_pii_columns(kolommen))
    assert not gemist, f"PII-detector mist kolommen op dim_deelnemer: {gemist}"


def test_niet_persoonsgebonden_dimensies_bevatten_geen_pii(demo_star):
    for naam in ("dim_opleiding", "dim_instelling"):
        kolommen = demo_star[naam].columns
        assert detect_pii_columns(kolommen) == [], naam


def test_star_bevat_nergens_ruwe_persoonsidentifiers(demo_star, tbgi_star):
    """Alleen het pseudoniem ``_persoon_id`` mag het star schema in (#125).

    TBGI-kindrijen dragen sinds #125 BSN/ONr tot in de detailtabellen; geen
    enkel star-feit of -dimensie mag die doorgeven.
    """
    ruw = {"Burgerservicenummer", "Onderwijsnummer", "PseudoNummer"}
    for star in (demo_star, tbgi_star):
        for naam, tabel in star.items():
            assert not ruw & set(tabel.columns), naam


def test_alle_fact_tabellen_detecteren_pii_kolommen(demo_star, tbgi_star):
    """Alle fact-tabellen moeten PII-kolommen herkennen.

    Bijv. DatumOverlijden, Leeftijd, RedenUitschrijving.
    Dit voorkomt dat ze per ongeluk in CSV-downloads komen.
    """
    nieuwe_patterns = ["DatumOverlijden", "Leeftijd", "RedenUitschrijving"]
    for star in (demo_star, tbgi_star):
        for naam, tabel in star.items():
            if not naam.startswith("fact_"):
                continue
            if tabel.is_empty():
                continue
            pii_gevonden = detect_pii_columns(tabel.columns)
            assert "_persoon_id" in pii_gevonden, (
                f"{naam}: _persoon_id niet gedetecteerd als PII"
            )
            for kolom in tabel.columns:
                if any(p in kolom for p in nieuwe_patterns):
                    assert kolom in pii_gevonden, (
                        f"{naam}: {kolom} niet gedetecteerd als PII"
                    )
