"""Uniciteit op de business key van elk detailfeit en een vaste BRIN-kolom (#328).

De keys staan in ``contracts.DETAIL_GRAIN`` (#327, ``docs/datamodel.md``). De
twee-instellingenproef uit de audit: dezelfde RO-inhoud onder een tweede BRIN
geeft op een key zonder ``levering`` dubbelen, op de vastgelegde key niet.
De tweede levering is een kopie in ``tmp_path``; de demo zelf blijft ongewijzigd.
"""

import re
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden import ernst
from mbo_bekostiging_bestanden.contracts import DETAIL_GRAIN
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline
from mbo_bekostiging_bestanden.quality import (
    compile_quality_report,
    kwaliteitsmeldingen,
)
from mbo_bekostiging_bestanden.stack import leveringslabels, stack_prepared
from mbo_bekostiging_bestanden.star import build_star

DEMO = Path("data/01-raw/demo")
RO = next(DEMO.glob("h15/RO_27DV_*.csv"))
GRONDSLAG = next(DEMO.glob("h17/GRONDSLAG_*.csv"))
_TWEEDE_BRIN = "98YY"


def _als_andere_instelling(bron: Path, doelmap: Path) -> Path:
    """Kopie van ``bron`` met ``_TWEEDE_BRIN`` in bestandsnaam en VLP."""
    brin = bron.name.split("_")[1]
    kopie = doelmap / bron.name.replace(brin, _TWEEDE_BRIN)
    regels = bron.read_text(encoding="utf-8").splitlines()
    regels[0] = regels[0].replace(brin, _TWEEDE_BRIN)
    kopie.write_text("\n".join(regels) + "\n", encoding="utf-8")
    return kopie


def _ster(tmp_path: Path, *bronnen: Path) -> tuple[dict, dict]:
    mappen = []
    for bron in bronnen:
        doel = tmp_path / "prepared" / bron.stem
        run_auto_pipeline(bron, doel)
        mappen.append(doel)
    invoer = stack_prepared(mappen, labels=leveringslabels(mappen, tmp_path))
    return build_star(invoer), invoer


@pytest.fixture(scope="module")
def twee_instellingen(tmp_path_factory) -> tuple[dict, dict]:
    tmp = tmp_path_factory.mktemp("twee")
    return _ster(tmp, RO, _als_andere_instelling(RO, tmp))


def _dubbelen(star: dict, invoer: dict | None = None) -> dict[str, int]:
    rapport = compile_quality_report(star, invoer=invoer)
    return {
        feit: rapport["star"]["key_duplicates"][feit]["duplicate_keys"]
        for feit in DETAIL_GRAIN
    }


def test_twee_instellingen_geven_geen_dubbelen_op_de_business_key(twee_instellingen):
    star, invoer = twee_instellingen
    assert star["fact_bpv"].height > 0
    assert _dubbelen(star, invoer) == dict.fromkeys(DETAIL_GRAIN, 0)


def test_zonder_levering_zou_de_proef_wel_dubbelen_geven(twee_instellingen):
    """Het contrast uit #327: de key zonder ``levering`` is niet uniek."""
    star, _ = twee_instellingen
    key = [k for k in DETAIL_GRAIN["fact_bpv"] if k != "levering"]
    assert star["fact_bpv"].select(key).is_duplicated().any()


@pytest.mark.parametrize("feit", DETAIL_GRAIN)
def test_dubbele_detailrij_is_een_error(demo_star, demo_stacked, feit):
    kapot = demo_star | {feit: pl.concat([demo_star[feit], demo_star[feit].head(1)])}
    rapport = compile_quality_report(kapot, invoer=demo_stacked)
    assert rapport["star"]["key_duplicates"][feit]["duplicate_keys"] == 1
    assert rapport["summary"]["status"] == "fail"


