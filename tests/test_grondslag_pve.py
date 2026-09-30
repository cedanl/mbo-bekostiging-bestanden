"""GRONDSLAG-veldindeling positioneel getoetst tegen PvE 4.8.2 §17.5 (#127).

De fixture bevat per recordtype één regel in PvE-volgorde met een herkenbare
waarde per positie. Parsing is positioneel: een verkeerde veldvolgorde in
``grondslag_schema.toml`` zet waarden stil in de verkeerde kolom. De demo kan
dat niet aantonen (geen AMO, lege KZD-velden na ``Resultaat``).

Afwijking van het PvE, gedreven door de praktijk: VLP heeft in echte leveringen
een ``BRIN`` op positie 2 (zie de demo-levering). Deze fixture volgt die
praktijkvariant; de officiële VLP zonder BRIN staat, met een oracle rechtstreeks
uit §17.5, in ``tests/test_layoutvarianten.py`` (#236).
"""

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.decode import decode_frames, decode_grondslag
from mbo_bekostiging_bestanden.ingest import read_grondslag
from mbo_bekostiging_bestanden.quality import tel_parseverlies

FIXTURE = Path("tests/fixtures/grondslag_pve/GRONDSLAG_IP_MBO_97XX_20251119_2025.csv")
_PGN = ("PseudoNummer", "900000001")
_BRIN = ("BRIN", "97XX")

# Veld → ruwe waarde, in PvE-volgorde (Recordsoort weggelaten).
VERWACHT: dict[str, list[tuple[str, str]]] = {
    "VLP": [
        ("BRIN", "97XX"),
        ("Studiejaar", "2025"),
        ("DatumAanmaak", "20251119"),
        ("BekostigingsType", "V"),
    ],
    "PER": [
        _PGN,
        ("Leeftijd1", "17"),
        ("Leeftijd2", "18"),
        ("Leeftijd3", "19"),
        ("Leeftijd4", "20"),
        ("Geslacht", "V"),
        ("Postcodecijfers", "1234"),
        ("DatumOverlijden", "20300101"),
        ("DatumVestigingNederland", "20100202"),
        ("DatumVertrekNederland", "20290303"),
        ("CodeGeboorteland", "6030"),
        ("CodeGeboortelandOuder1", "6031"),
        ("CodeGeboortelandOuder2", "6032"),
        ("CodeLandWaarnaarVertrokken", "6033"),
        ("Verblijfstitel", "01"),
        ("Nationaliteit1", "0001"),
        ("Nationaliteit2", "0002"),
    ],
    "ISG": [
        _PGN,
        _BRIN,
        ("Inschrijvingvolgnummer", "INS1"),
        ("DatumInschrijving", "20240801"),
        ("DatumUitschrijvingGepland", "20270731"),
        ("DatumUitschrijvingWerkelijk", "20250615"),
        ("RedenUitschrijving", "08"),
    ],
    "ISP": [
        _PGN,
        _BRIN,
        ("Inschrijvingvolgnummer", "INS1"),
        ("DatumBegin", "20240801"),
        ("DatumEind", "20250615"),
        ("Opleidingcode", "25655"),
        ("Niveau", "MBO-4"),
        ("Leertraject", "BOL"),
        ("LocatiecodeVSV", "VSV001"),
        ("IndicatieBekostigbaar", "1"),
        ("Onderwijsaanbieder", "101A001"),
        ("Onderwijslocatie", "101L001"),
        ("Leerroute", "VM"),
        ("Leerroutefase", "F1"),
    ],
    "ISE": [
        _PGN,
        _BRIN,
        ("Inschrijvingvolgnummer", "INS1"),
        ("DatumBeginExtraOndersteuning", "20240901"),
        ("DatumEindExtraOndersteuning", "20241231"),
    ],
    "BPV": [
        _PGN,
        _BRIN,
        ("Inschrijvingvolgnummer", "INS1"),
        ("Volgnummer", "BPV7"),
        ("Afsluitdatum", "20240820"),
        ("DatumBegin", "20240901"),
        ("DatumEindGepland", "20250131"),
        ("DatumEindWerkelijk", "20250130"),
        ("Omvang", "400"),
        ("LeerbedrijfID", "1234567"),
        ("Opleidingcode", "25655"),
        ("CodeKeuzedeel", "K0067"),
    ],
    "BII": [
        _PGN,
        _BRIN,
        ("Inschrijvingvolgnummer", "INS1"),
        ("Teldatum", "20241001"),
        ("DatumTijdBepalingBekostigingsgrondslagen", "20241121104229"),
        ("StatusBepalingBekostigingsstatus", "V"),
        ("Bekostigingsstatus", "J"),
        ("InschrijvingVoorCorrectiefactor", "J"),
        ("BBLBOLFactor", "1.00"),
        ("PrijsfactorMBO", "1.25"),
        ("AantalBekostigdeVerblijfsjarenMBO", "0"),
        ("Verblijfsjaarfactor", "0.00"),
        ("BijdrageInschrijvingAanDeelnemerswaarde", "1234.567890"),
    ],
    "DIP": [
        _PGN,
        _BRIN,
        ("Resultaatvolgnummer", "RVN-DIP"),
        ("Opleidingcode", "25655"),
        ("DatumResultaat", "20250615"),
        ("IndicatieBekostigbaar", "1"),
        ("Inschrijvingvolgnummer", "INS1"),
        ("Onderwijsaanbieder", "101A001"),
    ],
    "BID": [
        _PGN,
        _BRIN,
        ("Resultaatvolgnummer", "RVN-DIP"),
        ("Niveau", "MBO-4"),
        ("IndicatieSpecialistendiploma", "N"),
        ("NiveauHoogstBekostigdeDiploma", "MBO-3"),
        ("IndicatieHoogstBekostigdeDiplomaIsSpecialist", "N"),
        ("DatumTijdBepalingBekostigingsgrondslagen", "20251121104229"),
        ("StatusBepalingBekostigingsstatus", "D"),
        ("Bekostigingsstatus", "J"),
        ("BijdrageDiplomawaarde", "1"),
    ],
    "AMO": [
        _PGN,
        _BRIN,
        ("ResultaatvolgnummerDiploma", "RVN-DIP"),
        ("Resultaatvolgnummer", "RVN-AMO"),
        ("CodeAMvBOnderdeel", "C0004"),
        ("Certificaat", "1"),
        ("DatumResultaat", "20250310"),
        ("Inschrijvingvolgnummer", "INS1"),
        ("Onderwijsaanbieder", "101A001"),
    ],
    "GEO": [
        _PGN,
        _BRIN,
        ("ResultaatvolgnummerDiploma", "RVN-DIP"),
        ("Resultaatvolgnummer", "RVN-GEO"),
        ("CodeGeneriekExamenonderdeel", "3005"),
        ("Eindcijfer", "7"),
        ("VrijstellingGeneriekExamenonderdeel", "MBO"),
        ("CijferIE", "74"),
        ("VrijstellingIE", "HBO"),
        ("CijferCE", "51"),
        ("VrijstellingCE", "VWO"),
        ("DatumResultaat", "20250311"),
        ("Inschrijvingvolgnummer", "INS1"),
        ("Onderwijsaanbieder", "101A001"),
    ],
    "KZD": [
        _PGN,
        _BRIN,
        ("ResultaatvolgnummerDiploma", "RVN-DIP"),
        ("Resultaatvolgnummer", "RVN-KZD"),
        ("CodeKeuzedeel", "K0067"),
        ("Resultaat", "BEHAALD"),
        ("Certificaat", "1"),
        ("DatumResultaat", "20250312"),
        ("Inschrijvingvolgnummer", "INS1"),
        ("Onderwijsaanbieder", "101A001"),
    ],
}


