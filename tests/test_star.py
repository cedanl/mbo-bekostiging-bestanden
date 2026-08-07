"""Tests voor star.py (dimensionaal model)."""

import polars as pl

from mbo_bekostiging_bestanden.star import build_star


def _minimal_stacked() -> dict[str, pl.DataFrame]:
    """Minimale stacked-input voor alle drie dimensies en de feittabel."""
    isp = pl.DataFrame({
        "levering": ["h15/RO_X", "h15/RO_X", "h15/RO_X"],
        "Burgerservicenummer": ["P1", "P1", "P2"],
        "Inschrijvingvolgnummer": ["001", "002", "003"],
        "Opleidingcode": ["25655", "23301", "25655"],
        "Niveau": ["MBO-4", "MBO-1", "MBO-4"],
        "BRIN": ["01AA", "01AA", "02BB"],
        "Recordsoort": ["ISP", "ISP", "ISP"],
    })
    per = pl.DataFrame({
        "levering": ["h15/RO_X", "h15/RO_X"],
        "Burgerservicenummer": ["P1", "P2"],
        "Geslacht": ["M", "V"],
        "Recordsoort": ["PER", "PER"],
    })
    isg = pl.DataFrame(schema={
        "levering": pl.Utf8,
        "Burgerservicenummer": pl.Utf8,
        "Inschrijvingvolgnummer": pl.Utf8,
    })
    vlp = pl.DataFrame({
        "levering": ["h15/RO_X"],
        "BRIN": ["01AA"],
    })
    return {"ISP": isp, "PER": per, "ISG": isg, "VLP": vlp}


def test_star_bevat_alle_tabellen():
    """build_star retourneert tien tabellen (drie dims + zeven facts)."""
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
    }


def test_dim_deelnemer_uniek_op_persoon():
    """dim_deelnemer heeft één rij per _persoon_id."""
    result = build_star(_minimal_stacked())
    dim = result["dim_deelnemer"]
    assert dim.shape[0] == 2
    assert dim["_persoon_id"].to_list() == ["P1", "P2"]
    assert "Geslacht" in dim.columns


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
