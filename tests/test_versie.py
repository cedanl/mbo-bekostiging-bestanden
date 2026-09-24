"""De packageversie heeft één bron: pyproject.toml."""

import tomllib
from pathlib import Path

import mbo_bekostiging_bestanden

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def test_dunder_version_volgt_pyproject():
    with PYPROJECT.open("rb") as f:
        verwacht = tomllib.load(f)["project"]["version"]
    assert mbo_bekostiging_bestanden.__version__ == verwacht
