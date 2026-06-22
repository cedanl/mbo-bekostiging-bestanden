"""Decoderen van velden: codes omzetten naar leesbare waarden via metadata."""

import polars as pl


def decode_fields(data: pl.DataFrame) -> pl.DataFrame:
    """Zet gecodeerde velden om naar leesbare waarden.

    Args:
        data: Onbewerkte data uit :func:`ingest.read_raw_file`.

    Returns:
        DataFrame met gedecodeerde, leesbare kolommen.
    """
    # TODO: koppel codeboeken uit ``metadata/`` aan de gecodeerde kolommen.
    return data
