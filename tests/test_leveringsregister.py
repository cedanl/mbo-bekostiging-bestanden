"""Eén leveringsregister voor ster, metadata en quality.json (#188).

Het leveringslabel komt uit :func:`stack_prepared` (bijv. ``h15/RO_27DV_…``).
``meta_leveringen`` bevat elke gestapelde levering — ook TBGI zonder VLP/SLR —
en ``quality.json`` gebruikt hetzelfde label, zodat kwaliteitsregels aan de
feiten te koppelen zijn.
"""

import json
import shutil

import polars as pl

from mbo_bekostiging_bestanden.pipeline import run_star
from mbo_bekostiging_bestanden.stack import leveringslabels


def _leveringen_in_feiten(star: dict[str, pl.DataFrame]) -> set[str]:
    return {
        lev
        for naam, df in star.items()
        if naam.startswith("fact_") and "levering" in df.columns
        for lev in df["levering"].unique().to_list()
    }


def test_ster_metadata_en_quality_noemen_dezelfde_leveringen(demo_prepared, tmp_path):
    prepared, dirs = demo_prepared

    star = run_star(dirs, tmp_path, relative_to=prepared)
    quality = json.loads((tmp_path / "quality.json").read_text(encoding="utf-8"))

    in_feiten = _leveringen_in_feiten(star)
    assert set(star["meta_leveringen"]["levering"].to_list()) == in_feiten
    assert {d["levering"] for d in quality["deliveries"]} == in_feiten
    assert quality["summary"]["total_deliveries"] == star["meta_leveringen"].height


def test_gelijke_mapnaam_in_andere_submap_blijft_apart(demo_prepared, tmp_path):
    prepared, dirs = demo_prepared
    bron = dirs[0]
    kopie = tmp_path / "prepared" / "h99" / bron.name
    shutil.copytree(prepared, tmp_path / "prepared")
    shutil.copytree(bron, kopie)
    bronnen = [tmp_path / "prepared" / bron.relative_to(prepared), kopie]

    run_star(bronnen, tmp_path / "uit", relative_to=tmp_path / "prepared")
    quality = json.loads((tmp_path / "uit" / "quality.json").read_text())

    assert len(quality["deliveries"]) == 2


def test_leveringslabels_relatief_of_mapnaam(tmp_path):
    a, b = tmp_path / "h15" / "RO_A", tmp_path / "h17" / "GS_B"

    assert leveringslabels([a, b], relative_to=tmp_path) == ["h15/RO_A", "h17/GS_B"]
    assert leveringslabels([a, b]) == ["RO_A", "GS_B"]
