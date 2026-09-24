"""Tests voor wees-feiten (#89) en uniciteit van de periodesleutel (#122)."""

import polars as pl

from mbo_bekostiging_bestanden.quality import (
    controleer_koppelingen,
    controleer_sleuteluniciteit,
)

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


# --- Uniciteit van de periodesleutel (issue #122) ---------------------------


def _inschrijvingen(*rijen: tuple[str, str | None]) -> dict[str, pl.DataFrame]:
    """fact_inschrijving met (levering, sleutel)-rijen."""
    return {
        "fact_inschrijving": pl.DataFrame(
            {"levering": [r[0] for r in rijen], SLEUTEL: [r[1] for r in rijen]},
            schema={"levering": pl.Utf8, SLEUTEL: pl.Utf8},
        )
    }


def test_unieke_periodesleutels_geven_geen_melding():
    star = _inschrijvingen(("L1", "a"), ("L1", "b"), ("L2", "c"))
    assert controleer_sleuteluniciteit(star) == []


def test_dubbele_periodesleutel_meldt_aantal_per_levering():
    star = _inschrijvingen(("L1", "a"), ("L1", "a"), ("L1", "a"), ("L2", "b"))
    [melding] = controleer_sleuteluniciteit(star)
    assert "fact_inschrijving" in melding
    assert "1 sleutel" in melding
    assert "L1: 3 rijen" in melding
    assert "L2" not in melding


def test_lege_periodesleutels_tellen_niet_als_dubbel():
    star = _inschrijvingen(("L1", None), ("L1", None))
    assert controleer_sleuteluniciteit(star) == []


def test_ontbrekende_sleutelkolom_wordt_overgeslagen():
    assert controleer_sleuteluniciteit({"fact_inschrijving": pl.DataFrame()}) == []
    assert controleer_sleuteluniciteit({}) == []


def test_demo_star_heeft_unieke_periodesleutels(demo_star, tbgi_star):
    assert controleer_sleuteluniciteit(demo_star) == []
    assert controleer_sleuteluniciteit(tbgi_star) == []
