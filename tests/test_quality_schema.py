"""``quality.json`` van ``run_star()`` volgt ``docs/quality.schema.json`` (#177).

Het schema is het contract voor afnemers buiten de app. Het is strikt
(``additionalProperties: false``), zodat een hernoemd of nieuw veld in de code
zonder schema-update een falende test oplevert in plaats van stille drift.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from mbo_bekostiging_bestanden.pipeline import run_star

SCHEMA = json.loads(Path("docs/quality.schema.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def demo_quality(demo_prepared, tmp_path_factory) -> dict:
    prepared, dirs = demo_prepared
    doel = tmp_path_factory.mktemp("star")
    run_star(dirs, doel, relative_to=prepared)
    return json.loads((doel / "quality.json").read_text(encoding="utf-8"))


def _objecten_met_properties(schema: dict, pad: str = "$"):
    """Alle (pad, subschema) met vaste ``properties`` in het schema."""
    if "properties" in schema:
        yield pad, schema
        for naam, sub in schema["properties"].items():
            yield from _objecten_met_properties(sub, f"{pad}.{naam}")
    for sleutel in ("items", "additionalProperties"):
        if isinstance(schema.get(sleutel), dict):
            yield from _objecten_met_properties(schema[sleutel], f"{pad}[{sleutel}]")


def test_schema_is_geldig_draft7():
    Draft7Validator.check_schema(SCHEMA)


def test_schema_is_strikt():
    los = [
        pad
        for pad, sub in _objecten_met_properties(SCHEMA)
        if sub.get("additionalProperties") is not False
    ]
    assert los == []


def test_demo_quality_volgt_schema(demo_quality):
    fouten = [
        f"{'.'.join(map(str, f.absolute_path))}: {f.message}"
        for f in Draft7Validator(SCHEMA).iter_errors(demo_quality)
    ]
    assert fouten == []


def test_onbekend_veld_wordt_afgewezen(demo_quality):
    fout = {**demo_quality, "star": {**demo_quality["star"], "nivel_issues": {}}}

    assert not Draft7Validator(SCHEMA).is_valid(fout)
