"""De ster wordt atomair gepubliceerd; fail-output oogt niet als publicatie (#363).

Voorheen stond bij ``fail`` een volledig ogende ``datamodel/`` op schijf, die
een downstream-proces dat alleen naar bestanden kijkt als gepubliceerd kon
oppakken. Nu bouwt ``run_star`` in een staging-map en promoveert alleen bij
``pass``/``warn`` of met de override; anders komt de output in ``diagnose/``.
"""

import json
from pathlib import Path

import pytest

from mbo_bekostiging_bestanden import pipeline
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline, run_star
from mbo_bekostiging_bestanden.publicatie import lees_ster
from mbo_bekostiging_bestanden.quality import KwaliteitsFout

DEMO_RO = Path("data/01-raw/demo/h15/RO_21CY_20250730_20250731.csv")
KERNTABEL = Path("datamodel") / "fact_inschrijving.parquet"


@pytest.fixture
def prepared_zonder_fout(tmp_path) -> Path:
    doel = tmp_path / "prepared" / DEMO_RO.stem
    run_auto_pipeline(DEMO_RO, doel)
    return doel


def _rapport(pad: Path) -> dict:
    return json.loads((pad / "quality.json").read_text(encoding="utf-8"))


def _inhoud(doel: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(doel)): p.read_bytes()
        for p in sorted(doel.rglob("*"))
        if p.is_file()
    }


def test_fail_publiceert_niet_maar_bewaart_de_diagnose(prepared_met_fout, tmp_path):
    doel = tmp_path / "star"
    with pytest.raises(KwaliteitsFout, match="diagnose"):
        run_star(prepared_met_fout[1], doel)

    assert not (doel / "datamodel").exists()
    assert not (doel / "quality.json").exists()
    diagnose = doel / "diagnose"
    assert (diagnose / KERNTABEL).exists()
    assert _rapport(diagnose)["summary"]["status"] == "fail"
    assert _rapport(diagnose)["provenance"]["gepubliceerd"] is False


def test_fail_laat_de_vorige_publicatie_ongemoeid(
    prepared_zonder_fout, prepared_met_fout, tmp_path
):
    doel = tmp_path / "star"
    run_star([prepared_zonder_fout], doel)
    gepubliceerd = _inhoud(doel)

    with pytest.raises(KwaliteitsFout):
        run_star(prepared_met_fout[1], doel)

    na = {k: v for k, v in _inhoud(doel).items() if not k.startswith("diagnose")}
    assert na == gepubliceerd


def test_onderbroken_run_laat_geen_halve_ster_achter(
    prepared_zonder_fout, tmp_path, monkeypatch
):
    doel = tmp_path / "star"
    run_star([prepared_zonder_fout], doel)
    gepubliceerd = _inhoud(doel)
    echte_export = pipeline.export_frames

    def onderbroken(frames, map_, **kwargs):
        echte_export(dict(list(frames.items())[:2]), map_, **kwargs)
        raise KeyboardInterrupt

    monkeypatch.setattr(pipeline, "export_frames", onderbroken)
    with pytest.raises(KeyboardInterrupt):
        run_star([prepared_zonder_fout], doel)

    assert _inhoud(doel) == gepubliceerd
    assert sorted(p.name for p in doel.iterdir()) == ["datamodel", "quality.json"]


def test_override_publiceert_en_legt_dat_vast(prepared_met_fout, tmp_path):
    doel = tmp_path / "star"
    run_star(prepared_met_fout[1], doel, fail_on_errors=False)

    assert (doel / KERNTABEL).exists()
    provenance = _rapport(doel)["provenance"]
    assert provenance["gepubliceerd"] is True
    assert provenance["kwaliteitsfouten_toegestaan"] is True


def test_publicatie_ruimt_een_verouderde_diagnose_op(
    prepared_zonder_fout, prepared_met_fout, tmp_path
):
    doel = tmp_path / "star"
    with pytest.raises(KwaliteitsFout):
        run_star(prepared_met_fout[1], doel)
    run_star([prepared_zonder_fout], doel)

    assert not (doel / "diagnose").exists()
    assert _rapport(doel)["provenance"]["gepubliceerd"] is True


def test_lees_ster_weigert_standaard_een_ster_met_status_fail(
    prepared_met_fout, tmp_path
):
    doel = tmp_path / "star"
    run_star(prepared_met_fout[1], doel, fail_on_errors=False)

    with pytest.raises(KwaliteitsFout, match="fail"):
        lees_ster(doel)
    assert "fact_inschrijving" in lees_ster(doel, fouten_toestaan=True)


def test_lees_ster_leest_een_schone_publicatie(prepared_zonder_fout, tmp_path):
    doel = tmp_path / "star"
    star = run_star([prepared_zonder_fout], doel)

    gelezen = lees_ster(doel)
    assert set(gelezen) == set(star)


def test_lees_ster_weigert_een_map_zonder_publicatie(tmp_path):
    with pytest.raises(FileNotFoundError):
        lees_ster(tmp_path)
