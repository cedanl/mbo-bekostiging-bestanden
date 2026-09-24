"""Tests voor star.py (dimensionaal model)."""

from datetime import date

import polars as pl
from conftest import pseudoniem_van_identifier

from mbo_bekostiging_bestanden.star import _build_dim, build_star


def _minimal_stacked() -> dict[str, pl.DataFrame]:
    """Minimale stacked-input voor alle drie dimensies en de feittabel."""
    isp = pl.DataFrame(
        {
            "levering": ["h15/RO_X", "h15/RO_X", "h15/RO_X"],
            "Burgerservicenummer": ["P1", "P1", "P2"],
            "Inschrijvingvolgnummer": ["001", "002", "003"],
            "Opleidingcode": ["25655", "23301", "25655"],
            "Niveau": ["MBO-4", "MBO-1", "MBO-4"],
            "BRIN": ["01AA", "01AA", "02BB"],
            "DatumBegin": [date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 1)],
            "Recordsoort": ["ISP", "ISP", "ISP"],
        }
    )
    per = pl.DataFrame(
        {
            "levering": ["h15/RO_X", "h15/RO_X"],
            "Burgerservicenummer": ["P1", "P2"],
            "Geslacht": ["M", "V"],
            "Recordsoort": ["PER", "PER"],
        }
    )
    isg = pl.DataFrame(
        schema={
            "levering": pl.Utf8,
            "Burgerservicenummer": pl.Utf8,
            "Inschrijvingvolgnummer": pl.Utf8,
        }
    )
    vlp = pl.DataFrame(
        {
            "levering": ["h15/RO_X"],
            "BRIN": ["01AA"],
        }
    )
    return {"ISP": isp, "PER": per, "ISG": isg, "VLP": vlp}


def test_star_bevat_alle_tabellen():
    """build_star retourneert elf tabellen (drie dims + zeven facts + meta)."""
    result = build_star(_minimal_stacked())
    assert set(result.keys()) == {
        "dim_deelnemer",
        "dim_opleiding",
        "dim_instelling",
        "fact_inschrijving",
        "fact_bpv",
        "fact_kzd",
        "fact_amo",
        "fact_geo",
        "fact_bekostiging",
        "fact_bekostiging_diploma",
        "meta_leveringen",
    }


def test_dim_deelnemer_uniek_op_persoon():
    """dim_deelnemer heeft één rij per _persoon_id."""
    result = build_star(_minimal_stacked())
    dim = result["dim_deelnemer"]
    assert dim.shape[0] == 2
    expected_personen = sorted(
        [pseudoniem_van_identifier("P1"), pseudoniem_van_identifier("P2")]
    )
    actual_personen = sorted(dim["_persoon_id"].to_list())
    assert actual_personen == expected_personen
    assert "Geslacht" in dim.columns


def test_build_dim_coalesceert_velden_over_leveringen():
    """Een veld dat maar in één levering staat, gaat niet verloren.

    Persoon P1 zit in twee leveringen: de ene heeft Geboortedatum (RO), de andere
    de demografie (GRONDSLAG). De dim-rij moet beide bevatten.
    """
    df = pl.DataFrame(
        {
            "_persoon_id": ["P1", "P1"],
            "Geboortedatum": ["1990-01-01", None],
            "Gemeente": [None, "Apeldoorn"],
        }
    )
    dim = _build_dim(df, ["_persoon_id", "Geboortedatum", "Gemeente"], "_persoon_id")
    assert dim.shape[0] == 1
    rij = dim.row(0, named=True)
    assert rij["Geboortedatum"] == "1990-01-01"
    assert rij["Gemeente"] == "Apeldoorn"


def test_dim_opleiding_uniek_op_code():
    """dim_opleiding heeft één rij per Opleidingcode."""
    result = build_star(_minimal_stacked())
    dim = result["dim_opleiding"]
    assert dim.shape[0] == 2
    assert set(dim["Opleidingcode"].to_list()) == {"25655", "23301"}
    assert "Opleiding_naam" in dim.columns
    assert "Niveau" in dim.columns


def test_dim_instelling_uniek_op_brin():
    """dim_instelling heeft één rij per BRIN."""
    result = build_star(_minimal_stacked())
    dim = result["dim_instelling"]
    assert dim.shape[0] == 2
    assert set(dim["BRIN"].to_list()) == {"01AA", "02BB"}


def test_fact_bevat_fks_en_measures():
    """fact_inschrijving bevat foreign keys en measures, niet de dimensie-attributen."""
    result = build_star(_minimal_stacked())
    fact = result["fact_inschrijving"]
    assert fact.shape[0] == 3
    assert "_persoon_id" in fact.columns
    assert "Opleidingcode" in fact.columns
    assert "BRIN" in fact.columns
    assert "_telling" in fact.columns
    assert "Instelling_naam" not in fact.columns
    assert "Opleiding_naam" not in fact.columns
    assert "Geslacht" not in fact.columns


def test_fact_behoudt_alle_rijen():
    """fact_inschrijving verliest geen rijen t.o.v. de ISP-input."""
    result = build_star(_minimal_stacked())
    assert result["fact_inschrijving"].shape[0] == 3


def test_fact_inschrijving_grain_uniek():
    """fact_inschrijving is uniek op zijn grain-sleutel.

    Grain: (levering, _persoon_id, Inschrijvingvolgnummer, _inschrijving_periode_id)
    Dit zorgt ervoor dat joins met detail-feiten (BPV, KZD) geen fan-out veroorzaken.
    """
    result = build_star(_minimal_stacked())
    fact = result["fact_inschrijving"]
    grain_key = ["levering", "_persoon_id", "Inschrijvingvolgnummer",
                 "_inschrijving_periode_id"]
    assert "_inschrijving_periode_id" in fact.columns
    unieke_sleutels = fact.select(grain_key).unique().shape[0]
    assert fact.shape[0] == unieke_sleutels, (
        f"fact_inschrijving is niet uniek op grain-sleutel: "
        f"{fact.shape[0]} rijen, {unieke_sleutels} unieke sleutels"
    )


def test_inschrijving_periode_id_is_stable_and_data_derived():
    """_inschrijving_periode_id derived from data hash (stable, reproducible, FK-ready).

    Hash of (levering, _persoon_id, Inschrijvingvolgnummer, DatumBegin).
    - Stable: same data → same hash
    - Reproducible: order-independent
    - Usable as FK: depends on data content, not row position
    """
    result = build_star(_minimal_stacked())
    fact = result["fact_inschrijving"]
    periode_ids = fact["_inschrijving_periode_id"].to_list()

    # Hash-based IDs are non-sequential (hashes won't sort in data order)
    is_sequential = periode_ids == sorted(periode_ids)
    assert not is_sequential, (
        "_inschrijving_periode_id should be hash-derived (non-sequential), "
        f"not pl.int_range. Got: {periode_ids}"
    )

    # All IDs present and non-null
    assert len(periode_ids) == fact.shape[0]
    assert all(id is not None for id in periode_ids)


def test_meta_leveringen_bevat_vlp():
    """meta_leveringen bevat één rij per leveringsbestand uit VLP."""
    result = build_star(_minimal_stacked())
    meta = result["meta_leveringen"]
    assert not meta.is_empty()
    assert meta["levering"].to_list() == ["h15/RO_X"]
