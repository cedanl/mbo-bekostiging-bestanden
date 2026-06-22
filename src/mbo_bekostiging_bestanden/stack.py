"""Samenvoegen van genormaliseerde leveringen over jaren/perioden."""

from collections.abc import Sequence
from pathlib import Path

import polars as pl


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
    """
    paths = [Path(s) for s in sources]
    if not paths:
        return {}

    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"Bronmap niet gevonden: {p}")

    if labels is not None and len(labels) != len(paths):
        raise ValueError(
            f"labels heeft {len(labels)} elementen, sources heeft {len(paths)}"
        )

    if labels is None:
        root = Path(relative_to) if relative_to is not None else None
        labels = [
            str(p.relative_to(root)) if root is not None else p.name for p in paths
        ]

    tables: dict[str, list[pl.DataFrame]] = {}
    for path, label in zip(paths, labels, strict=True):
        for parquet in sorted(path.glob("*.parquet")):
            df = pl.read_parquet(parquet).with_columns(pl.lit(label).alias(label_col))
            df = df.select([label_col, *[c for c in df.columns if c != label_col]])
            tables.setdefault(parquet.stem, []).append(df)

    return {
        tabel: pl.concat(frames, how="diagonal_relaxed")
        for tabel, frames in tables.items()
    }
