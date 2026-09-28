"""Het ster-artefact op schijf is gelijk aan wat ``run_star()`` teruggeeft (#189).

De snapshot-tests gebruiken de in-memory ster. Deze test dekt het wegschrijven:
een verkeerde map, een ontbrekende tabel of een schema dat bij het schrijven
verandert, valt hier op.
"""

import polars as pl
import pytest

from mbo_bekostiging_bestanden.pipeline import run_star


@pytest.fixture(scope="module")
def artefact(demo_prepared, tmp_path_factory):
    prepared, dirs = demo_prepared
    doel = tmp_path_factory.mktemp("star")
    return run_star(dirs, doel, relative_to=prepared), doel


def test_elke_tabel_staat_op_schijf_en_niets_meer(artefact):
    star, doel = artefact
    op_schijf = {p.stem for p in (doel / "datamodel").glob("*.parquet")}
    assert op_schijf == set(star)


def test_parquet_op_schijf_is_gelijk_aan_het_resultaat(artefact):
    star, doel = artefact
    for naam, verwacht in star.items():
        gelezen = pl.read_parquet(doel / "datamodel" / f"{naam}.parquet")
        assert gelezen.equals(verwacht), naam


def test_quality_json_staat_naast_het_datamodel(artefact):
    _, doel = artefact
    assert (doel / "quality.json").is_file()
