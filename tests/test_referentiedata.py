"""Herkomst van de referentietabellen in ``metadata/`` (#132).

Niveau, hoofdinschrijving, JR en DR hangen voor RO aan ``crebo.csv`` en de
S-BB-koppeltabel. Het manifest legt per bestand vast waar het vandaan komt, tot
wanneer het de opleidingen dekt en welke inhoud (sha256) is gebruikt; de ster
en ``quality.json`` nemen dat over.
"""

from datetime import date
from pathlib import Path

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


# Herkomst vastgesteld (#316): de #19-bestanden zijn DUO-decodeerbestanden en
# crebo.csv komt van S-BB. "onbekend" mag niet meer voorkomen.


@pytest.mark.parametrize("bestand", _DATABESTANDEN)
def test_herkomst_is_bekend(bestand):
    regel = laad_manifest()[bestand]
    assert not regel["bron"].startswith("onbekend"), bestand
    # De DUO-decodeerbestanden zijn niet openbaar: dan het bronbestand.
    assert regel.get("bron_url") or regel.get("bron_bestand"), bestand


@pytest.mark.parametrize("bestand", referentiedata.OPLEIDINGSREFERENTIES)
def test_opleidingsreferentie_heeft_een_dekking(bestand):
    """Zonder dekking werkt de controle op codes na de dekking niet (#132)."""
    assert laad_manifest()[bestand].get("dekking_tot"), bestand


def test_dekking_van_crebo_volgt_uit_de_sbb_crebolijst():
    """``crebo.csv`` heeft geen datums; de dekking is de laatste dag van het
    schooljaar tot waarin álle S-BB-kwalificaties erin staan."""
    crebo = set(pl.read_csv(METADATA / "crebo.csv", infer_schema_length=0)["code"])
    sbb = pl.read_parquet(METADATA / "sbb_crebolijst.parquet")
    dekking = laad_manifest()["crebo.csv"]["dekking_tot"]
    binnen = sbb.filter(pl.col("geldig_van") <= dekking)["kwalificatiecode"]
    assert set(binnen) <= crebo
    na = sbb.filter(pl.col("geldig_van") > dekking)["kwalificatiecode"]
    assert not set(na) <= crebo, "de dekking kan later"


def test_sbb_crebolijst_bevat_alleen_kwalificatiecodes():
    """Een titelregel in het S-BB-Excelbestand gaf kopteksten als code."""
    codes = pl.read_parquet(METADATA / "sbb_crebolijst.parquet")["kwalificatiecode"]
    assert codes.str.contains(r"^\d{5}$").all(), codes.filter(
        ~codes.str.contains(r"^\d{5}$")
    ).to_list()


def test_updatescript_trimt_codes_en_laat_kopteksten_weg():
    import importlib.util

    pad = Path(__file__).parents[1] / "scripts" / "update_sbb_koppeltabel.py"
    spec = importlib.util.spec_from_file_location("update_sbb_koppeltabel", pad)
    assert spec and spec.loader
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    ruw = pl.DataFrame(
        {"kwalificatiecode": ["25617\xa0", "Crebonummer", "25618", None]}
    )
    assert script.kwalificatiecodes(ruw)["kwalificatiecode"].to_list() == [
        "25617",
        "25618",
    ]
