"""Kwaliteitscontroles op de ingelezen bekostigingsdata."""

import polars as pl

from mbo_bekostiging_bestanden.metadata import load_schema


def validate_multi_record(
    frames: dict[str, pl.DataFrame],
    schema_name: str,
) -> dict[str, pl.DataFrame]:
    """Valideer een volledig pakket na decoding.

    Controles (schema-gedreven):
    - Alle verwachte kolommen aanwezig per recordtype.
    - Recordtypes met ``single_row = true`` in het schema bevatten exact 1 rij.

    Args:
        frames:      Dict van recordtype-code naar getypeerde DataFrame.
        schema_name: Naam van het schema (bijv. ``"ro"`` of ``"grondslag"``).

    Returns:
        Dezelfde frames, mits alle controles slagen.

    Raises:
        FileNotFoundError: Als het schema niet bestaat.
        ValueError:        Als een harde controle faalt.
    """
    schema = load_schema(schema_name)

    for rt, df in frames.items():
        if rt not in schema:
            continue
        missing = set(schema[rt]["fields"]) - set(df.columns)
        if missing:
            raise ValueError(f"{rt}: ontbrekende kolommen {sorted(missing)}")

    for rt, rt_schema in schema.items():
        if rt_schema.get("single_row") and rt in frames and frames[rt].height != 1:
            raise ValueError(
                f"{rt} moet exact 1 rij bevatten, gevonden: {frames[rt].height}"
            )

    return frames


def validate_ro(frames: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Valideer een RO-pakket na decoding.

    Dunne wrapper om :func:`validate_multi_record` met schema ``"ro"``.
    """
    return validate_multi_record(frames, "ro")


def validate_grondslag(frames: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """Valideer een GRONDSLAG IP MBO-pakket na decoding.

    Dunne wrapper om :func:`validate_multi_record` met schema ``"grondslag"``.
    """
    return validate_multi_record(frames, "grondslag")
