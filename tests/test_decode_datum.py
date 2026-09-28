"""Datums met onbekende dag of maand (``00``) blijven behouden (#206).

PvE 4.8.2 §15.5.2 (RO-PER): "De dag of de dag en maand kunnen leeg zijn. De dd
of de dd en mm worden dan gevuld met 00." Zo'n waarde is geldig en mag niet
null worden of als parseverlies tellen.
"""

from datetime import date

import polars as pl
import pytest

from mbo_bekostiging_bestanden.decode import decode_frames
from mbo_bekostiging_bestanden.quality import tel_parseverlies

# (formaat, [volledig, dag onbekend, dag+maand onbekend])
NOTATIES = {
    "iso": ["1992-05-17", "1992-05-00", "1992-00-00"],
    "compact": ["19920517", "19920500", "19920000"],
    "dutch": ["17-5-1992", "0-5-1992", "0-0-1992"],
}
VERWACHT = [date(1992, 5, 17), date(1992, 5, 1), date(1992, 1, 1)]
PRECISIE = ["dag", "maand", "jaar"]


def _per(geboortedata: list[str]) -> dict[str, pl.DataFrame]:
    return {"PER": pl.DataFrame({"Geboortedatum": geboortedata})}


@pytest.mark.parametrize("formaat", sorted(NOTATIES))
def test_datum_met_00_behoudt_jaar_en_maand(formaat):
    per = decode_frames(_per(NOTATIES[formaat]), "ro")["PER"]
    assert per["Geboortedatum"].to_list() == VERWACHT
    assert per["Geboortedatum_precisie"].to_list() == PRECISIE


@pytest.mark.parametrize("formaat", sorted(NOTATIES))
def test_datum_met_00_geen_parseverlies(formaat):
    ruw = _per(NOTATIES[formaat])
    assert tel_parseverlies(ruw, decode_frames(ruw, "ro")) == {}


def test_ongeldige_datum_blijft_parseverlies():
    ruw = _per(["1992-05-17", "1992-13-45"])
    per = decode_frames(ruw, "ro")["PER"]
    assert per["Geboortedatum_precisie"].to_list() == ["dag", None]
    assert tel_parseverlies(ruw, decode_frames(ruw, "ro")) == {
        "PER": {"Geboortedatum": 1}
    }


def test_lege_datum_heeft_geen_precisie():
    per = decode_frames(_per(["1992-05-17", ""]), "ro")["PER"]
    assert per["Geboortedatum_precisie"].to_list() == ["dag", None]


def test_00_alleen_voor_velden_die_het_pve_toestaat():
    """``DatumBegin`` staat geen 00 toe: blijft null + parseverlies."""
    ruw = {"ISP": pl.DataFrame({"DatumBegin": ["2024-08-01", "2024-08-00"]})}
    isp = decode_frames(ruw, "ro")["ISP"]
    assert isp["DatumBegin"].to_list() == [date(2024, 8, 1), None]
    assert "DatumBegin_precisie" not in isp.columns


def test_dim_deelnemer_bevat_precisie(demo_star):
    assert "Geboortedatum_precisie" in demo_star["dim_deelnemer"].columns