@pytest.mark.parametrize(
    "bronnen", [(RO,), (GRONDSLAG,), (RO, GRONDSLAG)], ids=["ro", "grondslag", "mix"]
)
def test_brin_in_elk_detailfeit_en_gevuld_bij_een_parent(tmp_path, bronnen):
    star, _ = _ster(tmp_path, *bronnen)
    for feit in DETAIL_GRAIN:
        df = star[feit]
        if df.is_empty():
            continue
        assert "BRIN" in df.columns, feit
        met_parent = df.join(
            star["fact_inschrijving"].select("_inschrijving_periode_id"),
            on="_inschrijving_periode_id",
        )
        assert met_parent["BRIN"].null_count() == 0, feit


def test_brin_komt_van_de_parent_inschrijving(twee_instellingen):
    star, _ = twee_instellingen
    bpv = star["fact_bpv"].join(
        star["fact_inschrijving"].select(
            "_inschrijving_periode_id", pl.col("BRIN").alias("parent")
        ),
        on="_inschrijving_periode_id",
    )
    assert set(bpv["BRIN"]) == {"27DV", _TWEEDE_BRIN}
    assert (bpv["BRIN"] == bpv["parent"]).all()


@pytest.fixture(scope="module")
def brin_conflict(tmp_path_factory) -> tuple[dict, dict]:
    """GRONDSLAG-kopie waarin één BPV-regel een andere BRIN draagt dan haar ISP."""
    tmp = tmp_path_factory.mktemp("conflict")
    kopie = tmp / GRONDSLAG.name
    regels = GRONDSLAG.read_text(encoding="utf-8").splitlines()
    i = next(i for i, r in enumerate(regels) if r.startswith("BPV;"))
    velden = regels[i].split(";")
    velden[2] = _TWEEDE_BRIN
    regels[i] = ";".join(velden)
    kopie.write_text("\n".join(regels) + "\n", encoding="utf-8")
    return _ster(tmp, kopie)


def test_brin_conflict_wordt_geteld_en_gemeld(brin_conflict):
    """#357: de parent wint, maar de afwijkende bronwaarde verdween stil."""
    star, invoer = brin_conflict
    rapport = compile_quality_report(star, invoer=invoer)

    assert rapport["star"]["brin_conflict"]["fact_bpv"] == 1
    assert sum(rapport["star"]["brin_conflict"].values()) == 1
    meldingen = [m for m in kwaliteitsmeldingen(rapport) if "BRIN" in m.tekst]
    assert [m.ernst for m in meldingen] == [ernst.WARNING]


def test_brin_conflict_bewaart_de_bronwaarde(brin_conflict):
    star, _ = brin_conflict
    conflict = star["fact_bpv"].filter(pl.col("_brin_bron").is_not_null())
    assert conflict.select("BRIN", "_brin_bron").rows() == [("27DV", _TWEEDE_BRIN)]


def test_gelijke_of_ontbrekende_bron_brin_is_geen_conflict(twee_instellingen):
    """RO-detailrecords hebben geen BRIN; GRONDSLAG-BRIN gelijk aan de parent."""
    star, invoer = twee_instellingen
    rapport = compile_quality_report(star, invoer=invoer)
    assert rapport["star"]["brin_conflict"] == dict.fromkeys(DETAIL_GRAIN, 0)


def test_demo_heeft_geen_brin_conflict(demo_star, demo_stacked):
    rapport = compile_quality_report(demo_star, invoer=demo_stacked)
    assert rapport["star"]["brin_conflict"] == dict.fromkeys(DETAIL_GRAIN, 0)


def test_datamodel_docs_noemen_dezelfde_business_key():
    """``docs/datamodel.md`` en ``DETAIL_GRAIN`` zijn één contract (#327)."""
    tekst = Path("docs/datamodel.md").read_text(encoding="utf-8")
    gedocumenteerd = {}
    for feiten, key in re.findall(r"^\| (`fact_[^|]+) \| (`[^|]+) \|", tekst, re.M):
        for feit in re.findall(r"`(fact_\w+)`", feiten):
            gedocumenteerd[feit] = tuple(re.findall(r"`(\w+)`", key))
    assert {f: gedocumenteerd.get(f) for f in DETAIL_GRAIN} == DETAIL_GRAIN
