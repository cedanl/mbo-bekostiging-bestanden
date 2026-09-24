"""TBGI-only output draagt dezelfde periodesleutel als de ISP-route (#109).

Zonder ISP-perioden is een TBGI-inschrijving één periode vanaf
``DatumInschrijving``; de detail-feiten koppelen daaraan met dezelfde regel.
"""

import pytest

from mbo_bekostiging_bestanden.quality import controleer_koppelingen

SLEUTEL = "_inschrijving_periode_id"
SHA256_HEX = r"^[0-9a-f]{64}$"


def test_tbgi_route_heeft_feiten_met_inhoud(tbgi_star):
    """Borgt dat de fixture echt de TBGI-only route raakt."""
    assert not tbgi_star["fact_inschrijving"].is_empty()
    assert not tbgi_star["fact_bekostiging"].is_empty()
    assert "DatumBegin" not in tbgi_star["fact_inschrijving"].columns


def test_fact_inschrijving_heeft_unieke_sha256_sleutel(tbgi_star):
    ids = tbgi_star["fact_inschrijving"][SLEUTEL]
    assert ids.null_count() == 0
    assert ids.is_unique().all()
    assert ids.str.contains(SHA256_HEX).all()


@pytest.mark.parametrize("naam", ["fact_bekostiging", "fact_bekostiging_diploma"])
def test_detail_feiten_hebben_periodesleutel(tbgi_star, naam):
    assert SLEUTEL in tbgi_star[naam].columns


def test_bekostiging_koppelt_aan_tbgi_inschrijving(tbgi_star):
    fi = tbgi_star["fact_inschrijving"].select(SLEUTEL)
    bek = tbgi_star["fact_bekostiging"]
    assert bek.join(fi, on=SLEUTEL, how="inner").height == bek.height


def test_koppelcontrole_meldt_alleen_echte_wezen(tbgi_star):
    """Demo: het TBGI-diploma hoort bij een andere persoon dan de inschrijving."""
    gemeld = {m.split(":")[0] for m in controleer_koppelingen(tbgi_star)}
    assert gemeld == {"fact_bekostiging_diploma"}
