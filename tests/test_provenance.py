"""Provenance van een run in ``quality.json`` en ``meta_leveringen`` (#300).

Achteraf moet vast te stellen zijn met welk bronbestand, welke PvE-versie,
welke referentiedata en welke code een output is gemaakt. Zonder
persoonsgegevens en zonder absolute paden: alleen bestandsnamen en hashes.
"""

import hashlib
import json
from importlib.metadata import version
from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.metadata import SCHEMA_DIR, schema_versie
from mbo_bekostiging_bestanden.pipeline import detect_bestandstype, run_star
from mbo_bekostiging_bestanden.referentiedata import METADATA

RAW = Path("data/01-raw/demo")


def _sha256(pad: Path) -> str:
    return hashlib.sha256(pad.read_bytes()).hexdigest()


def _ruw(levering: Path) -> Path:
    return next(p for p in RAW.rglob("*") if p.stem == levering.name)


@pytest.fixture(scope="module")
def star_run(demo_prepared, tmp_path_factory) -> tuple[Path, dict]:
    prepared, dirs = demo_prepared
    doel = tmp_path_factory.mktemp("star")
    star = run_star(dirs, doel, relative_to=prepared)
    return doel, star


def test_schema_versie_komt_uit_het_schema():
    for pad in SCHEMA_DIR.glob("*_schema.toml"):
        naam = pad.stem.removesuffix("_schema")
        assert f'schema_version = "{schema_versie(naam)}"' in pad.read_text()


def test_prepared_quality_noemt_bronbestand_met_hash(demo_prepared):
    _, dirs = demo_prepared
    for levering in dirs:
        rapport = json.loads((levering / "quality.json").read_text(encoding="utf-8"))
        ruw = _ruw(levering)
        bestandstype = detect_bestandstype(ruw)
        assert bestandstype is not None
        assert rapport["bronbestand"] == {
            "naam": ruw.name,
            "sha256": _sha256(ruw),
            "pve_versie": schema_versie(bestandstype),
        }


def test_star_quality_heeft_run_provenance(star_run):
    doel, _ = star_run
    rapport = json.loads((doel / "quality.json").read_text(encoding="utf-8"))

    herkomst = rapport["provenance"]

    assert herkomst["pakketversie"] == version("mbo-bekostiging-bestanden")
    assert herkomst["referentiemanifest_sha256"] == _sha256(
        METADATA / "referentiedata.json"
    )
    assert herkomst["git_commit"] is None or len(herkomst["git_commit"]) == 40
    assert all(d["bronbestand"]["sha256"] for d in rapport["deliveries"])


def test_meta_leveringen_noemt_bronbestand(star_run, demo_prepared):
    _, star = star_run
    _, dirs = demo_prepared
    meta = star["meta_leveringen"]

    for levering in dirs:
        rij = meta.filter(meta["levering"].str.ends_with(levering.name)).row(
            0, named=True
        )
        ruw = _ruw(levering)
        assert (rij["Bronbestand"], rij["Bronbestand_sha256"]) == (
            ruw.name,
            _sha256(ruw),
        )
        assert rij["PvE_versie"]


def test_provenance_bevat_geen_absolute_paden(star_run, demo_prepared):
    doel, _ = star_run
    prepared, _ = demo_prepared
    tekst = (doel / "quality.json").read_text(encoding="utf-8")
    for pad in (doel, prepared, RAW.resolve(), Path.home()):
        assert str(pad) not in tekst
