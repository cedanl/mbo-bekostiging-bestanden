"""``scenario`` in ``quality.json`` is expliciet, niet afgeleid uit het pad (#176)."""

import json
from pathlib import Path

import _utils

from mbo_bekostiging_bestanden.cli import build_parser
from mbo_bekostiging_bestanden.pipeline import run_star
from mbo_bekostiging_bestanden.quality import SCENARIO_ONBEKEND


def _scenario(doel: Path) -> str:
    return json.loads((doel / "quality.json").read_text(encoding="utf-8"))["scenario"]


def test_expliciet_scenario_ongeacht_pad(demo_prepared, tmp_path):
    prepared, dirs = demo_prepared
    doel = tmp_path / "productie-uitvoer"

    run_star(dirs, doel, relative_to=prepared, scenario="demo")

    assert _scenario(doel) == "demo"


def test_zonder_scenario_geen_padheuristiek(demo_prepared, tmp_path):
    prepared, dirs = demo_prepared
    doel = tmp_path / "demo"

    run_star(dirs, doel, relative_to=prepared)

    assert _scenario(doel) == SCENARIO_ONBEKEND


def test_cli_star_geeft_scenario_door(demo_prepared, tmp_path):
    prepared, dirs = demo_prepared
    doel = tmp_path / "uit"
    args = build_parser().parse_args(
        ["star", *map(str, dirs), "--output", str(doel), "--scenario", "demo"]
    )

    args.func(args)

    assert _scenario(doel) == "demo"


def test_app_scenario_komt_uit_config():
    assert _utils.scenario() == _utils.load_config()["data"]["scenario"]
