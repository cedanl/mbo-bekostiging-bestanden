"""KZD-resultaat wordt exact op de waardenlijst gematcht (#204).

``Niet behaald`` bevat de substring ``behaald``; een substring-match telde
niet-behaalde keuzedelen daardoor als behaald.
"""

import polars as pl

from mbo_bekostiging_bestanden.waardenlijsten import kzd_behaald


def _behaald(waarden: list[str | None]) -> list[bool | None]:
    df = pl.DataFrame({"Resultaat": waarden}, schema={"Resultaat": pl.Utf8})
    return df.select(kzd_behaald(pl.col("Resultaat")).alias("b"))["b"].to_list()


def test_ro_notatie():
    assert _behaald(["Behaald", "Niet behaald"]) == [True, False]


def test_grondslag_notatie():
    assert _behaald(["BEHAALD", "NIET BEHAALD"]) == [True, False]


def test_spaties_en_hoofdletters_genormaliseerd():
    assert _behaald([" behaald ", "niet  Behaald"]) == [True, False]


def test_onbekende_en_lege_waarde_is_null():
    assert _behaald(["Gedeeltelijk", None]) == [None, None]


def test_kzd_aantal_behaald_telt_niet_behaald_niet_mee(demo_star):
    """RO_21CY: K0161 Behaald, K0274 en K1056 Niet behaald.

    Handmatig geteld in de ruwe regels.
    """
    fi = demo_star["fact_inschrijving"].filter(
        pl.col("levering").str.contains("RO_21CY") & (pl.col("KZD_Aantal") > 0)
    )
    assert fi["KZD_Aantal"].sum() == 3
    assert fi["KZD_AantalBehaald"].sum() == 1


def test_fact_kzd_heeft_behaald_kolom(demo_star):
    kzd = demo_star["fact_kzd"].filter(pl.col("levering").str.contains("RO_21CY"))
    assert sorted(kzd["Behaald"].to_list()) == [False, False, True]
