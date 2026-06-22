"""Metadata: veldindelingen en codeboeken voor de bekostigingsbestanden."""

import tomllib
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "ro_schema.toml"


def load_schema() -> dict[str, dict]:
    """Laad ro_schema.toml en geef de recordtype-entries terug.

    Returns:
        Dict van recordtype-code naar schema-dict met ``fields``,
        ``date_fields`` en ``int_fields``.
    """
    with open(SCHEMA_PATH, "rb") as f:
        data = tomllib.load(f)
    return {k: v for k, v in data.items() if isinstance(v, dict)}
