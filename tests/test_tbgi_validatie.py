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
    run_auto_pipeline(bron, doel, fail_on_errors=False)
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
    assert inventariseer_xml_elementen(bron)["onbekende_xml_elementen"] == {
        "Parameter": {"Extra": 1}
    }


def test_element_binnen_een_bladelement_wordt_gemeld_onder_dat_blad(tmp_path):
    """#359: de tekstwaarde van het blad wordt nog gelezen, maar een kind
    erbinnen (een DUO-uitbreiding) was onzichtbaar."""
    bron = _kopie(
        tmp_path,
        ("<BRIN>25LX</BRIN>", "<BRIN>25LX<Extra>xyz</Extra></BRIN>"),
    )
    assert inventariseer_xml_elementen(bron)["onbekende_xml_elementen"] == {
        "BRIN": {"Extra": 1}
    }


def test_diep_genest_element_in_een_blad_telt_ook(tmp_path):
    bron = _kopie(
        tmp_path,
        ("<BRIN>25LX</BRIN>", "<BRIN>25LX<A><B>1</B></A></BRIN>"),
    )
    assert inventariseer_xml_elementen(bron)["onbekende_xml_elementen"]["BRIN"] == {
        "A": 1,
        "B": 1,
    }


def test_inventaris_van_demo_is_leeg():
    assert inventariseer_xml_elementen(DEMO_TBGI) == {
        "onbekende_xml_elementen": {},
        "onleesbare_xml_velden": {},
    }


@pytest.mark.parametrize(
    "veld", ["InschrijvingVoorCorrectiefactor", "IndicatieBekostigbaar"]
)
def test_boolean_buiten_domein_is_error(tmp_path, veld):
    bron = _kopie(
        tmp_path,
        (f"<{veld}>true</{veld}>", f"<{veld}>not-a-bool</{veld}>"),
    )
    rapport = _rapport(bron, tmp_path)
    assert rapport["domeinafwijkingen"]["Teldatum"][veld] == {
        "aantal": 1,
        "ernst": "error",
    }
    assert any(veld in e for e in rapport["errors"])


# Een blad met een genest element en zonder eigen tekst (#421): de waarde zit in
# het kind en wordt niet gelezen. Dat is waardeverlies, geen uitbreiding.


def _diploma_opleidingcode_genest(tmp_path: Path) -> Path:
    return _kopie(
        tmp_path,
        (
            "<Opleidingcode>25297</Opleidingcode>",
            "<Opleidingcode><Deel>25297</Deel></Opleidingcode>",
        ),
    )


def test_onleesbaar_veld_staat_met_plaats_in_de_inventaris(tmp_path):
    inventaris = inventariseer_xml_elementen(_diploma_opleidingcode_genest(tmp_path))
    assert inventaris["onleesbare_xml_velden"] == {
        "Diploma": {
            "Opleidingcode": {"aantal": 1, "plaatsen": ["Diploma[1]/Opleidingcode"]}
        }
    }


def test_onleesbaar_veld_is_een_error(tmp_path):
    rapport = _rapport(_diploma_opleidingcode_genest(tmp_path), tmp_path)
    assert any(
        "Diploma.Opleidingcode" in e and "Diploma[1]/Opleidingcode" in e
        for e in rapport["errors"]
    )


def test_plaats_volgt_het_pad_vanaf_het_record(tmp_path):
    bron = _kopie(
        tmp_path,
        (
            '<Opleidingcode xsi:nil="true"/>',
            "<Opleidingcode><Deel>1</Deel></Opleidingcode>",
        ),
    )
    plaatsen = inventariseer_xml_elementen(bron)["onleesbare_xml_velden"]
    assert plaatsen == {
        "BekostigingsrelevanteBPV": {
            "Opleidingcode": {
                "aantal": 1,
                "plaatsen": [
                    "Inschrijving[1]/Teldatum[1]/BekostigingsrelevanteBPV[1]"
                    "/Opleidingcode"
                ],
            }
        }
    }


def test_blad_met_eigen_waarde_en_kind_blijft_uitbreiding(tmp_path):
    """#359 blijft: de waarde wordt gelezen, het kind is een warning."""
    bron = _kopie(
        tmp_path,
        ("<BRIN>25LX</BRIN>", "<BRIN>25LX<Extra>xyz</Extra></BRIN>"),
    )
    assert inventariseer_xml_elementen(bron)["onleesbare_xml_velden"] == {}
