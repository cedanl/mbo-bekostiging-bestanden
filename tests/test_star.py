"""Tests voor star.py (dimensionaal model)."""

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline
from mbo_bekostiging_bestanden.stack import stack_prepared
from mbo_bekostiging_bestanden.star import (
    _PERSON_IDENTIFIER_COLS,
    _build_dim,
    build_star,
)
from mbo_bekostiging_bestanden.transform import pseudoniem


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
    """build_star retourneert dertien tabellen (drie dims + acht facts + twee meta)."""
    result = build_star(_minimal_stacked())
    assert set(result.keys()) == {
        "dim_deelnemer",
        "dim_opleiding",
        "dim_instelling",
        "fact_inschrijving",
        "fact_inschrijving_schooljaar",
        "fact_bpv",
        "fact_kzd",
        "fact_amo",
        "fact_geo",
        "fact_bekostiging",
        "fact_bekostiging_diploma",
        "meta_leveringen",
        "meta_canonicalisatie",
    }


def test_dim_deelnemer_uniek_op_persoon():
    """dim_deelnemer heeft één rij per _persoon_id."""
    result = build_star(_minimal_stacked())
    dim = result["dim_deelnemer"]
    assert dim.shape[0] == 2
    expected_personen = sorted([pseudoniem("BSN", "P1"), pseudoniem("BSN", "P2")])
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
    grain_key = [
        "levering",
        "_persoon_id",
        "Inschrijvingvolgnummer",
        "_inschrijving_periode_id",
    ]
    assert "_inschrijving_periode_id" in fact.columns
    unieke_sleutels = fact.select(grain_key).unique().shape[0]
    assert fact.shape[0] == unieke_sleutels, (
        f"fact_inschrijving is niet uniek op grain-sleutel: "
        f"{fact.shape[0]} rijen, {unieke_sleutels} unieke sleutels"
    )


def test_inschrijving_periode_id_is_deterministic():
    """Zelfde data → zelfde _inschrijving_periode_id (stable, reproduceerbaar).

    Hash van (levering, _persoon_id, Inschrijvingvolgnummer, DatumBegin).
    Vervangt de flaky 'niet-sequentiële volgorde'-assertie: de volgorde van een
    hash is geen eigenschap van de hash, determinisme wel.
    """
    ids_a = build_star(_minimal_stacked())["fact_inschrijving"][
        "_inschrijving_periode_id"
    ]
    ids_b = build_star(_minimal_stacked())["fact_inschrijving"][
        "_inschrijving_periode_id"
    ]

    assert ids_a.equals(ids_b)
    assert ids_a.null_count() == 0
    assert ids_a.len() == 3


def test_inschrijving_periode_id_is_rijvolgorde_onafhankelijk():
    """Herordenen van invoerrijen verandert de identifiers niet.

    Door rijen te herordenen wijzigt alleen de volgorde, niet de content van elke
    grain-sleutel; de set identifiers moet gelijk blijven (positioneel onafh.).
    """
    stacked = _minimal_stacked()
    herordend = {
        key: df.reverse() if df.height > 1 else df for key, df in stacked.items()
    }

    ids_a = sorted(
        build_star(_minimal_stacked())["fact_inschrijving"]["_inschrijving_periode_id"]
    )
    ids_b = sorted(
        build_star(herordend)["fact_inschrijving"]["_inschrijving_periode_id"]
    )

    assert ids_a == ids_b


def test_inschrijving_periode_id_volgt_uit_brondata():
    """Andere brondata (bijv. ander DatumBegin) geeft een andere identifier."""
    stacked = _minimal_stacked()
    isp = stacked["ISP"].with_columns(
        pl.when(pl.col("Inschrijvingvolgnummer") == "002")
        .then(pl.lit(date(2024, 2, 1)))
        .otherwise(pl.col("DatumBegin"))
        .alias("DatumBegin")
    )
    gewijzigd = {**stacked, "ISP": isp}

    ids_a = sorted(
        build_star(_minimal_stacked())["fact_inschrijving"]["_inschrijving_periode_id"]
    )
    ids_b = sorted(
        build_star(gewijzigd)["fact_inschrijving"]["_inschrijving_periode_id"]
    )

    assert ids_a != ids_b
    assert len(ids_a) == len(ids_b)


