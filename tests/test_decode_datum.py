"""Datums met onbekende dag of maand (``00``) blijven behouden (#206).

PvE 4.8.2 §15.5.2 (RO-PER): "De dag of de dag en maand kunnen leeg zijn. De dd
of de dd en mm worden dan gevuld met 00." Zo'n waarde is geldig en mag niet
null worden of als parseverlies tellen.
"""

from datetime import date

import polars as pl
import pytest

from mbo_bekostiging_bestanden.decode import decode_frames
from mbo_bekostiging_bestanden.quality import tel_onbekende_datums, tel_parseverlies

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


ONBEKEND_JAAR = {
    "iso": ["0000-00-00", "0000-05-17"],
    "compact": ["00000000", "00000517"],
    "dutch": ["0-0-0000", "17-5-0000"],
}


@pytest.mark.parametrize("formaat", sorted(ONBEKEND_JAAR))
def test_onbekend_jaar_wordt_null_met_precisie_onbekend(formaat):
    """#391: jaar 0 werd 0000-01-01, onleesbaar voor Python ``datetime``."""
    per = decode_frames(_per(ONBEKEND_JAAR[formaat]), "ro")["PER"]
    assert per["Geboortedatum"].to_list() == [None, None]
    assert per["Geboortedatum_precisie"].to_list() == ["onbekend", "onbekend"]


def test_onbekend_jaar_is_geen_parseverlies_maar_wel_geteld():
    """Het PvE kent geen jaar 0; de waarde is een bewuste 'onbekend', geen
    parsefout. Daarom een warning en geen error (#390)."""
    ruw = _per(["1992-05-17", "0000-00-00", ""])
    getypeerd = decode_frames(ruw, "ro")
    assert tel_parseverlies(ruw, getypeerd) == {}
    assert tel_onbekende_datums(getypeerd) == {"PER": {"Geboortedatum": 1}}


def test_jaar_0_zonder_00_toestemming_blijft_parseverlies():
    ruw = {"ISP": pl.DataFrame({"DatumBegin": ["0000-08-01"]})}
    isp = decode_frames(ruw, "ro")["ISP"]
    assert isp["DatumBegin"].to_list() == [None]
    assert tel_parseverlies(ruw, {"ISP": isp}) == {"ISP": {"DatumBegin": 1}}


def test_dim_deelnemer_bevat_precisie(demo_star):
    assert "Geboortedatum_precisie" in demo_star["dim_deelnemer"].columns


# Notatie per cel in plaats van uit één voorbeeldcel voor het hele bestand
# (#417): één lege of ongeldige eerste datum maakte alle andere datums null.


def test_gemengde_notaties_in_een_kolom_parsen_allemaal():
    per = decode_frames(_per(["1992-05-17", "17-5-1992", "19920517"]), "ro")["PER"]
    assert per["Geboortedatum"].to_list() == [date(1992, 5, 17)] * 3


def test_ongeldige_eerste_datum_kost_alleen_zichzelf():
    ruw = {
        "VLP": pl.DataFrame({"DatumBeginPeriode": ["not-a-date"]}),
        "ISG": pl.DataFrame({"DatumInschrijving": ["1-8-2025", "2025-08-02"]}),
    }
    getypeerd = decode_frames(ruw, "ro")
    assert getypeerd["ISG"]["DatumInschrijving"].to_list() == [
        date(2025, 8, 1),
        date(2025, 8, 2),
    ]
    assert tel_parseverlies(ruw, getypeerd) == {"VLP": {"DatumBeginPeriode": 1}}


@pytest.mark.parametrize("ongeldig", ["2025-8-1x", "1-8-25", "2025/08/01", "202508"])
def test_onbekende_notatie_is_parseverlies(ongeldig):
    ruw = {"ISG": pl.DataFrame({"DatumInschrijving": [ongeldig]})}
    assert tel_parseverlies(ruw, decode_frames(ruw, "ro")) == {
        "ISG": {"DatumInschrijving": 1}
    }
