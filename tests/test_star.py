"""Tests voor star.py (dimensionaal model)."""

import polars as pl

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
    assert dim["_persoon_id"].to_list() == ["P1", "P2"]
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


def test_meta_leveringen_bevat_vlp():
    """meta_leveringen bevat één rij per leveringsbestand uit VLP."""
    result = build_star(_minimal_stacked())
    meta = result["meta_leveringen"]
    assert not meta.is_empty()
    assert meta["levering"].to_list() == ["h15/RO_X"]
