"""De app gebruikt geen verouderde Streamlit-parameters (#111)."""

from pathlib import Path

import pytest

APP = Path(__file__).parent.parent / "app"
# Parameters die Streamlit heeft uitgefaseerd, met hun vervanger.
VEROUDERD = {"use_container_width": 'width="stretch"'}


@pytest.mark.parametrize(("parameter", "vervanger"), VEROUDERD.items())
def test_geen_verouderde_streamlit_parameters(parameter, vervanger):
    treffers = [
        f"{pad.relative_to(APP)}:{nr}"
        for pad in sorted(APP.rglob("*.py"))
        for nr, regel in enumerate(pad.read_text(encoding="utf-8").splitlines(), 1)
        if parameter in regel
    ]
    assert not treffers, f"Vervang {parameter} door {vervanger}: {treffers}"
