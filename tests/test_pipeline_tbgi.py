"""Tests voor de TBGI-pipeline (end-to-end, TDD)."""

import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.indicatoren import (
    entree_indicatoren,
    ingeschreven_na_peildatum,
    rendement,
)
from mbo_bekostiging_bestanden.pipeline import run_star, run_tbgi_pipeline
from mbo_bekostiging_bestanden.quality import lees_status

DEMO_H16 = Path("data/01-raw/demo/h16")
TBGI = DEMO_H16 / "TBGI_25LX_2027_20251124.XML"


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------


def test_run_tbgi_pipeline_contains_expected_tables(tmp_path):
    result = run_tbgi_pipeline(TBGI, tmp_path)
    assert {"Inschrijving", "Teldatum", "Diploma", "Signaal"} <= result.keys()


def test_run_tbgi_pipeline_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_tbgi_pipeline("bestaat_niet.xml", tmp_path)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def test_run_tbgi_pipeline_writes_parquet(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    written = {f.stem for f in tmp_path.glob("*.parquet")}
    assert written == set(frames.keys())


def test_run_tbgi_pipeline_csv_format(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path, fmt="csv")
    written = {f.stem for f in tmp_path.glob("*.csv")}
    assert written == set(frames.keys())


# ---------------------------------------------------------------------------
# Datums correct getypeerd
# ---------------------------------------------------------------------------


def test_run_tbgi_pipeline_inschrijving_datum_is_date(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    assert frames["Inschrijving"]["DatumInschrijving"].dtype == pl.Date


def test_run_tbgi_pipeline_inschrijving_datum_value(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    assert frames["Inschrijving"]["DatumInschrijving"][0] == date(2024, 2, 1)


def test_run_tbgi_pipeline_diploma_datum_is_date(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    assert frames["Diploma"]["DatumBehaald"].dtype == pl.Date


def test_run_tbgi_pipeline_diploma_datum_value(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    assert frames["Diploma"]["DatumBehaald"][0] == date(2025, 6, 17)


def test_run_tbgi_pipeline_teldatum_is_date(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    assert frames["Teldatum"]["Teldatum"].dtype == pl.Date


# ---------------------------------------------------------------------------
# Floats correct getypeerd
# ---------------------------------------------------------------------------


def test_run_tbgi_pipeline_bblbolfactor_is_float(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    assert frames["Teldatum"]["BBLBOLFactor"].dtype == pl.Float64


def test_run_tbgi_pipeline_bijdrage_is_float(tmp_path):
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    col = frames["Teldatum"]["BijdrageInschrijvingAanDeelnemerswaarde"]
    assert col.dtype == pl.Float64


def test_run_tbgi_pipeline_leeftijd_is_int(tmp_path):
    """LeeftijdOpEenAugustusStudiejaar is int_field → Int64."""
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    assert frames["Teldatum"]["LeeftijdOpEenAugustusStudiejaar"].dtype == pl.Int64


def test_run_tbgi_pipeline_datumtijd_stays_string(tmp_path):
    """DatumTijdBepalingBekostigingsgrondslagen bevat datetime-string en blijft Utf8."""
    frames = run_tbgi_pipeline(TBGI, tmp_path)
    col = frames["Teldatum"]["DatumTijdBepalingBekostigingsgrondslagen"]
    assert col.dtype == pl.Utf8


# ---------------------------------------------------------------------------
# Parquet-output bewaart types
# ---------------------------------------------------------------------------


def test_run_tbgi_pipeline_parquet_preserves_date(tmp_path):
    run_tbgi_pipeline(TBGI, tmp_path)
    df = pl.read_parquet(tmp_path / "Inschrijving.parquet")
    assert df["DatumInschrijving"].dtype == pl.Date


def test_run_tbgi_pipeline_parquet_preserves_float(tmp_path):
    run_tbgi_pipeline(TBGI, tmp_path)
    df = pl.read_parquet(tmp_path / "Teldatum.parquet")
    assert df["BBLBOLFactor"].dtype == pl.Float64


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def test_run_auto_pipeline_routes_tbgi(tmp_path):
    """run_auto_pipeline herkent TBGI-bestanden en roept de juiste pipeline aan."""
    from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline

    frames = run_auto_pipeline(TBGI, tmp_path)
    assert "Inschrijving" in frames


# ---------------------------------------------------------------------------
# Inschrijving met alleen een lege Teldatum (#445)
# ---------------------------------------------------------------------------
# De demo plus een niet-bekostigde inschrijving (volgnummer 003) zoals DUO die
# levert: één <Teldatum> vol xsi:nil. Vóór #445 werd dat een Teldatum-rij met
# alleen BRIN/BSN/volgnummer, met domeinfouten en status fail.

LEGE_TELDATUM = Path("tests/fixtures/tbgi_lege_teldatum/TBGI_25LX_2027_20251124.XML")


@pytest.fixture(scope="module")
def prepared_lege_teldatum(tmp_path_factory) -> tuple[Path, dict[str, pl.DataFrame]]:
    doel = tmp_path_factory.mktemp("prepared") / "levering"
    return doel, run_tbgi_pipeline(LEGE_TELDATUM, doel)


@pytest.fixture(scope="module")
def ster_lege_teldatum(prepared_lege_teldatum, tmp_path_factory):
    doel = tmp_path_factory.mktemp("star")
    return doel, run_star([prepared_lege_teldatum[0]], doel)


def test_lege_teldatum_geeft_geen_teldatumrij(prepared_lege_teldatum):
    _, frames = prepared_lege_teldatum
    assert frames["Inschrijving"].height == 2
    assert frames["Teldatum"].height == 1
    assert (
        frames["Teldatum"].filter(pl.col("Inschrijvingvolgnummer") == "003").is_empty()
    )


def test_lege_teldatum_pipeline_publiceert_met_status_pass(prepared_lege_teldatum):
    doel, _ = prepared_lege_teldatum
    rapport = json.loads((doel / "quality.json").read_text(encoding="utf-8"))
    assert (rapport["status"], rapport["errors"]) == ("pass", [])


def test_ster_bouwt_met_inschrijving_zonder_teldatum(ster_lege_teldatum):
    doel, ster = ster_lege_teldatum
    assert lees_status(doel / "quality.json") == ("pass", 0)
    assert "003" in ster["fact_inschrijving"]["Inschrijvingvolgnummer"].to_list()
    assert ster["fact_bekostiging"].height == 1


def test_indicatoren_draaien_zonder_teldatumrij(ster_lege_teldatum):
    _, ster = ster_lege_teldatum
    jaren = ster["fact_inschrijving_schooljaar"]
    for indicator in ("jr", "dr"):
        assert isinstance(rendement(jaren, indicator), pl.DataFrame)
    assert isinstance(entree_indicatoren(jaren), pl.DataFrame)
    assert ingeschreven_na_peildatum(ster["fact_inschrijving"], [2025]) >= 0
