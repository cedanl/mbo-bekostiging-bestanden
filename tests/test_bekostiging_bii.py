"""GRONDSLAG-BII/BID zijn numeriek en delen hun kolomnamen met TBG-i (#208).

PvE 4.8.2 noemt de velden in §16 (TBG-i) en §17 (GRONDSLAG) gelijk; de
bedragen en factoren hebben 2 of 6 decimalen. Het decimaalteken staat niet in
het PvE, dus zowel ``.`` als ``,`` wordt geaccepteerd.
"""

import polars as pl
import pytest

from mbo_bekostiging_bestanden.decode import decode_frames
from mbo_bekostiging_bestanden.metadata import load_schema
from mbo_bekostiging_bestanden.quality import tel_parseverlies

BII_BEDRAGEN = {
    "BBLBOLFactor": ("0,85", 0.85),
    "PrijsfactorMBO": ("1.25", 1.25),
    "Verblijfsjaarfactor": ("0,00", 0.0),
    "BijdrageInschrijvingAanDeelnemerswaarde": ("1234,567890", 1234.56789),
}


def _bii() -> dict[str, pl.DataFrame]:
    rij = {veld: [ruw] for veld, (ruw, _) in BII_BEDRAGEN.items()}
    rij["AantalBekostigdeVerblijfsjarenMBO"] = ["2"]
    return {"BII": pl.DataFrame(rij)}


def test_bii_bedragen_worden_getal():
    getypeerd = decode_frames(_bii(), "grondslag")["BII"]
    for veld, (_, verwacht) in BII_BEDRAGEN.items():
        assert getypeerd[veld].dtype == pl.Float64
        assert getypeerd[veld][0] == pytest.approx(verwacht)
    assert getypeerd["AantalBekostigdeVerblijfsjarenMBO"].to_list() == [2]


def test_bii_bedragen_zonder_parseverlies():
    ruw = _bii()
    assert tel_parseverlies(ruw, decode_frames(ruw, "grondslag")) == {}


def test_bid_bijdrage_wordt_getal():
    ruw = {"BID": pl.DataFrame({"BijdrageDiplomawaarde": ["512,25"]})}
    assert decode_frames(ruw, "grondslag")["BID"]["BijdrageDiplomawaarde"][0] == 512.25


def _numeriek(schema: dict) -> set[str]:
    return set(schema.get("int_fields", [])) | set(schema.get("float_fields", []))


@pytest.mark.parametrize(
    ("grondslag", "tbgi"), [("BII", "Teldatum"), ("BID", "Diploma")]
)
def test_bekostigingsvelden_heten_en_typeren_gelijk_aan_tbgi(grondslag, tbgi):
    """Eén concept, één kolom in fact_bekostiging: zelfde naam, zelfde typering."""
    gr = load_schema("grondslag")[grondslag]
    tb = load_schema("tbgi")[tbgi]
    gedeeld = set(gr["fields"]) & set(tb["fields"])
    assert _numeriek(tb) & set(gr["fields"]) <= _numeriek(gr)
    assert _numeriek(gr) <= gedeeld


def test_bii_bevat_alle_tbgi_bedragvelden():
    assert set(BII_BEDRAGEN) <= set(load_schema("grondslag")["BII"]["fields"])


def test_bii_en_tbgi_delen_kolommen_in_detail_bekostiging():
    """Een gemengde run heeft per bedrag één gevulde kolom, niet twee halflege."""
    from mbo_bekostiging_bestanden.transform import _bouw_detail_bekostiging

    sleutel = {"levering": ["L1"], "Inschrijvingvolgnummer": ["1"]}
    bii = decode_frames(_bii(), "grondslag")["BII"].with_columns(
        pl.lit("P1").alias("PseudoNummer"),
        **{k: pl.lit(v[0]) for k, v in sleutel.items()},
    )
    teldatum = decode_frames(
        {"Teldatum": pl.DataFrame({veld: ["1.00"] for veld in BII_BEDRAGEN})}, "tbgi"
    )["Teldatum"].with_columns(
        pl.lit("B1").alias("Burgerservicenummer"),
        **{k: pl.lit(v[0]) for k, v in sleutel.items()},
    )
    detail = _bouw_detail_bekostiging({"BII": bii, "Teldatum": teldatum})
    for veld in BII_BEDRAGEN:
        assert detail[veld].dtype == pl.Float64
        assert detail[veld].null_count() == 0
