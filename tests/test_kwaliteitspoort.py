"""Een quality-``fail`` is een publicatiepoort, geen losse mededeling (#289).

Voorheen schreef ``run_star`` ook bij errors een ster en eindigde ``mbo star``
met exitcode 0. De fout wordt nu na het schrijven van ``quality.json`` geworpen;
het rapport blijft leesbaar in ``diagnose/`` (#363, zie ``test_publicatie.py``).
``fail_on_errors=False`` is de expliciete override voor exploratief werk en
staat in de provenance.
"""

import json
from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.cli import main
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline, run_star
from mbo_bekostiging_bestanden.quality import KwaliteitsFout

DEMO_RO = Path("data/01-raw/demo/h15/RO_21CY_20250730_20250731.csv")


@pytest.fixture
def prepared_zonder_fout(tmp_path) -> Path:
    doel = tmp_path / "prepared" / DEMO_RO.stem
    run_auto_pipeline(DEMO_RO, doel)
    return doel


def _status(star_dir: Path) -> str:
    rapport = json.loads((star_dir / "quality.json").read_text(encoding="utf-8"))
    return rapport["summary"]["status"]


def test_run_star_faalt_bij_quality_errors_maar_laat_het_rapport_staan(
    prepared_met_fout, tmp_path
):
    doel = tmp_path / "star"
    with pytest.raises(KwaliteitsFout, match="quality.json"):
        run_star(prepared_met_fout[1], doel)
    assert _status(doel / "diagnose") == "fail"


def test_override_bouwt_de_ster_en_legt_dat_vast_in_de_provenance(
    prepared_met_fout, tmp_path
):
    doel = tmp_path / "star"
    star = run_star(prepared_met_fout[1], doel, fail_on_errors=False)
    assert "fact_inschrijving" in star
    rapport = json.loads((doel / "quality.json").read_text(encoding="utf-8"))
    assert rapport["summary"]["status"] == "fail"
    assert rapport["provenance"]["kwaliteitsfouten_toegestaan"] is True


def test_schone_run_slaagt_zonder_override(prepared_zonder_fout, tmp_path):
    doel = tmp_path / "star"
    run_star([prepared_zonder_fout], doel)
    rapport = json.loads((doel / "quality.json").read_text(encoding="utf-8"))
    assert rapport["summary"]["status"] != "fail"
    assert rapport["provenance"]["kwaliteitsfouten_toegestaan"] is False


def test_cli_star_eindigt_niet_nul_bij_quality_errors(
    prepared_met_fout, tmp_path, monkeypatch, capsys
):
    doel = tmp_path / "star"
    monkeypatch.setattr(
        "sys.argv", ["mbo", "star", str(prepared_met_fout[1][0]), "--output", str(doel)]
    )
    with pytest.raises(SystemExit) as uit:
        main()
    assert uit.value.code == 3
    assert "quality.json" in capsys.readouterr().err
    assert _status(doel / "diagnose") == "fail"


def test_cli_override_geeft_exitcode_nul_en_meldt_de_status(
    prepared_met_fout, tmp_path, monkeypatch, capsys
):
    doel = tmp_path / "star"
    monkeypatch.setattr(
        "sys.argv",
        [
            "mbo",
            "star",
            str(prepared_met_fout[1][0]),
            "--output",
            str(doel),
            "--allow-quality-errors",
        ],
    )
    main()
    assert "fail" in capsys.readouterr().out


def _demo_met_lege_brin(tmp_path: Path) -> Path:
    """Demo-RO met een lege VLP-BRIN: een error-domeinafwijking (#238)."""
    bron = tmp_path / DEMO_RO.name
    bron.write_text(
        DEMO_RO.read_text(encoding="utf-8").replace("VLP;21CY;", "VLP;;", 1),
        encoding="utf-8",
    )
    return bron


def _demo_zonder_eerste_isp(tmp_path: Path) -> Path:
    """Demo-RO met één ISP-regel minder dan het sluitrecord telt (#413)."""
    regels = DEMO_RO.read_text(encoding="utf-8").splitlines(keepends=True)
    eerste_isp = next(i for i, r in enumerate(regels) if r.startswith("ISP;"))
    bron = tmp_path / DEMO_RO.name
    bron.write_text("".join(regels[:eerste_isp] + regels[eerste_isp + 1 :]))
    return bron


@pytest.mark.parametrize(
    "bron_met_fout", [_demo_met_lege_brin, _demo_zonder_eerste_isp]
)
def test_cli_verwerk_eindigt_exit_3_bij_quality_errors(
    bron_met_fout, tmp_path, monkeypatch
):
    """``mbo verwerk`` eindigt met exitcode 3 (niet 0) bij quality-errors (#361).

    Een SLR-mismatch is een onvolledige levering en dus een error (#413).
    """
    bron = bron_met_fout(tmp_path)
    doel = tmp_path / "prepared"
    monkeypatch.setattr("sys.argv", ["mbo", "verwerk", str(bron), str(doel)])
    with pytest.raises(SystemExit) as uit:
        main()
    assert uit.value.code == 3


def test_cli_verwerk_met_allow_quality_errors_exit_nul(tmp_path, monkeypatch):
    """``mbo verwerk --allow-quality-errors`` slaat quality-errors over (#361)."""
    bron = _demo_met_lege_brin(tmp_path)
    doel = tmp_path / "prepared"
    monkeypatch.setattr(
        "sys.argv", ["mbo", "verwerk", str(bron), str(doel), "--allow-quality-errors"]
    )
    main()  # Should not raise SystemExit


def test_leveringsrapport_legt_de_override_vast(tmp_path):
    """#394: een prepared-map met errors laat zien of ze bewust zijn toegestaan."""
    demo = DEMO_RO
    standaard = tmp_path / "standaard"
    toegestaan = tmp_path / "toegestaan"
    run_auto_pipeline(demo, standaard)
    run_auto_pipeline(demo, toegestaan, fail_on_errors=False)

    def vlag(map_: Path) -> bool:
        rapport = json.loads((map_ / "quality.json").read_text(encoding="utf-8"))
        return rapport["kwaliteitsfouten_toegestaan"]

    assert vlag(standaard) is False
    assert vlag(toegestaan) is True
