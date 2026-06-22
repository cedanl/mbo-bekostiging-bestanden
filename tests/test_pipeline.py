"""Skeleton-tests op de demo-data.

De ruwe DUO-bestanden zijn multi-record (regeltypes VLP/PER/ISG, ``;``-gescheiden)
en XML. Het echte inlezen/decoderen volgt in aparte issues; deze tests borgen
alleen dat de demo-data aanwezig is en dat de validatie lege data afwijst.
"""

from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.validate import validate_data

DEMO_DIR = Path("data/01-raw/demo")


def test_demo_data_present():
    files = list(DEMO_DIR.rglob("*"))
    files = [f for f in files if f.is_file()]
    assert files, "Geen demo-bestanden gevonden in data/01-raw/demo"


def test_validate_passes_non_empty():
    data = pl.DataFrame({"x": [1, 2, 3]})
    assert validate_data(data).height == 3


def test_validate_rejects_empty():
    try:
        validate_data(pl.DataFrame())
    except ValueError:
        return
    raise AssertionError("validate_data had moeten falen op lege data")
