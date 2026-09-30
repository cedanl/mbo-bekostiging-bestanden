"""TBGI-inhoudscontrole: waardedomeinen (#323) en onbekende XML-elementen (#324).

CSV faalt fail-closed op afwijkingen (#257); XML liet een verminkte waarde of
een extra element ongemerkt door. De demo-XML is een vaste bron en blijft
onaangeroerd: elke afwijking wordt in een tijdelijke kopie aangebracht.
"""

import json
from pathlib import Path

import pytest

from mbo_bekostiging_bestanden.ingest import inventariseer_xml_elementen
from mbo_bekostiging_bestanden.pipeline import run_auto_pipeline

DEMO_TBGI = Path("data/01-raw/demo/h16/TBGI_25LX_2027_20251124.XML")


def _kopie(tmp_path: Path, *vervangingen: tuple[str, str]) -> Path:
    """Demo-XML met per (oud, nieuw) één vervanging in een tijdelijke map."""
    tekst = DEMO_TBGI.read_text(encoding="utf-8")
    for oud, nieuw in vervangingen:
        assert oud in tekst
        tekst = tekst.replace(oud, nieuw, 1)
    pad = tmp_path / DEMO_TBGI.name
    pad.write_text(tekst, encoding="utf-8")
    return pad


def _rapport(bron: Path, tmp_path: Path) -> dict:
    doel = tmp_path / "prepared"
    run_auto_pipeline(bron, doel)
    return json.loads((doel / "quality.json").read_text(encoding="utf-8"))


def test_demo_valt_binnen_de_domeinen_en_het_schema(tmp_path):
    rapport = _rapport(DEMO_TBGI, tmp_path)
    assert rapport["domeinafwijkingen"] == {}
    assert rapport["regelinventaris"]["onbekende_xml_elementen"] == {}


def test_ongeldig_brin_is_een_error(tmp_path):
    bron = _kopie(tmp_path, ("<BRIN>25LX</BRIN>", "<BRIN>25L!</BRIN>"))
    rapport = _rapport(bron, tmp_path)
    assert rapport["domeinafwijkingen"]["Inschrijving"]["BRIN"] == {
        "aantal": 1,
        "ernst": "error",
    }
    assert any("BRIN" in e for e in rapport["errors"])


@pytest.mark.parametrize(
    ("oud", "nieuw", "tabel", "veld"),
    [
        (
            "<Leertraject>BOL</Leertraject>",
            "<Leertraject>ONZIN</Leertraject>",
            "Teldatum",
            "Leertraject",
        ),
        ("<Niveau>MBO-4</Niveau>", "<Niveau>MBO-9</Niveau>", "Diploma", "Niveau"),
        (
            "<StatusBepalingBekostigingsstatus>V</StatusBepalingBekostigingsstatus>",
            "<StatusBepalingBekostigingsstatus>X</StatusBepalingBekostigingsstatus>",
            "Teldatum",
            "StatusBepalingBekostigingsstatus",
        ),
        (
            '<Leerroutefase xsi:nil="true"/>',
            "<Leerroutefase>ZZ</Leerroutefase>",
            "Teldatum",
            "Leerroutefase",
        ),
    ],
)
def test_waarde_buiten_domein_wordt_gemeld(tmp_path, oud, nieuw, tabel, veld):
    rapport = _rapport(_kopie(tmp_path, (oud, nieuw)), tmp_path)
    assert rapport["domeinafwijkingen"][tabel][veld]["aantal"] == 1


def test_onbekend_element_wordt_gemeld_met_groep_en_tagnaam(tmp_path):
    bron = _kopie(
        tmp_path,
        (
            "<BRIN>25LX</BRIN>",
            "<BRIN>25LX</BRIN><NewOfficialField>UNEXPECTED</NewOfficialField>",
        ),
    )
    rapport = _rapport(bron, tmp_path)
    assert rapport["regelinventaris"]["onbekende_xml_elementen"] == {
        "Inschrijving": {"NewOfficialField": 1}
    }
    assert any("NewOfficialField" in w for w in rapport["warnings"])
    assert rapport["errors"] == []


def test_onbekend_element_in_een_genest_element_krijgt_zijn_eigen_groep(tmp_path):
    bron = _kopie(
        tmp_path,
        ("<Parameter>", "<Parameter><Extra>1</Extra>"),
    )
    assert inventariseer_xml_elementen(bron) == {
        "onbekende_xml_elementen": {"Parameter": {"Extra": 1}}
    }


def test_inventaris_van_demo_is_leeg():
    assert inventariseer_xml_elementen(DEMO_TBGI) == {"onbekende_xml_elementen": {}}