def test_inschrijving_periode_id_is_volledige_sha256():
    """De sleutel is de volledige SHA-256 (256 bit), niet een afgekapte prefix.

    Een 64-bit prefix heeft bij grote aantallen perioden een reëel
    collisionrisico zonder dat de pipeline dat merkt (#86).
    """
    ids = build_star(_minimal_stacked())["fact_inschrijving"][
        "_inschrijving_periode_id"
    ]
    sha256_hex = r"^[0-9a-f]{64}$"
    assert ids.str.contains(sha256_hex).all()


def test_meta_leveringen_bevat_vlp():
    """meta_leveringen bevat één rij per leveringsbestand uit VLP."""
    result = build_star(_minimal_stacked())
    meta = result["meta_leveringen"]
    assert not meta.is_empty()
    assert meta["levering"].to_list() == ["h15/RO_X"]


def test_no_person_identifiers_in_star_facts():
    """Feittabellen bevatten geen persoon-identifiers (BSN, ONr, PseudoNummer).

    _persoon_id mag wel (gehashed), maar ruwe identifiers niet.
    """
    result = build_star(_minimal_stacked())
    fact_tables = [k for k in result.keys() if k.startswith("fact_")]

    for table_name in fact_tables:
        df = result[table_name]
        found_identifiers = _PERSON_IDENTIFIER_COLS & set(df.columns)
        assert not found_identifiers, (
            f"{table_name} contains person identifiers: {found_identifiers}. "
            f"These must be removed before star export."
        )


RAW = Path("data/01-raw/demo")

# ---------------------------------------------------------------------------
# dim_instelling dekt alle BRIN's (#133)
# ---------------------------------------------------------------------------


def _brins(tabel: pl.DataFrame) -> set[str]:
    if "BRIN" not in tabel.columns:
        return set()
    return set(tabel["BRIN"].drop_nulls().to_list())


@pytest.fixture(scope="module")
def star_ro_27dv_met_tbgi_25lx(tmp_path_factory):
    """RO van 27DV plus TBGI van 25LX: 25LX komt alleen in de bekostiging voor.

    In de ISP-route tellen TBGI-inschrijvingen niet mee in ``inschrijvingen``.
    """
    prepared = tmp_path_factory.mktemp("prepared_ro_tbgi")
    bronnen = [
        RAW / "h15" / "RO_27DV_20240731_20260324.csv",
        RAW / "h16" / "TBGI_25LX_2027_20251124.XML",
    ]
    dirs = []
    for bron in bronnen:
        doel = prepared / bron.parent.name / bron.stem
        run_auto_pipeline(bron, doel)
        dirs.append(doel)
    return build_star(stack_prepared(dirs, relative_to=prepared))


def test_dim_instelling_bevat_elke_brin_uit_de_feiten(star_ro_27dv_met_tbgi_25lx):
    star = star_ro_27dv_met_tbgi_25lx
    in_feiten = set().union(
        *(_brins(t) for naam, t in star.items() if naam.startswith("fact_"))
    )
    assert in_feiten == {"27DV", "25LX"}
    assert _brins(star["dim_instelling"]) == in_feiten


def test_dim_instelling_verrijkt_brin_uit_bekostiging(star_ro_27dv_met_tbgi_25lx):
    dim = star_ro_27dv_met_tbgi_25lx["dim_instelling"]
    assert dim.filter(pl.col("BRIN") == "25LX")["Instelling_naam"].to_list() == [
        "Curio"
    ]
