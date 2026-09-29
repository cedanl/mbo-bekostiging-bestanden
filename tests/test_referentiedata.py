"""Herkomst van de referentietabellen in ``metadata/`` (#132).

Niveau, hoofdinschrijving, JR en DR hangen voor RO aan ``crebo.csv`` en de
S-BB-koppeltabel. Het manifest legt per bestand vast waar het vandaan komt, tot
wanneer het de opleidingen dekt en welke inhoud (sha256) is gebruikt; de ster
en ``quality.json`` nemen dat over.
"""

from datetime import date

import polars as pl
import pytest

from mbo_bekostiging_bestanden import referentiedata
from mbo_bekostiging_bestanden.quality import (
    compile_quality_report,
    kwaliteitsmeldingen,
)
from mbo_bekostiging_bestanden.referentiedata import (
    METADATA,
    laad_manifest,
    meta_referentiedata,
)

_DATABESTANDEN = sorted(
    p.name for p in METADATA.iterdir() if p.suffix in {".csv", ".parquet"}
)


def test_manifest_dekt_elk_referentiebestand():
    assert sorted(laad_manifest()) == _DATABESTANDEN


@pytest.mark.parametrize("bestand", _DATABESTANDEN)
def test_manifest_klopt_met_de_inhoud(bestand):
    """Faalt na een update zonder manifest-update (``werk_manifest_bij``)."""
    regel = laad_manifest()[bestand]
    assert regel["sha256"] == referentiedata.sha256(METADATA / bestand)
    assert regel["rijen"] == referentiedata.rijen(METADATA / bestand)


@pytest.mark.parametrize("bestand", _DATABESTANDEN)
def test_manifest_noemt_bron_en_opname(bestand):
    regel = laad_manifest()[bestand]
    assert regel["bron"]
    date.fromisoformat(regel["opgenomen"])


def test_meta_referentiedata_is_een_rij_per_bestand():
    meta = meta_referentiedata()
    assert sorted(meta["bestand"]) == _DATABESTANDEN
    assert not meta["afwijkend"].any()


def test_afwijkend_bestand_valt_op(tmp_path, monkeypatch):
    """Lokaal vervangen zonder manifest-update: de run noemt de afwijking."""
    (tmp_path / "crebo.csv").write_text("code,niveau\n1,2\n", encoding="utf-8")
    manifest = "referentiedata.json"
    (tmp_path / manifest).write_bytes((METADATA / manifest).read_bytes())
    monkeypatch.setattr(referentiedata, "METADATA", tmp_path)
    meta = meta_referentiedata()
    assert meta.filter(pl.col("bestand") == "crebo.csv")["afwijkend"].item()


def _ster(codes: list[str], begin: date, dekking_tot: date | None) -> dict:
    return {
        "fact_inschrijving": pl.DataFrame(
            {"Opleidingcode": codes, "DatumBegin": [begin] * len(codes)}
        ),
        "meta_referentiedata": pl.DataFrame(
            {
                "bestand": ["crebo.csv", "sbb_koppeltabel.parquet"],
                "bron": ["x", "y"],
                "opgenomen": [date(2026, 8, 6)] * 2,
                "dekking_tot": [None, dekking_tot],
                "sha256": ["a", "b"],
                "rijen": [1, 1],
                "afwijkend": [False, False],
            },
            schema_overrides={"dekking_tot": pl.Date},
        ),
    }


def _waarschuwingen(ster: dict) -> list[str]:
    rapport = compile_quality_report(ster)
    return [m.tekst for m in kwaliteitsmeldingen(rapport) if m.ernst == "warning"]


def test_onbekende_code_na_de_dekking_waarschuwt_voor_een_oude_referentie():
    ster = _ster(["99999", "10002"], date(2027, 8, 1), date(2027, 7, 31))
    rapport = compile_quality_report(ster)

    na_dekking = rapport["star"]["referentiedata"]["onbekende_codes_na_dekking"]

    assert na_dekking == {"dekking_tot": "2027-07-31", "codes": ["99999"]}
    assert any("99999" in t and "referentie" in t for t in _waarschuwingen(ster))


def test_onbekende_code_binnen_de_dekking_is_geen_referentieprobleem():
    """Dan is de code onbekend, niet de referentie oud (zie niveau_issues)."""
    ster = _ster(["99999"], date(2026, 8, 1), date(2027, 7, 31))
    assert not any("referentie" in t for t in _waarschuwingen(ster))


def test_afwijkend_referentiebestand_waarschuwt():
    ster = _ster(["10002"], date(2026, 8, 1), date(2027, 7, 31))
    ster["meta_referentiedata"] = ster["meta_referentiedata"].with_columns(
        (pl.col("bestand") == "crebo.csv").alias("afwijkend")
    )
    assert any("crebo.csv" in t for t in _waarschuwingen(ster))


def test_ster_bevat_meta_referentiedata(demo_star):
    assert demo_star["meta_referentiedata"].height == len(_DATABESTANDEN)
