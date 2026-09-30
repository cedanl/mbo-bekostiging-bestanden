"""Dekking per levering × recordtype in ``quality.json`` (#295).

De overige checks kijken naar wat binnenkomt en naar de ster zelf, niet naar
wat onderweg verdwijnt: vóór #258 meldde de ster ``pass`` terwijl geen enkele
GRONDSLAG-BID het analysemodel bereikte. Dit is het vangnet daarvoor.
"""

import json
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden import star as star_module
from mbo_bekostiging_bestanden.pipeline import run_grondslag_pipeline, run_star
from mbo_bekostiging_bestanden.quality import (
    KwaliteitsFout,
    compile_quality_report,
    controleer_dekking,
    kwaliteitsmeldingen,
)

FIXTURE = Path("tests/fixtures/grondslag_pve/GRONDSLAG_IP_MBO_97XX_20251119_2025.csv")
L1, L2 = "L1", "L2"


def _records(levering: str, n: int, **kolommen) -> pl.DataFrame:
    return pl.DataFrame({"levering": [levering] * n, **kolommen})


def _rij(dekking: list[dict], levering: str, recordtype: str) -> dict:
    return next(
        r
        for r in dekking
        if r["levering"] == levering and r["recordtype"] == recordtype
    )


def test_telt_ingelezen_en_bereikt_per_levering():
    invoer = {"BPV": pl.concat([_records(L1, 3), _records(L2, 2)])}
    ster = {"fact_bpv": pl.concat([_records(L1, 3), _records(L2, 2)])}

    dekking = controleer_dekking(invoer, ster)

    assert _rij(dekking, L1, "BPV") == {
        "levering": L1,
        "recordtype": "BPV",
        "feit": "fact_bpv",
        "ingelezen": 3,
        "bereikt": 3,
        "ernst": None,
        "verklaring": None,
    }
    assert _rij(dekking, L2, "BPV")["bereikt"] == 2


def test_bekostigingsrecord_zonder_doorvertaling_is_error():
    """De situatie van vóór #258: BID ingelezen, niets in het feit."""
    invoer = {"BID": _records(L1, 2)}
    ster = {
        "fact_inschrijving": _records(L1, 1, Bron=["ISP"]),
        "fact_bekostiging_diploma": pl.DataFrame(),
    }

    rij = _rij(controleer_dekking(invoer, ster), L1, "BID")

    assert (rij["ingelezen"], rij["bereikt"], rij["ernst"]) == (2, 0, "error")


def test_bron_kolom_scheidt_recordtypes_in_een_gedeeld_feit():
    """TBG-i-Diploma in het feit maakt een ontbrekende BID niet ongezien."""
    invoer = {"BID": _records(L1, 1), "Diploma": _records(L1, 1)}
    ster = {"fact_bekostiging_diploma": _records(L1, 1, Bron=["TBGI"])}

    dekking = controleer_dekking(invoer, ster)

    assert _rij(dekking, L1, "BID")["bereikt"] == 0
    assert _rij(dekking, L1, "Diploma")["bereikt"] == 1


def test_ander_recordtype_zonder_doorvertaling_is_warning():
    rij = _rij(controleer_dekking({"KZD": _records(L1, 1)}, {}), L1, "KZD")
    assert rij["ernst"] == "warning"


def test_dip_met_gevulde_kolommen_in_het_feit_is_gedekt():
    """DIP heeft geen eigen feit maar voedt ``DIP_*``-kolommen (#326)."""
    invoer = {"DIP": _records(L1, 2)}
    ster = {
        "fact_inschrijving": _records(
            L1, 3, DIP_DatumResultaat=["2025-06-15", None, "2025-07-01"]
        )
    }

    rij = _rij(controleer_dekking(invoer, ster), L1, "DIP")

    assert (rij["feit"], rij["ingelezen"], rij["bereikt"], rij["ernst"]) == (
        "fact_inschrijving",
        2,
        2,
        None,
    )


def test_dip_zonder_gevulde_kolommen_is_warning():
    """Een regressie in de DIP→feit-projectie bleef ongezien: status bleef pass."""
    invoer = {"DIP": _records(L1, 2)}
    ster = {"fact_inschrijving": _records(L1, 3, DIP_DatumResultaat=[None] * 3)}

    rij = _rij(controleer_dekking(invoer, ster), L1, "DIP")

    assert (rij["bereikt"], rij["ernst"]) == (0, "warning")


def test_dip_zonder_dip_kolommen_in_het_feit_is_warning():
    invoer = {"DIP": _records(L1, 1)}
    ster = {"fact_inschrijving": _records(L1, 1)}

    assert _rij(controleer_dekking(invoer, ster), L1, "DIP")["ernst"] == "warning"


