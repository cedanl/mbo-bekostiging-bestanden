"""Tests voor canonicalisatie van overlappende leveringen (#134, #174).

Een levering is een bronbestand, geen tellingseenheid: staat dezelfde
inschrijving (instelling × persoon × inschrijvingvolgnummer) in meerdere
leveringen, dan telt alleen die uit de meest recente levering. Detailfeiten
volgen de gekozen levering van hun inschrijving.
"""

import shutil
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.canonicalisatie import (
    vervangen_inschrijvingen,
    verwijder_vervangen,
)
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline, run_star

RO_27DV = Path("data/01-raw/demo/h15/RO_27DV_20240731_20260324.csv")
_FEITEN = ("fact_inschrijving", "fact_bpv", "fact_kzd", "fact_geo", "fact_amo")


def _isp(*rijen: tuple[str, str, str, str]) -> pl.DataFrame:
    """ISP-sleutels: (levering, BRIN, _persoon_id, Inschrijvingvolgnummer)."""
    return pl.DataFrame(
        rijen,
        schema=["levering", "BRIN", "_persoon_id", "Inschrijvingvolgnummer"],
        orient="row",
    )


def _vlp(*rijen: tuple[str, date]) -> pl.DataFrame:
    """VLP per levering: (levering, DatumAanmaak)."""
    return pl.DataFrame(rijen, schema=["levering", "DatumAanmaak"], orient="row")


def _vervangen_sleutels(vervangen: pl.DataFrame) -> set[tuple[str, str, str]]:
    return set(
        vervangen.select("levering", "_persoon_id", "Inschrijvingvolgnummer").rows()
    )


# ---------------------------------------------------------------------------
# vervangen_inschrijvingen
# ---------------------------------------------------------------------------


def test_zelfde_inschrijving_recentste_levering_wint():
    isp = _isp(("L_oud", "27DV", "P", "1"), ("L_nieuw", "27DV", "P", "1"))
    vlp = _vlp(("L_oud", date(2025, 1, 1)), ("L_nieuw", date(2025, 6, 1)))

    assert _vervangen_sleutels(vervangen_inschrijvingen(isp, vlp)) == {
        ("L_oud", "P", "1")
    }


def test_recentheid_volgt_aanmaakdatum_niet_leveringsnaam():
    """Alfabetische volgorde van labels (incl. submap) zegt niets over recentheid."""
    isp = _isp(("h99/RO_oud", "27DV", "P", "1"), ("h15/RO_nieuw", "27DV", "P", "1"))
    vlp = _vlp(("h99/RO_oud", date(2024, 1, 1)), ("h15/RO_nieuw", date(2025, 1, 1)))

    assert _vervangen_sleutels(vervangen_inschrijvingen(isp, vlp)) == {
        ("h99/RO_oud", "P", "1")
    }


def test_gelijke_aanmaakdatum_leveringsnaam_beslist():
    isp = _isp(("L_a", "27DV", "P", "1"), ("L_b", "27DV", "P", "1"))
    vlp = _vlp(("L_a", date(2025, 1, 1)), ("L_b", date(2025, 1, 1)))

    assert _vervangen_sleutels(vervangen_inschrijvingen(isp, vlp)) == {
        ("L_a", "P", "1")
    }


def test_andere_instelling_is_andere_inschrijving():
    """Inschrijvingvolgnummer is niet instellingsoverstijgend uniek."""
    isp = _isp(("L_a", "21CY", "P", "1"), ("L_b", "27DV", "P", "1"))
    vlp = _vlp(("L_a", date(2025, 1, 1)), ("L_b", date(2025, 6, 1)))

    assert vervangen_inschrijvingen(isp, vlp).is_empty()


def test_ander_identifierdomein_is_andere_persoon():
    """RO (BSN/ONR) en GRONDSLAG (PGN) delen nooit een ``_persoon_id`` (#128)."""
    isp = _isp(("RO", "27DV", "BSN-hash", "1"), ("GRONDSLAG", "27DV", "PGN-hash", "1"))
    vlp = _vlp(("RO", date(2025, 1, 1)), ("GRONDSLAG", date(2025, 6, 1)))

    assert vervangen_inschrijvingen(isp, vlp).is_empty()


def test_per_inschrijving_niet_per_levering():
    """Een inschrijving die alleen in de oude levering staat, blijft staan."""
    isp = _isp(
        ("L_oud", "27DV", "P", "1"),
        ("L_oud", "27DV", "P", "2"),
        ("L_nieuw", "27DV", "P", "1"),
    )
    vlp = _vlp(("L_oud", date(2025, 1, 1)), ("L_nieuw", date(2025, 6, 1)))

    assert _vervangen_sleutels(vervangen_inschrijvingen(isp, vlp)) == {
        ("L_oud", "P", "1")
    }


