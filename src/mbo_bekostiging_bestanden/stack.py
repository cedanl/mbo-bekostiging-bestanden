"""Samenvoegen van genormaliseerde leveringen over jaren/perioden."""

from collections.abc import Sequence
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden.identiteit import PERSOON_COLS


def heeft_records(stacked: dict[str, pl.DataFrame], recordtype: str) -> bool:
    """Of de gestapelde data rijen van ``recordtype`` bevat."""
    return recordtype in stacked and not stacked[recordtype].is_empty()


def leveringslabels(
    sources: Sequence[Path | str], relative_to: Path | str | None = None
) -> list[str]:
    """Label per levering: pad t.o.v. ``relative_to``, anders de mapnaam.

    Eén bron voor het label in de ster (``levering``-kolom), ``meta_leveringen``
    en ``quality.json`` (#188).
    """
    paths = [Path(s) for s in sources]
    if relative_to is None:
        return [p.name for p in paths]
    return [p.relative_to(relative_to).as_posix() for p in paths]


def _controleer_bronnen(paths: list[Path], labels: list[str] | None) -> None:
    if labels is not None and len(labels) != len(paths):
        raise ValueError(
            f"labels heeft {len(labels)} elementen, sources heeft {len(paths)}"
        )
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"Bronmap niet gevonden: {p}")


def _lees_levering(
    path: Path, label: str, label_col: str
) -> list[tuple[str, pl.DataFrame]]:
    """Tabellen van één levering, met de leveringskolom als eerste kolom."""
    uit = []
    for parquet in sorted(path.glob("*.parquet")):
        df = pl.read_parquet(parquet)
        if identifiers := [c for c in PERSOON_COLS if c in df.columns]:
            # Brondata van vóór v4.0.0: pseudoniem pas in de sterbouw (#173).
            raise ValueError(
                f"{parquet} bevat persoonsidentifiers {identifiers}; verwerk de "
                "levering opnieuw met `mbo verwerk` (pseudoniem bij decode)"
            )
        df = df.with_columns(pl.lit(label).alias(label_col))
        df = df.select([label_col, *[c for c in df.columns if c != label_col]])
        uit.append((parquet.stem, df))
    return uit


def stack_prepared(
    sources: Sequence[Path | str],
    label_col: str = "levering",
    labels: list[str] | None = None,
    relative_to: Path | str | None = None,
) -> dict[str, pl.DataFrame]:
    """Voeg genormaliseerde tabellen van meerdere leveringen samen.

    Leest Parquet-bestanden uit elke bronmap, voegt een leveringskolom toe en
    concataneert tabellen met dezelfde naam. Tabellen die in slechts één bron
    voorkomen worden as-is opgenomen. Schema-drift (extra kolommen in één bron)
    wordt opgevangen door ontbrekende kolommen met ``null`` te vullen.

    Args:
        sources:     Lijst van mappen met Parquet-bestanden (één per levering).
        label_col:   Naam van de toe te voegen leveringskolom (eerste kolom).
        labels:      Labels per bron. Standaard: mapnamen, of relatieve paden
                     t.o.v. ``relative_to`` als dat is opgegeven.
        relative_to: Basispad voor automatische relatieve-pad-labels.

    Returns:
        Dict van tabelnaam naar gecombineerde DataFrame.

    Raises:
        FileNotFoundError: Als een bronmap niet bestaat.
        ValueError:        Als ``labels`` een andere lengte heeft dan ``sources``.

    Note:
        Deze functie stapelt enkel de gegevens. Kwaliteitscontrole gebeurt in
        :func:`~mbo_bekostiging_bestanden.pipeline.run_star`. Directe aanroep
        van deze functie (script, notebook) geeft geen kwaliteitsoordeel.
    """
    paths = [Path(s) for s in sources]
    if not paths:
        return {}
    _controleer_bronnen(paths, labels)
    if labels is None:
        labels = leveringslabels(paths, relative_to)

    tables: dict[str, list[pl.DataFrame]] = {}
    for path, label in zip(paths, labels, strict=True):
        for tabel, df in _lees_levering(path, label, label_col):
            tables.setdefault(tabel, []).append(df)

    return {
        tabel: pl.concat(frames, how="diagonal_relaxed")
        for tabel, frames in tables.items()
    }
