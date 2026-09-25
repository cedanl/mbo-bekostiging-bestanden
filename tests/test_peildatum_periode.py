"""Telling op 1 oktober per ISP-periode, niet per inschrijving (#144).

Een inschrijving die op 1 oktober loopt, maakt nog niet elke periode ervan
actief: alleen de periode die 1 oktober dekt. De hoofdinschrijving wordt
alleen uit die periodes gekozen (DUO: één hoofdinschrijving per student per
instelling op peildatum 1 oktober). Synthetische data; de demo wordt niet
aangepast.
"""

from datetime import date

import polars as pl

from mbo_bekostiging_bestanden.transform import (
    _voeg_bekostigingsvlaggen_toe,
    _voeg_sr_vlaggen_toe,
    _voeg_telling_en_jr_vlaggen_toe,
)


def _perioden(*rijen: tuple, studiejaar: int = 2025) -> pl.DataFrame:
    """ISP-rijen van persoon P bij BRIN A: (volgnummer, begin, eind, niveau, crebo)."""
    return pl.DataFrame(
        {
            "levering": ["L"] * len(rijen),
            "BRIN": ["A"] * len(rijen),
            "_persoon_id": ["P"] * len(rijen),
            "Inschrijvingvolgnummer": [r[0] for r in rijen],
            "Studiejaar": [studiejaar] * len(rijen),
            "DatumInschrijving": [date(2023, 8, 1)] * len(rijen),
            "DatumUitschrijvingWerkelijk": [None] * len(rijen),
            "IndicatieBekostigbaar": ["J"] * len(rijen),
            "DatumBegin": [r[1] for r in rijen],
            "DatumEind": [r[2] for r in rijen],
            "Niveau": [r[3] for r in rijen],
            "Opleidingcode": [r[4] for r in rijen],
        },
        schema_overrides={"DatumUitschrijvingWerkelijk": pl.Date, "DatumEind": pl.Date},
    )


def _vlaggen(df: pl.DataFrame) -> pl.DataFrame:
    df = _voeg_sr_vlaggen_toe(_voeg_bekostigingsvlaggen_toe(df))
    return _voeg_telling_en_jr_vlaggen_toe(df)


def test_periode_die_na_1_oktober_begint_telt_niet():
    df = _vlaggen(
        _perioden(
            ("C1", date(2025, 8, 1), None, "MBO-3", "30000"),
            ("C1", date(2026, 1, 20), None, "MBO-4", "40000"),
        )
    )
    assert df["_actief_1_oktober"].to_list() == [True, False]
    assert df["_hoofdinschrijving"].to_list() == [True, False]


def test_eerdere_periode_met_hoger_niveau_wordt_geen_hoofdinschrijving():
    """GRONDSLAG: alle perioden van de inschrijving, peildatum 1-10-2025."""
    df = _vlaggen(
        _perioden(
            ("C1", date(2023, 8, 1), None, "MBO-4", "40000"),
            ("C1", date(2025, 8, 1), None, "MBO-2", "20000"),
        )
    )
    assert df["_actief_1_oktober"].to_list() == [False, True]
    assert df["_hoofdinschrijving"].to_list() == [False, True]
    assert df["_telling"].to_list() == [False, True]


def test_datum_eind_voor_1_oktober_sluit_periode_af():
    df = _vlaggen(
        _perioden(
            ("C1", date(2025, 8, 1), date(2025, 9, 15), "MBO-3", "30000"),
            ("C1", date(2025, 11, 1), None, "MBO-3", "30000"),
        )
    )
    assert df["_actief_1_oktober"].to_list() == [False, False]
    assert df["_hoofdinschrijving"].to_list() == [False, False]


def test_periode_eindigt_niet_op_begin_van_andere_inschrijving():
    df = _vlaggen(
        _perioden(
            ("C1", date(2025, 8, 1), None, "MBO-3", "30000"),
            ("C2", date(2025, 9, 1), None, "MBO-4", "40000"),
        )
    )
    assert df["_actief_1_oktober"].to_list() == [True, True]
    assert df["_hoofdinschrijving"].to_list() == [False, True]


def test_gelijke_begindatum_maakt_periode_niet_leeg():
    df = _vlaggen(
        _perioden(
            ("C1", date(2025, 8, 1), None, "MBO-3", "30000"),
            ("C1", date(2025, 8, 1), None, "MBO-3", "30000"),
        )
    )
    assert df["_actief_1_oktober"].to_list() == [True, True]
    assert sum(df["_hoofdinschrijving"].to_list()) == 1