def test_meerdere_perioden_per_inschrijving_geven_een_vervangen_sleutel():
    isp = _isp(
        ("L_oud", "27DV", "P", "1"),
        ("L_oud", "27DV", "P", "1"),
        ("L_nieuw", "27DV", "P", "1"),
    )
    vlp = _vlp(("L_oud", date(2025, 1, 1)), ("L_nieuw", date(2025, 6, 1)))

    assert vervangen_inschrijvingen(isp, vlp).height == 1


# ---------------------------------------------------------------------------
# verwijder_vervangen
# ---------------------------------------------------------------------------


def test_verwijder_vervangen_filtert_alleen_vervangen_inschrijvingen():
    vervangen = pl.DataFrame(
        {"levering": ["L_oud"], "_persoon_id": ["P"], "Inschrijvingvolgnummer": ["1"]}
    )
    detail = pl.DataFrame(
        {
            "levering": ["L_oud", "L_oud", "L_nieuw", "TBGI"],
            "_persoon_id": ["P", "P", "P", "P"],
            "Inschrijvingvolgnummer": ["1", "2", "1", "1"],
        }
    )

    rest = verwijder_vervangen(detail, vervangen)

    assert set(rest.rows()) == {
        ("L_oud", "P", "2"),
        ("L_nieuw", "P", "1"),
        ("TBGI", "P", "1"),
    }


def test_verwijder_vervangen_laat_tabel_zonder_inschrijvingssleutel_ongemoeid():
    vervangen = pl.DataFrame(
        {"levering": ["L_oud"], "_persoon_id": ["P"], "Inschrijvingvolgnummer": ["1"]}
    )
    meta = pl.DataFrame({"levering": ["L_oud", "L_nieuw"]})

    assert verwijder_vervangen(meta, vervangen).equals(meta)


# ---------------------------------------------------------------------------
# End-to-end: run_star met overlappende leveringen
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ro_27dv(tmp_path_factory) -> Path:
    """Prepared-map van één echte (demo) RO-levering."""
    doel = tmp_path_factory.mktemp("prepared") / "h15" / RO_27DV.stem
    run_auto_pipeline(RO_27DV, doel)
    return doel


def _kopieer_levering(bron: Path, doel: Path, aanmaakdatum: date | None = None) -> Path:
    shutil.copytree(bron, doel)
    if aanmaakdatum is not None:
        vlp = pl.read_parquet(doel / "VLP.parquet")
        vlp.with_columns(pl.lit(aanmaakdatum).alias("DatumAanmaak")).write_parquet(
            doel / "VLP.parquet"
        )
    return doel


def _hoogtes(star: dict[str, pl.DataFrame]) -> dict[str, int]:
    return {naam: star[naam].height for naam in _FEITEN if naam in star}


def test_dubbele_levering_telt_eenmaal(ro_27dv, tmp_path):
    kopie = _kopieer_levering(ro_27dv, tmp_path / "h15" / "RO_27DV_kopie")

    enkel = run_star([ro_27dv], tmp_path / "enkel")
    dubbel = run_star([ro_27dv, kopie], tmp_path / "dubbel")

    assert enkel["fact_inschrijving"].height > 0
    assert _hoogtes(dubbel) == _hoogtes(enkel)


def test_dubbele_levering_indicatoren_gelijk_aan_enkele(ro_27dv, tmp_path):
    kopie = _kopieer_levering(ro_27dv, tmp_path / "h15" / "RO_27DV_kopie")
    vlaggen = ["_actief_1_oktober", "_hoofdinschrijving", "_telling", "_jr_noemer"]

    enkel = run_star([ro_27dv], tmp_path / "enkel")["fact_inschrijving"]
    dubbel = run_star([ro_27dv, kopie], tmp_path / "dubbel")["fact_inschrijving"]

    assert dubbel.select(pl.col(vlaggen).sum()).equals(
        enkel.select(pl.col(vlaggen).sum())
    )


def test_correctielevering_wint_op_aanmaakdatum(ro_27dv, tmp_path):
    """Recentere levering wint, ook als haar label alfabetisch eerder komt."""
    origineel = _kopieer_levering(ro_27dv, tmp_path / "h15" / ro_27dv.name)
    vlp = pl.read_parquet(origineel / "VLP.parquet")
    later = vlp["DatumAanmaak"][0] + timedelta(days=1)
    correctie = _kopieer_levering(ro_27dv, tmp_path / "h00" / "A_correctie", later)

    feit = run_star([origineel, correctie], tmp_path / "uit", relative_to=tmp_path)[
        "fact_inschrijving"
    ]

    assert feit["levering"].unique().to_list() == ["h00/A_correctie"]
