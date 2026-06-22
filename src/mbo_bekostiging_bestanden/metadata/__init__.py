"""Metadata: veldindelingen en codeboeken voor de bekostigingsbestanden."""

import tomllib
from functools import lru_cache
from pathlib import Path

SCHEMA_DIR = Path(__file__).parent


@lru_cache
def load_schema(name: str = "ro") -> dict[str, dict]:
    """Laad een schema-TOML en geef de recordtype-entries terug.

    Args:
        name: Naam van het schema zonder extensie (bijv. ``"ro"``,
              ``"grondslag"``). Laadt ``{name}_schema.toml`` uit de
              ``metadata/``-map.

    Returns:
        Dict van recordtype-code naar schema-dict met ``fields``,
        ``date_fields``, ``int_fields`` en optioneel ``single_row``.

    Raises:
        FileNotFoundError: Als het gevraagde schema-bestand niet bestaat.
    """
    schema_path = SCHEMA_DIR / f"{name}_schema.toml"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema niet gevonden: {schema_path}")
    with open(schema_path, "rb") as f:
        data = tomllib.load(f)
    return {k: v for k, v in data.items() if isinstance(v, dict)}
