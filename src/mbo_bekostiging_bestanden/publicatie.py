"""Atomaire publicatie, alleen na de kwaliteitspoort (#363, #414, #415).

Padcontract onder de doelmap van ``run_star``, gedeeld door CLI, app en
externe afnemers:

  datamodel/     de gepubliceerde ster (één Parquet-bestand per tabel)
  quality.json   het rapport van die publicatie
  diagnose/      zelfde indeling, van een run met status ``fail`` zonder
                 override: niet gepubliceerd, alleen om de oorzaak te lezen

De brondata van één levering (``02-prepared``) staat plat in de doelmap: één
bestand per recordtype plus ``quality.json``, en bij een foute run eveneens
``diagnose/``.

Een run schrijft eerst naar een verborgen staging-map op hetzelfde
bestandssysteem, dus een rename is atomair. De publicatie is daardoor nooit
half geschreven, bevat geen tabellen van een eerdere bron, en een mislukte of
onderbroken run laat de vorige publicatie staan.
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
def staging(basis: Path) -> Iterator[Path]:
    """Lege staging-map in ``basis``; verdwijnt na afloop, ook bij een onderbreking.

    ``basis`` ligt op hetzelfde bestandssysteem als wat vervangen wordt: de
    doelmap zelf (ster) of de map erboven (brondata).
    """
    basis.mkdir(parents=True, exist_ok=True)
    map_ = Path(tempfile.mkdtemp(prefix=_STAGING_PREFIX, dir=basis))
    try:
        yield map_
    finally:
        shutil.rmtree(map_, ignore_errors=True)


def _vervang(nieuw: Path, doel: Path, opzij: Path) -> None:
    """Zet ``nieuw`` op de plek van ``doel``; een bestaande ``doel`` gaat naar
    ``opzij`` (in de staging-map, dus die verdwijnt met de staging)."""
    if doel.exists():
        doel.rename(opzij)
    nieuw.rename(doel)


def publiceer(staging_map: Path, doel: Path) -> Path:
    """Vervang de publicatie in ``doel`` door die in ``staging_map``.

    De vorige ``datamodel/`` gaat eerst opzij in de staging-map (en verdwijnt
    daarmee), daarna komt de nieuwe er met één rename. Een eerdere diagnose
    hoort niet meer bij deze publicatie en wordt opgeruimd.

    Returns:
        Het pad van het gepubliceerde ``quality.json``.
    """
    _vervang(staging_map / DATAMODEL, doel / DATAMODEL, staging_map / _VORIGE)
    rapport = (staging_map / KWALITEITSRAPPORT).replace(doel / KWALITEITSRAPPORT)
    shutil.rmtree(doel / DIAGNOSE, ignore_errors=True)
    return rapport


def bewaar_diagnose(staging_map: Path, doel: Path) -> Path:
    """Zet de output van een niet-publiceerbare run in ``doel/diagnose/``.

    Returns:
        Het pad van het ``quality.json`` van de diagnose.
    """
    diagnose = doel / DIAGNOSE
    doel.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(diagnose, ignore_errors=True)
    staging_map.rename(diagnose)
    return diagnose / KWALITEITSRAPPORT


def controleer_brondatamap(doel: Path) -> None:
    """Weiger een doelmap die niet leeg is en geen eerdere brondata bevat.

    :func:`publiceer_brondata` vervangt de doelmap in zijn geheel; een per
    ongeluk gekozen bovenliggende map mag daarbij niet leeg raken.

    Raises:
        ValueError: als ``doel`` andere inhoud heeft.
    """
    if not doel.exists() or not any(doel.iterdir()):
        return
    if not ((doel / KWALITEITSRAPPORT).exists() or (doel / DIAGNOSE).is_dir()):
        raise ValueError(
            f"Doelmap {doel} bevat geen eerdere brondata (geen "
            f"{KWALITEITSRAPPORT} of {DIAGNOSE}/) en zou in zijn geheel worden "
            "vervangen; kies een lege of eigen map per levering"
        )


def publiceer_brondata(staging_map: Path, nieuw: Path, doel: Path) -> None:
    """Vervang de brondatamap ``doel`` in zijn geheel door ``nieuw``.

    ``staging_map`` staat naast ``doel`` (zie :func:`staging`); de vorige
    inhoud, inclusief een oude ``diagnose/``, verdwijnt daarmee.
    """
    _vervang(nieuw, doel, staging_map / _VORIGE)


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
