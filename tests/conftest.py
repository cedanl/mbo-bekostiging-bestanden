"""Gedeelde test-fixtures voor stack- en CLI-tests."""

from datetime import date

import polars as pl
import pytest


@pytest.fixture(scope="session")
def prepared_dirs(tmp_path_factory):
    """Twee RO-stijl en één GRONDSLAG-stijl prepared-map met synthetische Parquet-data.

    Structuur:
        base/
          h15/21CY/  ISG.parquet (4 rijen, RO-schema)
          h15/25LX/  ISG.parquet (3 rijen, RO-schema)
          h17/IP/    ISG.parquet (2 rijen, GRONDSLAG-schema — andere kolommen)
    """
    base = tmp_path_factory.mktemp("prepared")
    dir_21cy = base / "h15" / "21CY"
    dir_25lx = base / "h15" / "25LX"
    dir_ip = base / "h17" / "IP"

    for d in [dir_21cy, dir_25lx, dir_ip]:
        d.mkdir(parents=True)

    # RO-stijl ISG: Burgerservicenummer, geen BRIN
    isg_ro_a = pl.DataFrame(
        {
            "Recordsoort": ["ISG"] * 4,
            "Burgerservicenummer": ["100", "101", "102", "103"],
            "Inschrijvingvolgnummer": ["A1", "A2", "A3", "A4"],
            "DatumInschrijving": [date(2024, 8, 1)] * 4,
        }
    )
    isg_ro_b = pl.DataFrame(
        {
            "Recordsoort": ["ISG"] * 3,
            "Burgerservicenummer": ["200", "201", "202"],
            "Inschrijvingvolgnummer": ["B1", "B2", "B3"],
            "DatumInschrijving": [date(2025, 8, 1)] * 3,
        }
    )
    # GRONDSLAG-stijl ISG: PseudoNummer + BRIN, geen Burgerservicenummer
    isg_grondslag = pl.DataFrame(
        {
            "Recordsoort": ["ISG"] * 2,
            "PseudoNummer": ["P1", "P2"],
            "BRIN": ["27DV", "27DV"],
            "DatumInschrijving": [date(2025, 8, 1)] * 2,
        }
    )

    isg_ro_a.write_parquet(dir_21cy / "ISG.parquet")
    isg_ro_b.write_parquet(dir_25lx / "ISG.parquet")
    isg_grondslag.write_parquet(dir_ip / "ISG.parquet")

    return {
        "base": base,
        "21CY": dir_21cy,
        "25LX": dir_25lx,
        "IP": dir_ip,
    }