@pytest.mark.parametrize(
    ("recordtype", "kolom"), [("ISE", "ISE_DatumBegin"), ("ISG", "DatumInschrijving")]
)
def test_kolomdekking_geldt_ook_voor_ise_en_isg(recordtype, kolom):
    invoer = {recordtype: _records(L1, 1)}
    leeg = {"fact_inschrijving": _records(L1, 1, **{kolom: [None]})}
    gevuld = {"fact_inschrijving": _records(L1, 1, **{kolom: ["2025-08-01"]})}

    assert _rij(controleer_dekking(invoer, leeg), L1, recordtype)["ernst"] == "warning"
    assert _rij(controleer_dekking(invoer, gevuld), L1, recordtype)["ernst"] is None


def test_kolomdekking_is_per_levering():
    invoer = {"DIP": pl.concat([_records(L1, 1), _records(L2, 1)])}
    ster = {
        "fact_inschrijving": pl.concat(
            [
                _records(L1, 1, DIP_DatumResultaat=["2025-06-15"]),
                _records(L2, 1, DIP_DatumResultaat=[None]),
            ]
        )
    }

    dekking = controleer_dekking(invoer, ster)

    assert _rij(dekking, L1, "DIP")["ernst"] is None
    assert _rij(dekking, L2, "DIP")["ernst"] == "warning"


def test_bewust_niet_doorvertaald_heeft_een_verklaring_en_geen_ernst():
    rij = _rij(controleer_dekking({"VLP": _records(L1, 1)}, {}), L1, "VLP")
    assert rij["feit"] is None
    assert rij["ernst"] is None
    assert rij["verklaring"]


def test_onbekend_recordtype_is_warning():
    rij = _rij(controleer_dekking({"XYZ": _records(L1, 1)}, {}), L1, "XYZ")
    assert rij["ernst"] == "warning"
    assert rij["verklaring"]


def test_lege_invoer_en_tabellen_zonder_levering_tellen_niet():
    invoer = {"BPV": _records(L1, 0), "meta": pl.DataFrame({"x": [1]})}
    assert controleer_dekking(invoer, {}) == []


def test_volledig_vervangen_levering_is_verklaard():
    """Canonicalisatie (#174) haalt ook de details van een vervangen levering weg."""
    invoer = {"BPV": _records(L1, 2)}
    ster = {
        "fact_bpv": pl.DataFrame(),
        "meta_canonicalisatie": pl.DataFrame(
            {"levering": [L1], "vervangen_door": [L2]}
        ),
    }

    rij = _rij(controleer_dekking(invoer, ster), L1, "BPV")

    assert rij["ernst"] is None
    assert L2 in rij["verklaring"]


def test_gat_wordt_melding_en_telt_in_de_status():
    invoer = {"BID": _records(L1, 2)}
    rapport = compile_quality_report({}, invoer=invoer)

    fouten = [m.tekst for m in kwaliteitsmeldingen(rapport) if m.ernst == "error"]

    assert any("BID" in t and "fact_bekostiging_diploma" in t for t in fouten)
    assert rapport["summary"]["status"] == "fail"


@pytest.fixture(scope="module")
def grondslag_prepared(tmp_path_factory) -> Path:
    doel = tmp_path_factory.mktemp("prepared")
    run_grondslag_pipeline(FIXTURE, doel)
    return doel


def _quality(doel: Path) -> dict:
    return json.loads((doel / "quality.json").read_text(encoding="utf-8"))


def test_bid_bereikt_het_analysemodel(grondslag_prepared, tmp_path):
    run_star([grondslag_prepared], tmp_path)

    dekking = _quality(tmp_path)["star"]["dekking"]
    bid = next(r for r in dekking if r["recordtype"] == "BID")

    assert bid["bereikt"] == bid["ingelezen"] == 1
    assert bid["ernst"] is None


def test_bid_zonder_doorvertaling_faalt_de_run(
    grondslag_prepared, tmp_path, monkeypatch
):
    """Nabootsing van vóór #258: het feit bleef leeg."""
    monkeypatch.setattr(
        star_module, "_build_fact_bekostiging_diploma", lambda _: pl.DataFrame()
    )
    with pytest.raises(KwaliteitsFout):
        run_star([grondslag_prepared], tmp_path)

    assert _quality(tmp_path)["summary"]["status"] == "fail"


def test_demo_heeft_geen_dekkingsgaten(demo_prepared, tmp_path):
    prepared, dirs = demo_prepared
    run_star(dirs, tmp_path, relative_to=prepared)

    rapport = _quality(tmp_path)

    assert rapport["star"]["dekking"]
    assert [r for r in rapport["star"]["dekking"] if r["ernst"]] == []
    assert rapport["summary"]["status"] == "warn"
    assert rapport["summary"]["total_warnings"] == 1
