"""Gedeelde hulpfuncties voor de Streamlit-app."""

import os
import tomllib
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path

from mbo_bekostiging_bestanden.metadata import load_schema
from mbo_bekostiging_bestanden.publicatie import DIAGNOSE, KWALITEITSRAPPORT
from mbo_bekostiging_bestanden.quality import (
    kwaliteitsstatus,
    lees_leveringsrapport,
    lees_status,
)

# Relatieve datapaden in config.toml gelden t.o.v. de projectroot, zodat de app
# vanuit elke werkmap hetzelfde gedrag heeft.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_STAR_SUBMAP = "star"
# Een star-map telt als gebouwd zodra de centrale feittabel bestaat.
_STAR_KERNTABEL = Path("datamodel") / "fact_inschrijving.parquet"
# Sessiesleutels waarin Home het pad van het gebouwde star schema bewaart.
_STAR_SESSIESLEUTELS = ("resultaten_dir", "star_pad")
# TBGI-recordtypen (Teldatum, BekostigingsrelevanteBPV, …) uit het schema, zodat
# een nieuw recordtype automatisch in de TBGI-sectie van Resultaten verschijnt.
_TBGI_SCHEMA = "tbgi"


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.toml"
    with config_path.open("rb") as f:
        return tomllib.load(f)


def _config_pad(sleutel: str) -> Path:
    pad = Path(load_config()["data"][sleutel])
    return pad if pad.is_absolute() else _PROJECT_ROOT / pad


def raw_dir() -> Path:
    return _config_pad("raw")


def prepared_dir() -> Path:
    return _config_pad("prepared")


def output_dir() -> Path:
    return _config_pad("output")


def scenario() -> str:
    """Scenariolabel voor ``quality.json`` uit ``config.toml``."""
    return load_config()["data"]["scenario"]


def star_dir() -> Path:
    return output_dir() / _STAR_SUBMAP


def vind_star_dir(sessie: Mapping) -> Path | None:
    """Eerste map met een gebouwd star-datamodel.

    Probeert eerst de paden die Home in de sessie zette, daarna de
    standaardlocatie op schijf — zodat een pagina ook werkt bij een verse
    sessie of een directe link.
    """
    kandidaten = [Path(p) for k in _STAR_SESSIESLEUTELS if (p := sessie.get(k))]
    for kandidaat in [*kandidaten, star_dir()]:
        if (kandidaat / _STAR_KERNTABEL).exists():
            return kandidaat
    return None


def vind_prepared_dirs(sessie: Mapping) -> list[Path]:
    """Prepared-directories met brondata, voor de Brondata-sectie in Resultaten.

    Analoog aan :func:`vind_star_dir`: de paden die Home in de sessie zette
    hebben voorrang; zonder sessie (verse sessie of directe link) valt dit
    terug op een scan van ``prepared_dir()`` op schijf, zodat brondata en
    star schema na een herstart gelijkwaardig zichtbaar blijven (#263).
    """
    sessie_dirs = sessie.get("prepared_dirs")
    if sessie_dirs:
        return [Path(p) for p in sessie_dirs]
    basis = prepared_dir()
    if not basis.exists():
        return []
    return sorted(
        {
            parquet.parent
            for parquet in basis.rglob("*.parquet")
            if parquet.parent.name != DIAGNOSE
        }
    )


def groepeer_prepared(
    prepared_dirs: Iterable[Path | str],
) -> tuple[dict[str, Path], dict[str, Path]]:
    """Verdeel prepared-tabellen over een TBGI- en een overige groep.

    Sleutels zijn ``"<levering> / <tabel>"``, zodat tabellen met dezelfde naam
    uit verschillende leveringen elkaar niet overschrijven.

    Returns:
        ``(tbgi, overig)``: dicts van weergavenaam naar Parquet-pad.
    """
    tbgi_recordtypen = set(load_schema(_TBGI_SCHEMA))
    tbgi: dict[str, Path] = {}
    overig: dict[str, Path] = {}
    for prep_dir in map(Path, prepared_dirs):
        for parquet in sorted(prep_dir.glob("*.parquet")):
            groep = tbgi if parquet.stem in tbgi_recordtypen else overig
            groep[f"{prep_dir.name} / {parquet.stem}"] = parquet
    return tbgi, overig


def brondata_bijschrift(prepared_dirs: Iterable[Path | str]) -> str:
    """Map en status van de brondata, als eigen product naast de ster (#285).

    De status per levering komt uit haar ``quality.json``; ontbreekt dat, dan
    meldt :func:`lees_leveringsrapport` een warning.
    """
    mappen = [Path(d) for d in prepared_dirs]
    statussen = Counter(
        kwaliteitsstatus(len(r.errors), len(r.warnings))
        for r in (lees_leveringsrapport(m / KWALITEITSRAPPORT, m.name) for m in mappen)
    )
    telling = ", ".join(f"{n} {status}" for status, n in sorted(statussen.items()))
    basis = Path(os.path.commonpath(mappen)) if mappen else prepared_dir()
    return f"Brondata · `{basis}` · {len(mappen)} levering(en), status: {telling}"


def analysemodel_bijschrift(ster: Path) -> str:
    """Map en status van het analysemodel (``quality.json`` van de publicatie)."""
    rapport = ster / KWALITEITSRAPPORT
    if not rapport.exists():
        return f"Analysemodel · `{ster}` · status onbekend (geen {KWALITEITSRAPPORT})"
    status, fouten = lees_status(rapport)
    return f"Analysemodel · `{ster}` · status: {status} ({fouten} errors)"
