"""Pseudonimiseren of identifiers behouden: een expliciete keuze (#435).

Pseudonimiseren is de standaard en blijft fail-closed zonder salt. Identifiers
behouden is opt-in voor een vertrouwde omgeving; een ontbrekende salt schakelt
die modus nooit in.
"""

from pathlib import Path

import polars as pl
import pytest

from mbo_bekostiging_bestanden import identiteit
from mbo_bekostiging_bestanden.cli import main
from mbo_bekostiging_bestanden.decode import decode_ro
from mbo_bekostiging_bestanden.identiteit import (
    PERSOON_COLS,
    PERSOON_ID,
    Persoonsverwerking,
    ongezouten_pseudoniem,
)
from mbo_bekostiging_bestanden.ingest import read_ro
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline, run_star
from mbo_bekostiging_bestanden.quality import (
    PROFIEL_GEPSEUDONIMISEERD,
    PROFIEL_IDENTIFIERS_BEHOUDEN,
)

RAW = Path("data/01-raw/demo")
DEMO_RO = RAW / "h15" / "RO_21CY_20250730_20250731.csv"
BEHOUDEN = Persoonsverwerking.IDENTIFIERS_BEHOUDEN


@pytest.fixture
def zonder_salt(monkeypatch, tmp_path):
    monkeypatch.delenv("MBO_PSEUDONIMISERING_SALT", raising=False)
    monkeypatch.setattr(identiteit, "_DEMO_CONFIG", tmp_path / "bestaat_niet.toml")
    identiteit.laad_pseudonimisering_salt.cache_clear()
    yield
    identiteit.laad_pseudonimisering_salt.cache_clear()


def test_pseudonimiseren_is_de_standaard():
    assert Persoonsverwerking.PSEUDONIMISEREN.value == "pseudonimiseren"
    per = decode_ro(read_ro(DEMO_RO))["PER"]
    assert not set(PERSOON_COLS) & set(per.columns)


def test_ontbrekende_salt_schakelt_identifiers_behouden_niet_in(zonder_salt):
    with pytest.raises(ValueError, match="MBO_PSEUDONIMISERING_SALT"):
        decode_ro(read_ro(DEMO_RO))


def test_decode_behoudt_identifiers_zonder_salt(zonder_salt):
    ruw = read_ro(DEMO_RO)
    per = decode_ro(ruw, BEHOUDEN)["PER"]

    assert {"Burgerservicenummer", "Onderwijsnummer"} <= set(per.columns)
    assert per["Burgerservicenummer"].to_list() == [
        w or None for w in ruw["PER"]["Burgerservicenummer"]
    ]
    assert PERSOON_ID in per.columns


def test_persoon_id_in_behoudmodus_is_stabiel_en_ongezouten(zonder_salt):
    """Zelfde persoon → zelfde sleutel, ook zonder geheim; domein blijft gescheiden."""
    per = decode_ro(read_ro(DEMO_RO), BEHOUDEN)["PER"]
    bsn = per.filter(pl.col("Burgerservicenummer").is_not_null())
    eerste = bsn.row(0, named=True)

    assert eerste[PERSOON_ID] == ongezouten_pseudoniem(
        "BSN", eerste["Burgerservicenummer"]
    )
    assert ongezouten_pseudoniem("BSN", "123456782") != ongezouten_pseudoniem(
        "ONR", "123456782"
    )


def test_brondata_in_behoudmodus_bevat_identifiers_en_profiel(tmp_path, zonder_salt):
    doel = tmp_path / "prepared"
    run_auto_pipeline(DEMO_RO, doel, persoonsverwerking=BEHOUDEN)

    per = pl.read_parquet(doel / "PER.parquet")
    assert "Burgerservicenummer" in per.columns
    rapport = (doel / "quality.json").read_text(encoding="utf-8")
    assert f'"privacyprofiel": "{PROFIEL_IDENTIFIERS_BEHOUDEN}"' in rapport


