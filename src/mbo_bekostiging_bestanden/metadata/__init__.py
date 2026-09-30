"""Metadata: veldindelingen en codeboeken voor de bekostigingsbestanden."""

import json
import tomllib
from functools import lru_cache
from pathlib import Path

SCHEMA_DIR = Path(__file__).parent


@lru_cache
def _lees_schema(name: str) -> dict:
    schema_path = SCHEMA_DIR / f"{name}_schema.toml"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema niet gevonden: {schema_path}")
    with open(schema_path, "rb") as f:
        return tomllib.load(f)


def schema_versie(name: str) -> str:
    """PvE-versie waarop het schema gebaseerd is (``schema_version``, #300)."""
    return _lees_schema(name)["schema_version"]


def bestandsnaam_patroon(name: str) -> str | None:
    """Regex op de bestandsnaam met named groups voor ``uit_bestandsnaam`` (#236)."""
    return _lees_schema(name).get("bestandsnaam")


@lru_cache
def pve_bron() -> dict[str, str]:
    """De PvE-bron waarop de schema's zijn gebaseerd (``pve_bron.json``, #299).

    ``versie`` en ``sha256`` (van ``bestand``, de beknopte extractie in de repo)
    zijn het ijkpunt voor de consistentiecontrole in CI.
    """
    with open(SCHEMA_DIR / "pve_bron.json", encoding="utf-8") as f:
        return json.load(f)


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
    return {k: v for k, v in _lees_schema(name).items() if isinstance(v, dict)}


def extra_kolommen(recordschema: dict) -> dict[str, str]:
    """Kolomnaam → veld dat hij lijkt te herhalen, voor de ``spiegelvelden``.

    Die posities staan achter de PvE-velden en niet in het PvE; of ze een kopie
    of een eerdere waarde zijn, is onbekend (#260). De naam draagt daarom de
    positie, geen betekenis: ``Postcodecijfers_positie19``.
    """
    spiegelvelden = recordschema.get("spiegelvelden", [])
    eerste = len(recordschema["fields"]) + 1
    return {f"{veld}_positie{eerste + i}": veld for i, veld in enumerate(spiegelvelden)}


def alle_extra_kolommen() -> set[str]:
    return {
        kolom
        for pad in SCHEMA_DIR.glob("*_schema.toml")
        for recordschema in load_schema(pad.stem.removesuffix("_schema")).values()
        for kolom in extra_kolommen(recordschema)
    }
