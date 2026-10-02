"""De privacygrens ligt bij decode: brondata bevat geen persoonsidentifiers (#173).

Voorheen pseudonimiseerde pas de sterbouw; ``02-prepared`` bevatte BSN,
onderwijsnummer en PGN in platte tekst en was zo niet deelbaar (#172, #212).
Nu vervangt :func:`decode_frames` die kolommen door het pseudoniem
``_persoon_id``. De ruwe levering in ``01-raw`` blijft de auditbron.
"""

from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden import identiteit
from mbo_bekostiging_bestanden.cli import main
from mbo_bekostiging_bestanden.decode import decode_ro
from mbo_bekostiging_bestanden.identiteit import PERSOON_COLS, pseudoniem
from mbo_bekostiging_bestanden.ingest import read_ro
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline
from mbo_bekostiging_bestanden.stack import stack_prepared

RAW = Path("data/01-raw/demo")
DEMO_RO = RAW / "h15" / "RO_21CY_20250730_20250731.csv"
DEMO_BESTANDEN = sorted(
    p for p in RAW.rglob("*") if p.suffix.lower() in {".csv", ".xml"}
)


def test_decode_vervangt_identifiers_door_het_pseudoniem():
    ruw = read_ro(DEMO_RO)
    getypeerd = decode_ro(ruw)

    per = getypeerd["PER"]
    assert not set(PERSOON_COLS) & set(per.columns)
    eerste_bsn = ruw["PER"]["Burgerservicenummer"][0]
    assert per["_persoon_id"][0] == pseudoniem("BSN", eerste_bsn)
    # Recordtypes zonder persoon krijgen geen lege pseudoniemkolom.
    assert "_persoon_id" not in getypeerd["VLP"].columns


@pytest.mark.parametrize("bron", DEMO_BESTANDEN, ids=lambda p: p.name)
def test_brondata_bevat_geen_identifiers(bron, tmp_path):
    ruwe_waarden = _identifierwaarden(bron)
    doel = tmp_path / "prepared"
    run_auto_pipeline(bron, doel)

    for parquet in doel.glob("*.parquet"):
        df = pl.read_parquet(parquet)
        assert not set(PERSOON_COLS) & set(df.columns), parquet.name
        for kolom in df.select(pl.col(pl.Utf8)).columns:
            assert not ruwe_waarden & set(df[kolom].drop_nulls()), (parquet.name, kolom)


# Korte demo-identifiers ("1") vallen samen met volgnummers; die zeggen niets.
_MIN_LENGTE = 6


def _identifierwaarden(bron: Path) -> set[str]:
    """De ruwe BSN/ONr/PGN-waarden in de levering die als lek herkenbaar zijn."""
    from mbo_bekostiging_bestanden.ingest import read_grondslag, read_tbgi

    lezer = {"RO": read_ro, "GRONDSLAG": read_grondslag, "TBGI": read_tbgi}
    frames = lezer[bron.name.split("_")[0]](bron)
    return {
        waarde
        for df in frames.values()
        for kolom in PERSOON_COLS
        if kolom in df.columns
        for waarde in df[kolom].drop_nulls()
        if len(waarde.strip()) >= _MIN_LENGTE
    }


def test_verwerken_zonder_salt_faalt(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MBO_PSEUDONIMISERING_SALT", raising=False)
    monkeypatch.setattr(identiteit, "_DEMO_CONFIG", tmp_path / "bestaat_niet.toml")
    identiteit.laad_pseudonimisering_salt.cache_clear()
    monkeypatch.setattr(
        "sys.argv", ["mbo", "verwerk", str(DEMO_RO), str(tmp_path / "prepared")]
    )
    try:
        with pytest.raises(SystemExit) as uit:
            main()
    finally:
        identiteit.laad_pseudonimisering_salt.cache_clear()
    assert uit.value.code == 1
    assert "MBO_PSEUDONIMISERING_SALT" in capsys.readouterr().err
    assert not (tmp_path / "prepared").exists()


def test_brondata_van_voor_v4_wordt_geweigerd(tmp_path):
    """Oude brondata met identifiers moet opnieuw verwerkt worden."""
    oud = tmp_path / "oud"
    oud.mkdir()
    pl.DataFrame({"Burgerservicenummer": ["123456782"]}).write_parquet(
        oud / "PER.parquet"
    )
    with pytest.raises(ValueError, match="opnieuw"):
        stack_prepared([oud])
