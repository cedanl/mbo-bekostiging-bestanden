"""Onbekende TBG-i-XML-elementen blijven bewaard in de brondata (#420).

Een element dat het schema niet kent, werd geteld en gemeld (#324), maar
verdween uit ``02-prepared``: voegde DUO een veld toe, dan was de brondata niet
meer getrouw aan de levering. Nu staat elk onbekend element als ruwe XML in
de tabel ``OnbekendeXML``, met zijn plaats. Het analysemodel neemt het niet
over: de inhoud is ongeïnterpreteerd en kan persoonsgegevens bevatten.
"""

import json
from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.contracts import ONBEKENDE_XML
from mbo_bekostiging_bestanden.ingest import read_tbgi
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline, run_star

DEMO_TBGI = Path("data/01-raw/demo/h16/TBGI_25LX_2027_20251124.XML")
NIEUW_VELD = "<NewOfficialField>abc<Deel>1</Deel></NewOfficialField>"


def _kopie(tmp_path: Path, oud: str, nieuw: str) -> Path:
    tekst = DEMO_TBGI.read_text(encoding="utf-8")
    assert oud in tekst
    pad = tmp_path / "bron" / DEMO_TBGI.name
    pad.parent.mkdir()
    pad.write_text(tekst.replace(oud, nieuw, 1), encoding="utf-8")
    return pad


@pytest.fixture
def met_nieuw_veld(tmp_path) -> Path:
    return _kopie(tmp_path, "<BRIN>25LX</BRIN>", f"<BRIN>25LX</BRIN>{NIEUW_VELD}")


def test_onbekend_element_staat_met_plaats_en_xml_in_de_brondata(met_nieuw_veld):
    tabel = read_tbgi(met_nieuw_veld)[ONBEKENDE_XML]
    assert tabel.to_dicts() == [
        {
            "groep": "Inschrijving",
            "plaats": "Inschrijving[1]/NewOfficialField",
            "tag": "NewOfficialField",
            "xml": NIEUW_VELD,
        }
    ]


def test_kind_van_een_bladelement_wordt_ook_bewaard(tmp_path):
    """Uitbreiding onder een blad (#359): de bladwaarde zelf wordt gelezen."""
    bron = _kopie(tmp_path, "<BRIN>25LX</BRIN>", "<BRIN>25LX<Extra>xyz</Extra></BRIN>")
    frames = read_tbgi(bron)
    assert frames[ONBEKENDE_XML].to_dicts() == [
        {
            "groep": "BRIN",
            "plaats": "Inschrijving[1]/BRIN/Extra",
            "tag": "Extra",
            "xml": "<Extra>xyz</Extra>",
        }
    ]
    assert frames["Inschrijving"]["BRIN"][0] == "25LX"


def test_zonder_onbekende_elementen_geen_tabel():
    assert ONBEKENDE_XML not in read_tbgi(DEMO_TBGI)


def test_brondata_bewaart_het_en_de_ster_neemt_het_niet_over(met_nieuw_veld, tmp_path):
    prepared = tmp_path / "prepared"
    run_auto_pipeline(met_nieuw_veld, prepared)
    assert (prepared / f"{ONBEKENDE_XML}.parquet").exists()

    ster = tmp_path / "ster"
    run_star([prepared], ster)
    assert not any(
        "NewOfficialField" in p.read_bytes().decode("latin-1")
        for p in (ster / "datamodel").glob("*.parquet")
    )
    rapport = json.loads((ster / "quality.json").read_text(encoding="utf-8"))
    rij = next(
        r for r in rapport["star"]["dekking"] if r["recordtype"] == ONBEKENDE_XML
    )
    assert rij["ernst"] is None
    assert "brondata" in rij["verklaring"]
