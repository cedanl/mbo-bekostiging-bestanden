"""Tests voor wees-feiten (#89), sleuteluniciteit (#122) en niveau-dekking (#130)."""

import polars as pl

from mbo_bekostiging_bestanden.quality import (
    compile_quality_report,
    controleer_koppelingen,
    controleer_niveau,
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
    """Demo: de TBGI-inschrijving is parent van haar bekostiging (#196).

    Het TBGI-diploma is van een andere student, zonder inschrijving in de
    levering (PvE §16.1); gemeld, maar verklaard.
    """
    meldingen = controleer_koppelingen(demo_star)
    gemeld = {m.split(":")[0] for m in meldingen}
    assert gemeld == {"fact_bekostiging_diploma"}


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


# ---------------------------------------------------------------------------
# controleer_niveau (#130)
# ---------------------------------------------------------------------------


def _star_met_herkomst(herkomst: list[str]) -> dict[str, pl.DataFrame]:
    return {"fact_inschrijving": pl.DataFrame({"_niveau_herkomst": herkomst})}


def test_niveau_melding_telt_onbekend_en_sbb_nvt():
    star = _star_met_herkomst(
        ["bron", "crebo", "sbb", "sbb_nvt", "onbekend", "onbekend"]
    )
    assert controleer_niveau(star) == [
        "fact_inschrijving: 3 van 6 rijen zonder bekend niveau "
        "(2 code onbekend, 1 S-BB zonder niveau); ze vallen buiten JR/DR"
    ]


def test_niveau_melding_leeg_als_alle_niveaus_bekend():
    assert controleer_niveau(_star_met_herkomst(["bron", "crebo", "sbb"])) == []


def test_niveau_melding_leeg_zonder_herkomstkolom():
    assert controleer_niveau({"fact_inschrijving": pl.DataFrame({"x": [1]})}) == []


# --- Uniciteit van de schooljaar-grain (issue #200) --------------------------

_SCHOOLJAAR_GRAIN = ["BRIN", "_persoon_id", "Inschrijvingvolgnummer", "Schooljaar"]


def _schooljaren(*rijen: tuple[str, str, bool]) -> dict[str, pl.DataFrame]:
    """Schooljaar-fact met (levering, inschrijving, hoofd)-rijen in één jaar."""
    return {
        "fact_inschrijving_schooljaar": pl.DataFrame(
            {
                "levering": [r[0] for r in rijen],
                "BRIN": ["27DV"] * len(rijen),
                "_persoon_id": ["P"] * len(rijen),
                "Inschrijvingvolgnummer": [r[1] for r in rijen],
                "Schooljaar": [2025] * len(rijen),
                "_hoofdinschrijving": [r[2] for r in rijen],
                SLEUTEL: ["a"] * len(rijen),
            }
        )
    }


def test_dubbele_schooljaar_grain_wordt_gemeld():
    star = _schooljaren(("L1", "1", True), ("L1", "1", False))
    [melding] = controleer_sleuteluniciteit(star)
    assert "fact_inschrijving_schooljaar" in melding
    assert "L1: 2 rijen" in melding


def test_twee_hoofdinschrijvingen_in_een_schooljaar_worden_gemeld():
    star = _schooljaren(("L1", "1", True), ("L1", "2", True))
    [melding] = controleer_sleuteluniciteit(star)
    assert "hoofdinschrijving" in melding


def test_een_hoofdinschrijving_per_schooljaar_is_geen_melding():
    star = _schooljaren(("L1", "1", True), ("L1", "2", False))
    assert controleer_sleuteluniciteit(star) == []


def test_quality_report_telt_elk_geschonden_contract_als_error():
    star = {
        **_inschrijvingen(("L1", "a"), ("L1", "a")),
        **_schooljaren(("L1", "1", True), ("L1", "1", True)),
    }
    rapport = compile_quality_report(star)
    dubbel = rapport["star"]["key_duplicates"]
    assert dubbel["fact_inschrijving"]["duplicate_keys"] == 1
    assert dubbel["fact_inschrijving_schooljaar"]["duplicate_keys"] == 1
    assert dubbel["fact_inschrijving_schooljaar"]["sleutel"] == _SCHOOLJAAR_GRAIN
    assert rapport["summary"]["total_errors"] == 3


# --- Relatiecontract: optionele parent (issue #196) -------------------------


def _star_met_wees(feit: str, bron: str = "TBGI") -> dict[str, pl.DataFrame]:
    """Eén rij in ``feit`` uit recordtype ``bron`` die bij geen inschrijving hoort."""
    return {
        "fact_inschrijving": pl.DataFrame({"levering": ["T"], SLEUTEL: ["a"]}),
        feit: pl.DataFrame(
            {"levering": ["T"], SLEUTEL: [None], "Bron": [bron]},
            schema_overrides={SLEUTEL: pl.Utf8},
        ),
    }


def test_tbgi_diploma_zonder_inschrijving_is_verklaard_en_geen_fout():
    """PvE §16.1: TBG-i bevat de diploma's van kalenderjaar T-2, los van de
    inschrijvingen van studiejaar T-2; een diploma zonder inschrijving is normaal."""
    rapport = compile_quality_report(_star_met_wees("fact_bekostiging_diploma"))
    wees = rapport["star"]["orphaned_facts"]["fact_bekostiging_diploma"]
    assert (wees["orphaned_rows"], wees["explained_rows"]) == (1, 1)
    assert wees["explanation"]
    assert rapport["summary"]["total_errors"] == 0
    assert rapport["summary"]["total_warnings"] == 0


def test_grondslag_diploma_zonder_inschrijving_blijft_error():
    """Een BID koppelt via zijn DIP in dezelfde levering; zonder is het een bronfout."""
    rapport = compile_quality_report(_star_met_wees("fact_bekostiging_diploma", "BID"))
    wees = rapport["star"]["orphaned_facts"]["fact_bekostiging_diploma"]
    assert (wees["orphaned_rows"], wees["explained_rows"]) == (1, 0)
    assert rapport["summary"]["total_errors"] == 1


def test_wees_bekostiging_blijft_error():
    rapport = compile_quality_report(_star_met_wees("fact_bekostiging"))
    assert rapport["star"]["orphaned_facts"]["fact_bekostiging"]["explained_rows"] == 0
    assert rapport["summary"]["total_errors"] == 1


def test_melding_noemt_de_verklaring():
    [melding] = controleer_koppelingen(_star_met_wees("fact_bekostiging_diploma"))
    assert "verklaard" in melding


def test_demo_quality_heeft_geen_wees_errors(demo_star):
    wees = compile_quality_report(demo_star)["star"]["orphaned_facts"]
    assert all(m["orphaned_rows"] == m["explained_rows"] for m in wees.values())
