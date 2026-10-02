"""De brondata in ``02-prepared`` wordt atomair gepubliceerd (#414, #415).

Voorheen schreef de pipeline ``quality.json`` en de Parquets vóór de
kwaliteitspoort, rechtstreeks in de doelmap. Een foute run overschreef zo een
eerdere geldige levering, en een herverwerking liet tabellen staan die de
nieuwe bron niet meer bevat. Nu bouwt de pipeline naast de doelmap en vervangt
die alleen in zijn geheel; een foute run belandt in ``diagnose/``.
"""

import json
from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline
from mbo_bekostiging_bestanden.quality import KwaliteitsFout

DEMO_RO = Path("data/01-raw/demo/h15/RO_21CY_20250730_20250731.csv")
# Zonder AMO- en ISE-regels, die DEMO_RO wel heeft.
DEMO_RO_ZONDER_AMO = Path("data/01-raw/demo/h15/RO_27DV_20240731_20260324.csv")


def _inhoud(doel: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(doel)): p.read_bytes()
        for p in sorted(doel.rglob("*"))
        if p.is_file()
    }


def _ro_met_lege_brin(tmp_path: Path) -> Path:
    bron = tmp_path / "bron" / DEMO_RO.name
    bron.parent.mkdir()
    bron.write_text(
        DEMO_RO.read_text(encoding="utf-8").replace("VLP;21CY;", "VLP;;", 1),
        encoding="utf-8",
    )
    return bron


def test_herverwerking_laat_geen_tabellen_van_de_vorige_bron_staan(tmp_path):
    doel = tmp_path / "prepared"
    run_auto_pipeline(DEMO_RO, doel)
    assert (doel / "AMO.parquet").exists()

    frames = run_auto_pipeline(DEMO_RO_ZONDER_AMO, doel)

    assert sorted(p.stem for p in doel.glob("*.parquet")) == sorted(frames)


def test_fout_laat_de_vorige_publicatie_ongemoeid(tmp_path):
    doel = tmp_path / "prepared"
    run_auto_pipeline(DEMO_RO, doel)
    gepubliceerd = _inhoud(doel)

    with pytest.raises(KwaliteitsFout, match="diagnose"):
        run_auto_pipeline(_ro_met_lege_brin(tmp_path), doel)

    assert {k: v for k, v in _inhoud(doel).items() if "diagnose" not in k} == (
        gepubliceerd
    )
    rapport = json.loads((doel / "diagnose" / "quality.json").read_text("utf-8"))
    assert rapport["errors"]
    assert (doel / "diagnose" / "VLP.parquet").exists()


def test_fout_in_een_nieuwe_map_publiceert_niets(tmp_path):
    doel = tmp_path / "prepared"
    with pytest.raises(KwaliteitsFout):
        run_auto_pipeline(_ro_met_lege_brin(tmp_path), doel)
    assert [p.name for p in doel.iterdir()] == ["diagnose"]


def test_geslaagde_run_ruimt_een_oude_diagnose_op(tmp_path):
    doel = tmp_path / "prepared"
    with pytest.raises(KwaliteitsFout):
        run_auto_pipeline(_ro_met_lege_brin(tmp_path), doel)
    run_auto_pipeline(DEMO_RO, doel)
    assert not (doel / "diagnose").exists()
    assert (doel / "quality.json").exists()


def test_override_publiceert_ook_bij_errors(tmp_path):
    doel = tmp_path / "prepared"
    run_auto_pipeline(_ro_met_lege_brin(tmp_path), doel, fail_on_errors=False)
    assert (doel / "VLP.parquet").exists()
    assert not (doel / "diagnose").exists()


def test_geen_staging_resten_naast_de_doelmap(tmp_path):
    doel = tmp_path / "prepared"
    run_auto_pipeline(DEMO_RO, doel)
    with pytest.raises(KwaliteitsFout):
        run_auto_pipeline(_ro_met_lege_brin(tmp_path), doel)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bron", "prepared"]


def test_vervangt_geen_map_die_geen_brondata_bevat(tmp_path):
    """De doelmap wordt in zijn geheel vervangen; een verkeerd gekozen map
    (bijv. ``data/``) mag daarbij niet leeg raken."""
    doel = tmp_path / "eigen"
    doel.mkdir()
    (doel / "notities.txt").write_text("blijft staan", encoding="utf-8")

    with pytest.raises(ValueError, match="brondata"):
        run_auto_pipeline(DEMO_RO, doel)

    assert [p.name for p in doel.iterdir()] == ["notities.txt"]
