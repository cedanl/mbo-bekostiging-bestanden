"""Aggregaten in fact_inschrijving tellen per ISP-periode, niet per inschrijving (#105).

Een inschrijving met meerdere perioden mag haar BPV/KZD/AMO-aantallen niet op
elke periode herhalen; optellen over fact_inschrijving moet het aantal
gekoppelde detailrijen opleveren.
"""

import polars as pl
import pytest

SLEUTEL = "_inschrijving_periode_id"
AGGREGAAT_PER_FEIT = [
    ("BPV_Aantal", "fact_bpv"),
    ("KZD_Aantal", "fact_kzd"),
    ("AMO_Aantal", "fact_amo"),
]


@pytest.mark.parametrize(("kolom", "feit"), AGGREGAAT_PER_FEIT)
def test_som_van_aggregaat_is_aantal_gekoppelde_detailrijen(demo_star, kolom, feit):
    fi = demo_star["fact_inschrijving"]
    gekoppeld = demo_star[feit].drop_nulls(SLEUTEL).height
    assert fi[kolom].sum() == gekoppeld


@pytest.mark.parametrize(("kolom", "feit"), AGGREGAAT_PER_FEIT)
def test_aggregaat_per_periode_komt_overeen_met_detail_feit(demo_star, kolom, feit):
    verwacht = demo_star[feit].drop_nulls(SLEUTEL).group_by(SLEUTEL).len()
    werkelijk = (
        demo_star["fact_inschrijving"]
        .filter(pl.col(kolom) > 0)
        .select(SLEUTEL, pl.col(kolom).cast(pl.UInt32).alias("len"))
    )
    assert werkelijk.sort(SLEUTEL).equals(verwacht.sort(SLEUTEL))


def test_kzd_behaald_telt_niet_dubbel(demo_star):
    fi = demo_star["fact_inschrijving"]
    kzd = demo_star["fact_kzd"].drop_nulls(SLEUTEL)
    behaald = kzd["Resultaat"].str.to_uppercase().str.contains("BEHAALD").sum()
    assert fi["KZD_AantalBehaald"].sum() == behaald
