"""Kwaliteitscontroles op de ingelezen bekostigingsdata."""

import polars as pl


def validate_data(data: pl.DataFrame) -> pl.DataFrame:
    """Controleer de data op kwaliteit en geef deze ongewijzigd terug.

    Stopt met een fout als een harde controle faalt.

    Args:
        data: Gedecodeerde data uit :func:`decode.decode_fields`.

    Returns:
        Dezelfde data, mits alle controles slagen.
    """
    if data.is_empty():
        raise ValueError("Geen rijen in de dataset na inlezen.")

    # TODO: voeg controles toe op verplichte kolommen, dubbelingen en bereik.
    return data
