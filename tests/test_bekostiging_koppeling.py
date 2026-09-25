"""Bekostiging koppelt over leveringen heen aan RO-perioden, als die er zijn (#112).

TBGI komt altijd uit een andere levering dan de RO-inschrijvingen. Eerst wordt
binnen de eigen levering gekoppeld; lukt dat niet, dan via (BRIN, _persoon_id,
Inschrijvingvolgnummer) naar de ISP-periode waarin de Teldatum valt. Zonder
passende inschrijving blijft de sleutel leeg (en meldt controleer_koppelingen dat).
Synthetische data: de demodata wordt nooit aangepast.
"""

from datetime import date

import polars as pl

from mbo_bekostiging_bestanden.quality import controleer_koppelingen
from mbo_bekostiging_bestanden.star import build_star

SLEUTEL = "_inschrijving_periode_id"
RO = "h15/RO_25LX"
TBGI = "h16/TBGI_25LX"


def _stacked(teldata: list[tuple[str, str, str, date]]) -> dict[str, pl.DataFrame]:
    """RO: één inschrijving (BSN S1, nr 002, BRIN 25LX) met twee ISP-perioden.

    ``teldata``: TBGI-rijen als (BRIN, BSN, Inschrijvingvolgnummer, Teldatum).
    """
    isp = pl.DataFrame(
        {
            "levering": [RO, RO],
            "Recordsoort": ["ISP", "ISP"],
            "Burgerservicenummer": ["S1", "S1"],
            "Inschrijvingvolgnummer": ["002", "002"],
            "DatumBegin": [date(2024, 8, 1), date(2025, 8, 1)],
            "Opleidingcode": ["25655", "25655"],
        }
    )
    per = pl.DataFrame(
        {"levering": [RO], "Recordsoort": ["PER"], "Burgerservicenummer": ["S1"]}
    )
    isg = pl.DataFrame(
        {
            "levering": [RO],
            "Burgerservicenummer": ["S1"],
            "Inschrijvingvolgnummer": ["002"],
        }
    )
    vlp = pl.DataFrame({"levering": [RO, TBGI], "BRIN": ["25LX", "25LX"]})
    inschrijving = pl.DataFrame(
        {
            "levering": [TBGI] * len(teldata),
            "BRIN": [t[0] for t in teldata],
            "Burgerservicenummer": [t[1] for t in teldata],
            "Onderwijsnummer": [None] * len(teldata),
            "Inschrijvingvolgnummer": [t[2] for t in teldata],
        },
        schema_overrides={"Onderwijsnummer": pl.Utf8},
    )
    # read_tbgi zet de persoon van de ouder-inschrijving op elke Teldatum-rij (#125).
    teldatum = inschrijving.with_columns(pl.Series("Teldatum", [t[3] for t in teldata]))
    return {
        "ISP": isp,
        "PER": per,
        "ISG": isg,
        "VLP": vlp,
        "Inschrijving": inschrijving,
        "Teldatum": teldatum,
    }


def _periode_ids(star: dict[str, pl.DataFrame]) -> dict[date, str]:
    fi = star["fact_inschrijving"]
    return dict(zip(fi["DatumBegin"], fi[SLEUTEL], strict=True))


def test_tbgi_koppelt_aan_ro_periode_waarin_teldatum_valt():
    star = build_star(_stacked([("25LX", "S1", "002", date(2025, 10, 1))]))
    ids = _periode_ids(star)
    assert star["fact_bekostiging"][SLEUTEL].to_list() == [ids[date(2025, 8, 1)]]
    assert controleer_koppelingen(star) == []


def test_zonder_passende_ro_inschrijving_blijft_sleutel_leeg():
    """Andere instelling of onbekende student: niet koppelen, wel melden."""
    star = build_star(
        _stacked(
            [
                ("99XX", "S1", "002", date(2025, 10, 1)),  # andere BRIN
                ("25LX", "S9", "002", date(2025, 10, 1)),  # onbekende student
            ]
        )
    )
    assert star["fact_bekostiging"][SLEUTEL].to_list() == [None, None]
    [melding] = controleer_koppelingen(star)
    assert melding.startswith("fact_bekostiging:")


def test_koppeling_over_leveringen_is_rijvolgorde_onafhankelijk():
    teldata = [
        ("25LX", "S1", "002", date(2024, 10, 1)),
        ("25LX", "S1", "002", date(2025, 10, 1)),
    ]
    vooruit = build_star(_stacked(teldata))["fact_bekostiging"]
    achteruit = build_star(_stacked(teldata[::-1]))["fact_bekostiging"]
    assert sorted(vooruit[SLEUTEL].to_list()) == sorted(achteruit[SLEUTEL].to_list())
    assert vooruit[SLEUTEL].n_unique() == 2


def test_inschrijving_in_meerdere_ro_leveringen_koppelt_deterministisch():
    """Dezelfde inschrijving in twee RO-leveringen: één vaste keuze, geen fan-out.

    Bij gelijke begindatum wint de levering die alfabetisch als laatste komt
    (leveringsnamen eindigen op hun datums, dus doorgaans de recentste).
    """
    stacked = _stacked([("25LX", "S1", "002", date(2025, 10, 1))])
    later = "h15/RO_25LX_later"
    for naam in ("ISP", "PER", "ISG"):
        stacked[naam] = pl.concat(
            [stacked[naam], stacked[naam].with_columns(pl.lit(later).alias("levering"))]
        )
    stacked["VLP"] = pl.concat(
        [stacked["VLP"], pl.DataFrame({"levering": [later], "BRIN": ["25LX"]})]
    )
    star = build_star(stacked)
    fi = star["fact_inschrijving"]
    verwacht = fi.filter(
        (pl.col("levering") == later) & (pl.col("DatumBegin") == date(2025, 8, 1))
    )[SLEUTEL].item()
    bek = star["fact_bekostiging"]
    assert bek[SLEUTEL].to_list() == [verwacht]
    assert bek.join(fi.select(SLEUTEL), on=SLEUTEL).height == bek.height
