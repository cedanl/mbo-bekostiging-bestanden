"""Publicatie van de ster: atomair en alleen na de kwaliteitspoort (#363).

Padcontract onder de doelmap van ``run_star``, gedeeld door CLI, app en
externe afnemers:

  datamodel/     de gepubliceerde ster (één Parquet-bestand per tabel)
  quality.json   het rapport van die publicatie
  diagnose/      zelfde indeling, van een run met status ``fail`` zonder
                 override: niet gepubliceerd, alleen om de oorzaak te lezen

Een run schrijft eerst naar een verborgen staging-map in de doelmap (zelfde
bestandssysteem, dus een rename is atomair). ``datamodel/`` is daardoor nooit
half geschreven, en een mislukte of onderbroken run laat de vorige publicatie
staan.
"""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.quality import KwaliteitsFout, lees_status

DATAMODEL = "datamodel"
KWALITEITSRAPPORT = "quality.json"
DIAGNOSE = "diagnose"
_STAGING_PREFIX = ".staging-"
_VORIGE = f"{DATAMODEL}.vorige"


@contextmanager
def staging(doel: Path) -> Iterator[Path]:
    """Lege staging-map in ``doel``; verdwijnt na afloop, ook bij een onderbreking."""
    doel.mkdir(parents=True, exist_ok=True)
    map_ = Path(tempfile.mkdtemp(prefix=_STAGING_PREFIX, dir=doel))
    try:
        yield map_
    finally:
        shutil.rmtree(map_, ignore_errors=True)


def publiceer(staging_map: Path, doel: Path) -> Path:
    """Vervang de publicatie in ``doel`` door die in ``staging_map``.

    De vorige ``datamodel/`` gaat eerst opzij in de staging-map (en verdwijnt
    daarmee), daarna komt de nieuwe er met één rename. Een eerdere diagnose
    hoort niet meer bij deze publicatie en wordt opgeruimd.

    Returns:
        Het pad van het gepubliceerde ``quality.json``.
    """
    datamodel = doel / DATAMODEL
    if datamodel.exists():
        datamodel.rename(staging_map / _VORIGE)
    (staging_map / DATAMODEL).rename(datamodel)
    rapport = (staging_map / KWALITEITSRAPPORT).replace(doel / KWALITEITSRAPPORT)
    shutil.rmtree(doel / DIAGNOSE, ignore_errors=True)
    return rapport


def bewaar_diagnose(staging_map: Path, doel: Path) -> Path:
    """Zet de output van een niet-publiceerbare run in ``doel/diagnose/``.

    Returns:
        Het pad van het ``quality.json`` van de diagnose.
    """
    diagnose = doel / DIAGNOSE
    shutil.rmtree(diagnose, ignore_errors=True)
    staging_map.rename(diagnose)
    return diagnose / KWALITEITSRAPPORT


def lees_ster(
    doel: Path | str, fouten_toestaan: bool = False
) -> dict[str, pl.DataFrame]:
    """Lees de gepubliceerde ster in ``doel``.

    Met ``--allow-quality-errors`` kan ook een ster met status ``fail``
    gepubliceerd zijn; een afnemer moet dat bewust accepteren met
    ``fouten_toestaan``.

    Raises:
        FileNotFoundError: als ``doel`` geen gepubliceerde ster bevat.
        KwaliteitsFout: bij status ``fail`` zonder ``fouten_toestaan``.
    """
    doel = Path(doel)
    datamodel = doel / DATAMODEL
    rapport = doel / KWALITEITSRAPPORT
    if not datamodel.is_dir() or not rapport.exists():
        raise FileNotFoundError(f"Geen gepubliceerde ster in {doel}")
    status, fouten = lees_status(rapport)
    if status == "fail" and not fouten_toestaan:
        raise KwaliteitsFout(
            f"De ster in {doel} heeft kwaliteitsstatus fail ({fouten} error(s)); "
            f"zie {rapport}"
        )
    return {p.stem: pl.read_parquet(p) for p in sorted(datamodel.glob("*.parquet"))}
