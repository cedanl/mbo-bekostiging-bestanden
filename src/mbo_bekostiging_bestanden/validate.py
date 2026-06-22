"""Kwaliteitscontroles op de ingelezen bekostigingsdata."""

import polars as pl

from mbo_bekostiging_bestanden.metadata import load_schema

_SINGLE_ROW_TYPES = ("VLP", "SLR")


def validate_ro(frames: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Valideer een volledig RO-pakket na decoding.

    Controles:
    - Alle verwachte kolommen aanwezig per recordtype (schema-gedreven).
    - VLP en SLR bevatten elk exact 1 rij.

    Args:
        frames: Dict van recordtype-code naar getypeerde DataFrame.

    Returns:
        Dezelfde frames, mits alle controles slagen.

    Raises:
        ValueError: Als een harde controle faalt.
    """
    schema = load_schema()

    for rt, df in frames.items():
        if rt not in schema:
            continue
        expected = set(schema[rt]["fields"])
        missing = expected - set(df.columns)
        if missing:
            raise ValueError(
                f"{rt}: ontbrekende kolommen {sorted(missing)}"
            )

    for rt in _SINGLE_ROW_TYPES:
        if rt in frames and frames[rt].height != 1:
            raise ValueError(
                f"{rt} moet exact 1 rij bevatten, gevonden: {frames[rt].height}"
            )

    return frames
