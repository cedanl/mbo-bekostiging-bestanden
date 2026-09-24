"""Tests voor het signaleren van wees-feiten in het star schema (issue #89)."""

import polars as pl

from mbo_bekostiging_bestanden.quality import controleer_koppelingen

SLEUTEL = "_inschrijving_periode_id"


def _star(**feiten: pl.DataFrame) -> dict[str, pl.DataFrame]:
    fact_inschrijving = pl.DataFrame({SLEUTEL: ["a", "b"]})
    return {
        "fact_inschrijving": fact_inschrijving,
        "dim_opleiding": pl.DataFrame(),
        **feiten,
    }


def test_volledig_gekoppelde_feiten_geven_geen_waarschuwing():
    star = _star(fact_bpv=pl.DataFrame({SLEUTEL: ["a", "b", "b"]}))
    assert controleer_koppelingen(star) == []


def test_lege_feiten_en_dimensies_worden_overgeslagen():
    star = _star(fact_amo=pl.DataFrame(), fact_kzd=pl.DataFrame({SLEUTEL: []}))
    assert controleer_koppelingen(star) == []


def test_deels_wees_feit_meldt_aantal_en_aandeel():
    star = _star(fact_geo=pl.DataFrame({SLEUTEL: ["a", None, "x", "b"]}))
    [melding] = controleer_koppelingen(star)
    assert "fact_geo" in melding
    assert "2 van 4" in melding
    assert "50%" in melding


def test_volledig_wees_feit_wordt_expliciet_benoemd():
    star = _star(
        fact_bekostiging=pl.DataFrame({SLEUTEL: [None]}, schema={SLEUTEL: pl.Utf8})
    )
    [melding] = controleer_koppelingen(star)
    assert "fact_bekostiging" in melding
    assert "geen enkele rij" in melding


def test_demo_star_signaleert_alleen_de_wees_bekostiging(demo_star):
    """Demo: TBGI-bekostiging (25LX) hoort bij geen enkele ISP-levering."""
    meldingen = controleer_koppelingen(demo_star)
    gemeld = {m.split(":")[0] for m in meldingen}
    assert gemeld == {"fact_bekostiging", "fact_bekostiging_diploma"}
