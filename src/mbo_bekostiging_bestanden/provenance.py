"""Provenance van een run: code, PvE-versie, bronbestanden, referenties (#300).

Alleen bestandsnamen en hashes, nooit paden of inhoud: ``quality.json`` en de
ster mogen geen persoonsgegevens of lokale mappen bevatten.
"""

from __future__ import annotations

import subprocess
import tomllib
from functools import cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

from mbo_bekostiging_bestanden.metadata import schema_versie
from mbo_bekostiging_bestanden.referentiedata import manifest_pad, sha256

if TYPE_CHECKING:
    from mbo_bekostiging_bestanden.quality import QualityReport

PAKKET = "mbo-bekostiging-bestanden"
_PAKKETMAP = Path(__file__).parent


def bronbestand(pad: Path, schema_naam: str) -> dict[str, str]:
    """Naam, sha256 en PvE-versie van een ruw leveringsbestand."""
    return {
        "naam": pad.name,
        "sha256": sha256(pad),
        "pve_versie": schema_versie(schema_naam),
    }


def pakketversie() -> str | None:
    try:
        return version(PAKKET)
    except PackageNotFoundError:
        return None


@cache
def git_commit() -> str | None:
    """Commit van de checkout waar deze code uit komt; ``None`` buiten een checkout.

    Alleen als de repo dít project is: een installatie in de virtualenv van een
    ander project zou anders diens commit krijgen.
    """
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel", "HEAD"],
            cwd=_PAKKETMAP,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return None
    pyproject = Path(top[0]) / "pyproject.toml"
    if not pyproject.exists():
        return None
    project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
    return top[1] if project.get("name") == PAKKET else None


def run_provenance() -> dict[str, Any]:
    """Wat de code van deze run vastlegt; de bronbestanden staan per levering."""
    return {
        "pakketversie": pakketversie(),
        "git_commit": git_commit(),
        "referentiemanifest_sha256": sha256(manifest_pad()),
    }


# Kolommen in meta_leveringen → sleutel in QualityReport.bronbestand.
_BRONBESTAND_KOLOMMEN = {
    "Bronbestand": "naam",
    "Bronbestand_sha256": "sha256",
    "PvE_versie": "pve_versie",
}


def met_bronbestanden(
    meta_leveringen: pl.DataFrame, rapporten: dict[str, QualityReport]
) -> pl.DataFrame:
    """``meta_leveringen`` met naam, sha256 en PvE-versie van elk bronbestand."""
    herkomst = pl.DataFrame(
        [
            {
                "levering": levering,
                **{
                    kolom: (rapport.bronbestand or {}).get(sleutel)
                    for kolom, sleutel in _BRONBESTAND_KOLOMMEN.items()
                },
            }
            for levering, rapport in rapporten.items()
        ],
        schema={"levering": pl.Utf8, **dict.fromkeys(_BRONBESTAND_KOLOMMEN, pl.Utf8)},
    )
    if meta_leveringen.is_empty():
        return meta_leveringen
    return meta_leveringen.join(herkomst, on="levering", how="left")