def test_brondata_in_standaardmodus_houdt_het_profiel_gepseudonimiseerd(tmp_path):
    doel = tmp_path / "prepared"
    run_auto_pipeline(DEMO_RO, doel)

    rapport = (doel / "quality.json").read_text(encoding="utf-8")
    assert f'"privacyprofiel": "{PROFIEL_GEPSEUDONIMISEERD}"' in rapport


def _verwerk_demo(doel: Path, verwerking: Persoonsverwerking) -> list[Path]:
    bronnen = [DEMO_RO, *sorted((RAW / "h16").glob("TBGI_*.XML"))]
    mappen = [doel / b.stem for b in bronnen]
    for bron, map_ in zip(bronnen, mappen, strict=True):
        run_auto_pipeline(bron, map_, persoonsverwerking=verwerking)
    return mappen


def test_ster_in_behoudmodus_toont_identifiers_alleen_in_dim_deelnemer(
    tmp_path, zonder_salt
):
    mappen = _verwerk_demo(tmp_path / "prepared", BEHOUDEN)
    ster = run_star(mappen, tmp_path / "star", scenario="test", fail_on_errors=False)

    assert {"Burgerservicenummer", "Onderwijsnummer"} <= set(
        ster["dim_deelnemer"].columns
    )
    for naam, tabel in ster.items():
        if naam != "dim_deelnemer":
            assert not set(PERSOON_COLS) & set(tabel.columns), naam
    rapport = (tmp_path / "star" / "quality.json").read_text(encoding="utf-8")
    assert f'"privacyprofiel": "{PROFIEL_IDENTIFIERS_BEHOUDEN}"' in rapport


def test_ster_in_standaardmodus_bevat_geen_identifiers(tmp_path):
    mappen = _verwerk_demo(tmp_path / "prepared", Persoonsverwerking.PSEUDONIMISEREN)
    ster = run_star(mappen, tmp_path / "star", scenario="test", fail_on_errors=False)

    for naam, tabel in ster.items():
        assert not set(PERSOON_COLS) & set(tabel.columns), naam


def test_leveringen_met_verschillende_modi_worden_niet_gemengd(tmp_path, monkeypatch):
    """Anders koppelen gezouten en ongezouten ``_persoon_id`` dezelfde persoon niet."""
    ro, tbgi = tmp_path / "ro", tmp_path / "tbgi"
    run_auto_pipeline(DEMO_RO, ro, persoonsverwerking=BEHOUDEN)
    run_auto_pipeline(next((RAW / "h16").glob("TBGI_*.XML")), tbgi)

    with pytest.raises(ValueError, match="persoonsverwerking"):
        run_star([ro, tbgi], tmp_path / "star", fail_on_errors=False)


def test_brondata_met_identifiers_zonder_profiel_wordt_nog_geweigerd(tmp_path):
    """Brondata van vóór v4.0.0 heeft geen profiel en blijft niet toegestaan."""
    oud = tmp_path / "oud"
    oud.mkdir()
    pl.DataFrame({"Burgerservicenummer": ["123456782"]}).write_parquet(
        oud / "PER.parquet"
    )
    with pytest.raises(ValueError, match="opnieuw"):
        run_star([oud], tmp_path / "star")


def test_cli_zonder_vlag_faalt_zonder_salt(zonder_salt, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv", ["mbo", "verwerk", str(DEMO_RO), str(tmp_path / "prepared")]
    )
    with pytest.raises(SystemExit) as uit:
        main()
    assert uit.value.code == 1
    assert not (tmp_path / "prepared").exists()


def test_cli_identifiers_behouden_werkt_zonder_salt_en_waarschuwt(
    zonder_salt, tmp_path, monkeypatch, capsys
):
    doel = tmp_path / "prepared"
    monkeypatch.setattr(
        "sys.argv",
        [
            "mbo",
            "verwerk",
            str(DEMO_RO),
            str(doel),
            "--persoonsverwerking",
            "identifiers_behouden",
        ],
    )
    main()

    assert "persoonsgegevens" in capsys.readouterr().err.lower()
    assert "Burgerservicenummer" in pl.read_parquet(doel / "PER.parquet").columns
