"""Zijbalk: ruw → werkbaar, dan analysemodel, dan dashboard, elk een eigen pagina."""

import ast
from pathlib import Path

_APP = Path(__file__).parents[1] / "app"


def _pagina_s() -> list[tuple[str, str]]:
    """``(bestand, titel)`` van elke ``st.Page`` in ``main.py``, in volgorde."""
    boom = ast.parse((_APP / "main.py").read_text(encoding="utf-8"))
    return [
        (
            ast.literal_eval(n.args[0]),
            next(ast.literal_eval(k.value) for k in n.keywords if k.arg == "title"),
        )
        for n in ast.walk(boom)
        if isinstance(n, ast.Call)
        and getattr(n.func, "attr", "") == "Page"
        and any(k.arg == "title" for k in n.keywords)
    ]


def test_zijbalk_scheidt_werkbare_data_analysemodel_en_dashboard():
    assert [titel for _, titel in _pagina_s()] == [
        "Home",
        "Werkbare data",
        "Analysemodel",
        "Dashboard",
    ]


def test_elke_pagina_in_de_zijbalk_bestaat():
    for bestand, _ in _pagina_s():
        assert (_APP / bestand).exists(), bestand
