"""GRONDSLAG-BID komt in ``fact_bekostiging_diploma``, naast TBG-i-Diploma (#258).

BID mist ``Inschrijvingvolgnummer``, ``Opleidingcode`` en de behaaldatum
(PvE §17.5); die staan op het DIP-record met hetzelfde ``Resultaatvolgnummer``.
Een BID zonder DIP in dezelfde levering is een bronfout, geen verklaarde
wees-rij: de uitzondering voor TBG-i (PvE §16.1) geldt niet voor GRONDSLAG.
"""

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.pipeline import run_grondslag_pipeline, run_star
from mbo_bekostiging_bestanden.quality import _wees_feiten

FIXTURE = Path("tests/fixtures/grondslag_pve/GRONDSLAG_IP_MBO_97XX_20251119_2025.csv")


@pytest.fixture(scope="module")
def prepared(tmp_path_factory) -> Path:
    doel = tmp_path_factory.mktemp("prepared")
    run_grondslag_pipeline(FIXTURE, doel)
    return doel


@pytest.fixture(scope="module")
def ster(prepared, tmp_path_factory) -> dict[str, pl.DataFrame]:
    return run_star([prepared], tmp_path_factory.mktemp("star"))


def test_bid_landt_in_fact_bekostiging_diploma(ster):
    rij = ster["fact_bekostiging_diploma"].row(0, named=True)
    assert ster["fact_bekostiging_diploma"].height == 1
    assert rij["BijdrageDiplomawaarde"] == 1.0
    assert rij["NiveauHoogstBekostigdeDiploma"] == "MBO-3"
    assert rij["IndicatieSpecialistendiploma"] == "N"


def test_bid_neemt_inschrijving_en_datum_over_van_dip(ster):
    rij = ster["fact_bekostiging_diploma"].row(0, named=True)
    assert rij["Inschrijvingvolgnummer"] == "INS1"
    assert rij["Opleidingcode"] == "25655"
    assert rij["DatumBehaald"] == date(2025, 6, 15)


def test_bid_koppelt_aan_inschrijvingsperiode(ster):
    diploma = ster["fact_bekostiging_diploma"]
    assert diploma["_inschrijving_periode_id"].null_count() == 0
    assert set(diploma["_inschrijving_periode_id"]) <= set(
        ster["fact_inschrijving"]["_inschrijving_periode_id"]
    )


def test_bid_zonder_dip_is_onverklaarde_wees(prepared, tmp_path):
    """Zonder DIP geen inschrijving: melden als error, niet wegverklaren."""
    pl.read_parquet(prepared / "DIP.parquet").clear().write_parquet(
        tmp_path / "DIP.parquet"
    )
    for bestand in prepared.glob("*.parquet"):
        if bestand.name != "DIP.parquet":
            (tmp_path / bestand.name).write_bytes(bestand.read_bytes())

    ster = run_star([tmp_path], tmp_path / "star", fail_on_errors=False)
    wees = _wees_feiten(ster)
    assert wees["fact_bekostiging_diploma"]["orphaned_rows"] == 1
    assert wees["fact_bekostiging_diploma"]["explained_rows"] == 0
