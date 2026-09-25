"""Samenvoegen van genormaliseerde leveringen over jaren/perioden."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

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

    if labels is not None and len(labels) != len(paths):
        raise ValueError(
            f"labels heeft {len(labels)} elementen, sources heeft {len(paths)}"
        )

    for p in paths:
        if not p.exists():
            raise FileNotFoundError(f"Bronmap niet gevonden: {p}")

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


def deduplicate_overlaps(
    stacked: dict[str, pl.DataFrame],
    grain_cols: list[str] | None = None,
    delivery_col: str = "levering",
) -> tuple[dict[str, pl.DataFrame], dict[str, Any]]:
    """Deduplicate overlapping rows per grain; keep most recent delivery.

    If grain_cols is None, uses table-specific grains:
    - inschrijvingen: [_persoon_id, Inschrijvingvolgnummer, Studiejaar]

    Returns:
        (deduplicated_tables, stats) where stats = {table: {removed_count, by_delivery}}
    """
    if grain_cols is None:
        # Table-specific grains
        grain_cols_map = {
            "inschrijvingen": ["_persoon_id", "Inschrijvingvolgnummer", "Studiejaar"],
        }
    else:
        grain_cols_map = {name: grain_cols for name in stacked}

    deduped = {}
    stats = {}

    for table_name, df in stacked.items():
        if df.is_empty() or delivery_col not in df.columns:
            deduped[table_name] = df
            stats[table_name] = {"removed_count": 0, "by_delivery": {}}
            continue

        grain = grain_cols_map.get(table_name, grain_cols)
        if not grain:
            deduped[table_name] = df
            stats[table_name] = {"removed_count": 0, "by_delivery": {}}
            continue

        # Check all grain columns exist
        available_grain = [c for c in grain if c in df.columns]
        if not available_grain:
            deduped[table_name] = df
            stats[table_name] = {"removed_count": 0, "by_delivery": {}}
            continue

        # Rank by delivery (alphabetically last wins = most recent)
        # Add row_number; take only first per grain (most recent delivery)
        ranked = df.with_columns(
            pl.col(delivery_col)
            .rank(method="ordinal", descending=True)
            .over(available_grain)
            .alias("_rank")
        )

        # Count removals per delivery before filtering
        if "_rank" in ranked.columns:
            removed_per_delivery = (
                ranked.filter(pl.col("_rank") > 1)
                .group_by(delivery_col)
                .len()
                .sort(delivery_col)
            )
            removal_dict = {
                row[0]: int(row[1]) for row in removed_per_delivery.iter_rows()
            }
        else:
            removal_dict = {}

        # Keep only rank 1 (most recent per grain)
        deduped_df = ranked.filter(pl.col("_rank") == 1).drop("_rank")
        removed_total = df.height - deduped_df.height

        stats[table_name] = {
            "removed_count": removed_total,
            "by_delivery": removal_dict,
        }
        deduped[table_name] = deduped_df

    return deduped, stats
