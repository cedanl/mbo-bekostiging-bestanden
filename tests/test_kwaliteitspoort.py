"""Een quality-``fail`` is een publicatiepoort, geen losse mededeling (#289).

Voorheen schreef ``run_star`` ook bij errors een ster en eindigde ``mbo star``
met exitcode 0. De fout wordt nu na het schrijven van ``quality.json`` geworpen
(het rapport blijft leesbaar); ``fail_on_errors=False`` is de expliciete override
voor exploratief werk en staat in de provenance.
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
    assert _status(doel) == "fail"


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
    assert _status(doel) == "fail"


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