@pytest.fixture(scope="module")
def ruw():
    return read_grondslag(FIXTURE)


@pytest.mark.parametrize("recordtype", sorted(VERWACHT))
def test_velden_staan_op_pve_positie(ruw, recordtype):
    rij = ruw[recordtype].row(0, named=True)
    for veld, waarde in VERWACHT[recordtype]:
        assert rij[veld] == waarde, f"{recordtype}.{veld}"


@pytest.mark.parametrize("recordtype", ["AMO", "KZD"])
def test_geen_ro_veld_opleidingcode_diploma(ruw, recordtype):
    """``OpleidingcodeDiploma`` bestaat alleen in RO (§15), niet in de afslag (§17)."""
    assert "OpleidingcodeDiploma" not in ruw[recordtype].columns


def test_pve_conform_bestand_zonder_parseverlies(ruw):
    assert tel_parseverlies(ruw, decode_grondslag(ruw)) == {}


@pytest.mark.parametrize(
    ("recordtype", "datum"), [("AMO", date(2025, 3, 10)), ("KZD", date(2025, 3, 12))]
)
def test_datum_resultaat_landt_in_eigen_kolom(ruw, recordtype, datum):
    """Referentiedatum voor de periodekoppeling (``_PERIODE_REFERENTIEDATUM``)."""
    assert decode_grondslag(ruw)[recordtype]["DatumResultaat"][0] == datum


def test_geo_cijfers_met_komma_worden_niet_null():
    """Zelfde klasse als #208 (RO-equivalent: #259): Eindcijfer/CijferIE/CijferCE
    zijn N1..2/N2..3-decimaal in het PvE, geen integer."""
    frames = {
        "GEO": pl.DataFrame(
            {"Eindcijfer": ["6,5"], "CijferIE": ["7,0"], "CijferCE": ["6,0"]}
        )
    }
    geo = decode_frames(frames, "grondslag")["GEO"]
    assert geo["Eindcijfer"].to_list() == [6.5]
    assert geo["CijferIE"].to_list() == [7.0]
    assert geo["CijferCE"].to_list() == [6.0]
