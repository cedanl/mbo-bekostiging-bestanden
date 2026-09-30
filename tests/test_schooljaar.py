"""fact_inschrijving_schooljaar: één rij per persoon × BRIN × inschrijving × schooljaar.

Schooljaar t loopt van 1-8-t t/m 31-7-(t+1); de peildatum is 1-10-t. Een
ISP-periode telt in elk schooljaar waarvan zij de peildatum dekt (#193); een
open periode loopt tot de peildatum van de levering. Vlaggen gelden per
schooljaar (#164), het JR-diplomavenster is het schooljaar zelf (#194).

De verwachte waarden hieronder zijn met de hand afgeleid uit die definities,
niet uit pipeline-output.
"""

from datetime import date

import polars as pl
import pytest

from mbo_bekostiging_bestanden.schooljaar import bouw_inschrijving_schooljaar

_PEILGRENS = date(2026, 3, 24)


def _periode(
    begin: date,
    *,
    levering: str = "L",
    brin: str = "27DV",
    persoon: str = "P",
    nr: str = "1",
    eind: date | None = None,
    uitschrijving: date | None = None,
    niveau: str = "MBO-4",
    crebo: str = "25000",
    bekostigbaar: str = "J",
    diploma: date | None = None,
    diploma_crebo: str = "10002",
) -> dict:
    return {
        "levering": levering,
        "BRIN": brin,
        "_persoon_id": persoon,
        "Inschrijvingvolgnummer": nr,
        "DatumBegin": begin,
        "DatumEind": eind,
        "DatumUitschrijvingWerkelijk": uitschrijving,
        "Niveau": niveau,
        "Opleidingcode": crebo,
        "Leertraject": "BOL",
        "IndicatieBekostigbaar": bekostigbaar,
        "DIP_DatumResultaat": diploma,
        "DIP_Opleidingcode": diploma_crebo if diploma else None,
        "_inschrijving_periode_id": f"{levering}|{persoon}|{nr}|{begin}",
    }


def _inschrijvingen(*perioden: dict) -> pl.DataFrame:
    return pl.DataFrame(
        list(perioden),
        schema_overrides={
            "DatumEind": pl.Date,
            "DatumUitschrijvingWerkelijk": pl.Date,
            "DIP_DatumResultaat": pl.Date,
            "DIP_Opleidingcode": pl.Utf8,
        },
    )


def _leveringen(**peilgrenzen: date | None) -> pl.DataFrame:
    namen = peilgrenzen or {"L": _PEILGRENS}
    return pl.DataFrame(
        {
            "levering": list(namen),
            "DatumEindePeriode": list(namen.values()),
            "DatumAanmaak": [None] * len(namen),
        },
        schema_overrides={"DatumEindePeriode": pl.Date, "DatumAanmaak": pl.Date},
    )


def _bouw(*perioden: dict, leveringen: pl.DataFrame | None = None) -> pl.DataFrame:
    return bouw_inschrijving_schooljaar(
        _inschrijvingen(*perioden),
        leveringen if leveringen is not None else _leveringen(),
    ).sort("_persoon_id", "BRIN", "Inschrijvingvolgnummer", "Schooljaar")


def _jaren(df: pl.DataFrame) -> list[int]:
    return df["Schooljaar"].to_list()


# ---------------------------------------------------------------------------
# Welke schooljaren (#193)
# ---------------------------------------------------------------------------


def test_periode_over_meerdere_jaren_telt_elk_gedekt_schooljaar():
    df = _bouw(
        _periode(date(2022, 1, 10)),
        _periode(date(2024, 11, 21)),
    )
    # 2022-01-10 t/m 2024-11-20 dekt 1-10-2022, 1-10-2023 en 1-10-2024.
    eerste = df.filter(pl.col("DatumBegin") == date(2022, 1, 10))
    assert _jaren(eerste) == [2022, 2023, 2024]


def test_start_na_peildatum_telt_pas_volgend_schooljaar():
    df = _bouw(_periode(date(2023, 10, 2), eind=date(2024, 12, 31)))
    assert _jaren(df) == [2024]


def test_peildatum_is_1_oktober_van_het_schooljaar():
    df = _bouw(_periode(date(2023, 8, 1), eind=date(2024, 7, 31)))
    assert df.select("Schooljaar", "Peildatum").rows() == [(2023, date(2023, 10, 1))]


def test_open_periode_loopt_tot_peildatum_van_levering():
    lev = _leveringen(L=date(2025, 11, 19))
    assert _jaren(_bouw(_periode(date(2023, 8, 1)), leveringen=lev)) == [
        2023,
        2024,
        2025,
    ]


def test_peildatum_levering_voor_1_oktober_telt_dat_jaar_niet():
    lev = _leveringen(L=date(2025, 9, 30))
    assert _jaren(_bouw(_periode(date(2023, 8, 1)), leveringen=lev)) == [2023, 2024]


def test_aanmaakdatum_is_peildatum_zonder_einde_periode():
    lev = pl.DataFrame(
        {
            "levering": ["L"],
            "DatumEindePeriode": [None],
            "DatumAanmaak": [date(2024, 11, 19)],
        },
        schema_overrides={"DatumEindePeriode": pl.Date},
    )
    assert _jaren(_bouw(_periode(date(2023, 8, 1)), leveringen=lev)) == [2023, 2024]


def test_open_periode_zonder_peildatum_alleen_startschooljaar():
    lev = _leveringen(L=None)
    assert _jaren(_bouw(_periode(date(2023, 8, 1)), leveringen=lev)) == [2023]


def test_uitschrijving_voor_peildatum_is_harde_grens():
    df = _bouw(_periode(date(2023, 8, 1), uitschrijving=date(2025, 9, 16)))
    assert _jaren(df) == [2023, 2024]


def test_einddatum_na_peildatum_levering_wordt_begrensd():
    lev = _leveringen(L=date(2025, 11, 19))
    df = _bouw(_periode(date(2025, 8, 1), eind=date(2027, 7, 31)), leveringen=lev)
    assert _jaren(df) == [2025]


def test_periode_zonder_peildatum_valt_weg():
    df = _bouw(_periode(date(2024, 8, 1), eind=date(2024, 9, 30)))
    assert df.is_empty()


# ---------------------------------------------------------------------------
# Hoofdinschrijving per persoon × BRIN × schooljaar
# ---------------------------------------------------------------------------


def _hoofd(df: pl.DataFrame) -> dict[tuple[str, int], bool]:
    return {
        (r["Inschrijvingvolgnummer"], r["Schooljaar"]): r["_hoofdinschrijving"]
        for r in df.iter_rows(named=True)
    }


def test_hoogste_niveau_wordt_hoofdinschrijving():
    df = _bouw(
        _periode(date(2024, 8, 1), nr="1", niveau="MBO-3", eind=date(2025, 7, 31)),
        _periode(date(2024, 8, 1), nr="2", niveau="MBO-4", eind=date(2025, 7, 31)),
    )
    assert _hoofd(df) == {("1", 2024): False, ("2", 2024): True}


def test_gelijk_niveau_laagste_crebo_wint():
    df = _bouw(
        _periode(date(2024, 8, 1), nr="1", crebo="25999", eind=date(2025, 7, 31)),
        _periode(date(2024, 8, 1), nr="2", crebo="25001", eind=date(2025, 7, 31)),
    )
    assert _hoofd(df) == {("1", 2024): False, ("2", 2024): True}


def test_een_hoofdinschrijving_over_leveringen_heen():
    """Na canonicalisatie kunnen inschrijvingen uit verschillende leveringen komen."""
    lev = _leveringen(L_a=_PEILGRENS, L_b=_PEILGRENS)
    df = _bouw(
        _periode(date(2024, 8, 1), levering="L_a", nr="1", eind=date(2025, 7, 31)),
        _periode(date(2024, 8, 1), levering="L_b", nr="2", eind=date(2025, 7, 31)),
        leveringen=lev,
    )
    assert df["_hoofdinschrijving"].sum() == 1


def test_andere_instelling_eigen_hoofdinschrijving():
    df = _bouw(
        _periode(date(2024, 8, 1), brin="21CY", eind=date(2025, 7, 31)),
        _periode(date(2024, 8, 1), brin="27DV", eind=date(2025, 7, 31)),
    )
    assert df["_hoofdinschrijving"].to_list() == [True, True]


def test_hoofdinschrijving_per_schooljaar_opnieuw_gekozen():
    df = _bouw(
        _periode(date(2023, 8, 1), nr="1", niveau="MBO-4", eind=date(2024, 7, 31)),
        _periode(date(2023, 8, 1), nr="2", niveau="MBO-3", eind=date(2025, 7, 31)),
    )
    assert _hoofd(df) == {("1", 2023): True, ("2", 2023): False, ("2", 2024): True}


# ---------------------------------------------------------------------------
# Telling, bekostiging, JR (#194)
# ---------------------------------------------------------------------------


def test_telling_is_hoofdinschrijving():
    df = _bouw(
        _periode(date(2024, 8, 1), nr="1", niveau="MBO-3", eind=date(2025, 7, 31)),
        _periode(date(2024, 8, 1), nr="2", niveau="MBO-4", eind=date(2025, 7, 31)),
    )
    assert df["_telling"].to_list() == df["_hoofdinschrijving"].to_list()


def test_bekostigd_volgt_indicatie_van_de_periode():
    df = _bouw(_periode(date(2024, 8, 1), bekostigbaar="N", eind=date(2025, 7, 31)))
    assert df["_bekostigd"].to_list() == [False]


@pytest.mark.parametrize(
    ("diploma", "verwacht"),
    [
        (date(2025, 7, 7), True),  # binnen schooljaar 2024
        (date(2024, 8, 1), True),  # eerste dag schooljaar 2024
        (date(2025, 7, 31), True),  # laatste dag schooljaar 2024
        (date(2024, 7, 31), False),  # schooljaar 2023
        (date(2025, 8, 1), False),  # schooljaar 2025
    ],
)
def test_jr_diplomavenster_is_het_schooljaar_zelf(diploma, verwacht):
    df = _bouw(
        _periode(date(2024, 5, 7), uitschrijving=date(2025, 7, 7), diploma=diploma)
    )
    rij = df.filter(pl.col("Schooljaar") == 2024)
    assert rij.select("_gediplomeerd_in_jaar", "_jr_noemer", "_jr_teller").row(0) == (
        verwacht,
        True,
        verwacht,
    )


def test_jr_teller_alleen_voor_hoofdinschrijving():
    df = _bouw(
        _periode(date(2024, 8, 1), nr="1", niveau="MBO-3", diploma=date(2025, 6, 1)),
        _periode(date(2024, 8, 1), nr="2", niveau="MBO-4", eind=date(2025, 7, 31)),
    )
    teller = df.filter(pl.col("Schooljaar") == 2024)["_jr_teller"].to_list()
    assert teller == [False, False]


# ---------------------------------------------------------------------------
# DR: uitstroom alleen als het volgende schooljaar waarneembaar is
# ---------------------------------------------------------------------------


def _dr(df: pl.DataFrame) -> dict[int, tuple[bool, bool]]:
    return {
        r["Schooljaar"]: (r["_dr_noemer"], r["_dr_teller"])
        for r in df.iter_rows(named=True)
    }


def test_uitstromer_zonder_inschrijving_volgend_schooljaar():
    df = _bouw(
        _periode(
            date(2023, 8, 1), uitschrijving=date(2024, 7, 31), diploma=date(2024, 7, 1)
        )
    )
    assert _dr(df) == {2023: (True, True)}


def test_doorlopende_inschrijving_is_geen_uitstromer():
    df = _bouw(_periode(date(2023, 8, 1), uitschrijving=date(2025, 7, 31)))
    assert _dr(df) == {2023: (False, False), 2024: (True, False)}


def test_laatste_waarneembare_schooljaar_is_geen_uitstroom():
    """Of iemand in t+1 nog staat ingeschreven, kan de levering niet weten."""
    lev = _leveringen(L=date(2025, 11, 19))
    df = _bouw(_periode(date(2024, 8, 1)), leveringen=lev)
    assert _dr(df) == {2024: (False, False), 2025: (False, False)}


def test_dr_alleen_vanaf_niveau_2():
    df = _bouw(
        _periode(date(2023, 8, 1), niveau="MBO-1", uitschrijving=date(2024, 7, 31))
    )
    assert _dr(df) == {2023: (False, False)}


# Uitstroom is instelling-onafhankelijk (#118): wie in t+1 bij een andere
# instelling in de dataset staat, is geen uitstromer. Waarneembaarheid blijft
# per eigen BRIN: dat t+1 bij een andere instelling gezien is, maakt een
# onwaarneembaar t+1 niet waarneembaar (anders telt alleen blijven mee).
_TWEE_INSTELLINGEN = _leveringen(A=_PEILGRENS, B=_PEILGRENS)


def _bij(brin: str, begin: date, **kwargs) -> dict:
    return _periode(begin, levering=brin, brin=brin, **kwargs)


def _dr_bij(df: pl.DataFrame, brin: str) -> dict[int, tuple[bool, bool]]:
    return _dr(df.filter(pl.col("BRIN") == brin))


def test_overstap_naar_andere_instelling_is_geen_uitstroom():
    df = _bouw(
        _bij("A", date(2023, 8, 1), uitschrijving=date(2024, 7, 31)),
        _bij("B", date(2024, 8, 1), uitschrijving=date(2025, 7, 31)),
        leveringen=_TWEE_INSTELLINGEN,
    )
    assert _dr_bij(df, "A") == {2023: (False, False)}


def test_andere_persoon_bij_andere_instelling_telt_niet():
    df = _bouw(
        _bij("A", date(2023, 8, 1), uitschrijving=date(2024, 7, 31)),
        _bij("B", date(2024, 8, 1), persoon="Q"),
        leveringen=_TWEE_INSTELLINGEN,
    )
    assert _dr_bij(df, "A") == {2023: (True, False)}


def test_overstap_maakt_onwaarneembaar_jaar_niet_waarneembaar():
    lev = _leveringen(A=date(2024, 3, 1), B=_PEILGRENS)
    df = _bouw(
        _bij("A", date(2023, 8, 1)),
        _bij("B", date(2024, 8, 1)),
        leveringen=lev,
    )
    assert _dr_bij(df, "A") == {2023: (False, False)}


# ---------------------------------------------------------------------------
# DR-teller (#119, #237): diploma niveau >= 2 bij de instelling die de student
# verlaat, van het begin van schooljaar t-5 tot de peildatum 1-10-(t+1)
# ---------------------------------------------------------------------------
# Uitstroom in schooljaar 2023: actief op 1-10-2023, niet op 1-10-2024. Het
# venster loopt van 1-8-2018 (begin van schooljaar 2018 = 2023 - 5) tot
# 1-10-2024: een diploma in augustus of september 2024 is er een waarmee de
# student vertrok. Crebo 10002 is niveau 4, 10022 niveau 1 (metadata/crebo.csv).
_NIVEAU_4, _NIVEAU_1 = "10002", "10022"


def _uitstromer_2023(*eerdere: dict, **kwargs) -> pl.DataFrame:
    """Uitstromer in 2023, met eventueel eerdere inschrijvingen (met diploma)."""
    return _bouw(
        _periode(date(2023, 8, 1), uitschrijving=date(2024, 7, 31), **kwargs),
        *eerdere,
    ).filter(pl.col("Schooljaar") == 2023, pl.col("Inschrijvingvolgnummer") == "1")


def _eerder(diploma: date, **kwargs) -> dict:
    begin = date(diploma.year - 1, 8, 1)
    return _periode(begin, nr="0", uitschrijving=diploma, diploma=diploma, **kwargs)


@pytest.mark.parametrize(
    ("diploma", "verwacht"),
    [
        (date(2024, 7, 31), True),  # laatste dag van het uitstroomjaar
        (date(2024, 9, 30), True),  # daags voor de peildatum van t+1
        (date(2018, 8, 1), True),  # eerste dag van het zesde schooljaar ervoor
        (date(2018, 7, 31), False),  # zeven schooljaren voor uitstroom
    ],
)
def test_dr_diploma_in_het_zesjaarsvenster(diploma, verwacht):
    if diploma >= date(2023, 8, 1):
        df = _uitstromer_2023(diploma=diploma)
    else:
        df = _uitstromer_2023(_eerder(diploma))
    assert df.select("_dr_noemer", "_dr_teller").row(0) == (True, verwacht)


def test_dr_diploma_op_of_na_de_peildatum_van_t_plus_1_telt_niet():
    """Eén dag na het venster: het diploma hoort niet bij deze uitstroom."""
    df = _uitstromer_2023(diploma=date(2024, 10, 1))
    assert df.select("_dr_noemer", "_dr_teller").row(0) == (True, False)


def test_dr_diploma_op_niveau_1_telt_niet():
    df = _uitstromer_2023(diploma=date(2024, 6, 1), diploma_crebo=_NIVEAU_1)
    assert df.select("_dr_noemer", "_dr_teller").row(0) == (True, False)


def test_dr_eerder_diploma_niveau_2_plus_telt_bij_uitstroom_zonder_diploma():
    """Het diploma hoeft niet bij de uitstroominschrijving te horen."""
    df = _uitstromer_2023(_eerder(date(2021, 6, 30)))
    assert df.select("_dr_noemer", "_dr_teller").row(0) == (True, True)


def test_dr_diploma_van_onbekend_niveau_telt_niet():
    df = _uitstromer_2023(diploma=date(2024, 6, 1), diploma_crebo="00000")
    assert df.select("_dr_noemer", "_dr_teller").row(0) == (True, False)


def test_dr_meerdere_diplomas_een_uitkomst():
    df = _uitstromer_2023(
        _eerder(date(2021, 6, 30)),
        _eerder(date(2016, 6, 30)) | {"Inschrijvingvolgnummer": "9"},
        diploma=date(2024, 6, 1),
    )
    assert df.height == 1
    assert df.select("_dr_noemer", "_dr_teller").row(0) == (True, True)


def test_dr_diploma_bij_andere_instelling_telt_niet():
    """DR is het resultaat van de instelling die de student verlaat."""
    df = _bouw(
        _bij("A", date(2023, 8, 1), uitschrijving=date(2024, 7, 31)),
        _bij(
            "B",
            date(2020, 8, 1),
            uitschrijving=date(2021, 6, 30),
            diploma=date(2021, 6, 30),
            nr="0",
        ),
        leveringen=_TWEE_INSTELLINGEN,
    ).filter(pl.col("BRIN") == "A")
    assert _dr(df) == {2023: (True, False)}


def test_dr_diploma_zonder_uitstroom_telt_niet():
    df = _bouw(
        _periode(
            date(2023, 8, 1), uitschrijving=date(2025, 7, 31), diploma=date(2024, 6, 1)
        )
    ).filter(pl.col("Schooljaar") == 2023)
    assert _dr(df) == {2023: (False, False)}


def test_quality_noemt_de_instellingen_waarbinnen_uitstroom_bepaald_is():
    """Buiten de dataset ziet niemand de overstap: dat staat in quality.json."""
    from mbo_bekostiging_bestanden.quality import (
        compile_quality_report,
        kwaliteitsmeldingen,
    )

    df = _bouw(
        _bij("A", date(2023, 8, 1)),
        _bij("B", date(2023, 8, 1), persoon="Q"),
        leveringen=_TWEE_INSTELLINGEN,
    )
    rapport = compile_quality_report({"fact_inschrijving_schooljaar": df})

    assert rapport["star"]["dr_scope"] == {"brins": ["A", "B"], "mbo_breed": False}
    info = [m.tekst for m in kwaliteitsmeldingen(rapport) if m.ernst == "info"]
    assert any("2 instellingen" in t for t in info)


# ---------------------------------------------------------------------------
# Star-output op de demo
# ---------------------------------------------------------------------------


def test_demo_grain_is_uniek(demo_star):
    feit = demo_star["fact_inschrijving_schooljaar"]
    sleutel = ["BRIN", "_persoon_id", "Inschrijvingvolgnummer", "Schooljaar"]
    assert feit.height > 0
    assert not feit.select(sleutel).is_duplicated().any()


def test_demo_precies_een_hoofdinschrijving_per_persoon_instelling_schooljaar(
    demo_star,
):
    per_groep = (
        demo_star["fact_inschrijving_schooljaar"]
        .group_by("BRIN", "_persoon_id", "Schooljaar")
        .agg(pl.col("_hoofdinschrijving").sum().alias("n"))
    )
    assert per_groep["n"].unique().to_list() == [1]


def test_demo_heeft_positieve_jr_teller(demo_star):
    """De demo bevat gediplomeerden die in hun schooljaar tellen (#194)."""
    assert demo_star["fact_inschrijving_schooljaar"]["_jr_teller"].sum() > 0


def test_demo_periode_fk_bestaat_in_fact_inschrijving(demo_star):
    jaren = demo_star["fact_inschrijving_schooljaar"]
    perioden = demo_star["fact_inschrijving"]
    wees = jaren.join(perioden, on="_inschrijving_periode_id", how="anti")
    assert wees.is_empty()


def test_tbgi_only_inschrijving_is_de_periode(tbgi_star):
    """Zonder ISP verwijst elke schooljaarrij naar de TBGI-inschrijving."""
    jaren = tbgi_star["fact_inschrijving_schooljaar"]
    assert jaren.height > 0
    assert not jaren.join(
        tbgi_star["fact_inschrijving"], on="_inschrijving_periode_id", how="anti"
    ).height


# ---------------------------------------------------------------------------
# TBGI: de teldatum is de waarneming (#197)
# ---------------------------------------------------------------------------


def _tbgi_inschrijving(nr: str = "1", inschrijving: date = date(2024, 2, 1)) -> dict:
    """TBGI levert een inschrijving (geen ISP-periode) met ``DatumInschrijving``."""
    rij = _periode(inschrijving, levering="T", nr=nr)
    rij["DatumInschrijving"] = rij.pop("DatumBegin")
    rij["DatumUitschrijvingGepland"] = date(2027, 1, 31)
    rij["Bron"] = "TBGI"
    return rij


def _teldata(*rijen: tuple[str, date]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "levering": ["T"] * len(rijen),
            "BRIN": ["27DV"] * len(rijen),
            "_persoon_id": ["P"] * len(rijen),
            "Inschrijvingvolgnummer": [nr for nr, _ in rijen],
            "Teldatum": [d for _, d in rijen],
            "Opleidingcode": ["25748"] * len(rijen),
            "Niveau": ["MBO-1"] * len(rijen),
            "Leertraject": ["BBL"] * len(rijen),
            "IndicatieBekostigbaar": ["J"] * len(rijen),
        }
    )


def _bouw_tbgi(inschrijvingen: pl.DataFrame, teldata: pl.DataFrame) -> pl.DataFrame:
    return bouw_inschrijving_schooljaar(
        inschrijvingen, _leveringen(T=None), teldata=teldata
    )


def test_tbgi_schooljaar_volgt_teldatum_niet_datum_inschrijving():
    """Inschrijving 1-2-2024, teldatum 1-10-2025 → alleen schooljaar 2025."""
    df = _bouw_tbgi(
        _inschrijvingen(_tbgi_inschrijving()), _teldata(("1", date(2025, 10, 1)))
    )
    assert df["Schooljaar"].to_list() == [2025]
    assert df["Peildatum"].to_list() == [date(2025, 10, 1)]


def test_tbgi_attributen_komen_van_de_teldatum():
    """Opleiding, niveau en bekostigbaarheid zijn per teldatum waargenomen."""
    inschrijving = _tbgi_inschrijving()
    inschrijving.update(Niveau=None, Opleidingcode=None, Leertraject=None)
    df = _bouw_tbgi(_inschrijvingen(inschrijving), _teldata(("1", date(2025, 10, 1))))
    rij = df.row(0, named=True)
    assert (rij["Opleidingcode"], rij["Leertraject"]) == ("25748", "BBL")
    assert rij["_hoofdinschrijving"] and rij["_bekostigd"]


def test_tbgi_teldatum_1_februari_is_geen_peildatum():
    df = _bouw_tbgi(
        _inschrijvingen(_tbgi_inschrijving()),
        _teldata(("1", date(2025, 10, 1)), ("1", date(2026, 2, 1))),
    )
    assert df["Schooljaar"].to_list() == [2025]


def test_tbgi_inschrijving_zonder_teldatum_telt_niet():
    """PvE §16: geen <Teldatum> = niet in aanmerking op 1-10 of 1-2."""
    df = _bouw_tbgi(
        _inschrijvingen(_tbgi_inschrijving("1"), _tbgi_inschrijving("2")),
        _teldata(("1", date(2025, 10, 1))),
    )
    assert df["Inschrijvingvolgnummer"].to_list() == ["1"]


def test_tbgi_only_demo_schooljaar_is_teldatum(tbgi_star):
    """Demo 25LX: DatumInschrijving 2024-02-01, Teldatum 2025-10-01."""
    jaren = tbgi_star["fact_inschrijving_schooljaar"]
    assert jaren["Schooljaar"].to_list() == [2025]
    assert jaren["Peildatum"].to_list() == [date(2025, 10, 1)]


def test_twee_perioden_met_gelijke_begindatum_worden_gemeld():
    """Auditprobe #200: zelfde inschrijving en DatumBegin, andere periode-ID.

    Dat is een bronfout (dubbele ISP-sleutel); de schooljaar-fact ontdubbelt
    niet stil, maar quality.json meldt de geschonden grain als error.
    """
    from mbo_bekostiging_bestanden.quality import controleer_sleuteluniciteit

    a = _periode(date(2024, 8, 1), crebo="25000")
    b = _periode(date(2024, 8, 1), crebo="25001")
    b["_inschrijving_periode_id"] += "-b"
    df = _bouw(a, b)
    meldingen = controleer_sleuteluniciteit({"fact_inschrijving_schooljaar": df})
    assert any("fact_inschrijving_schooljaar" in m for m in meldingen)


# ---------------------------------------------------------------------------
# Observatievenster per levering (#211)
# ---------------------------------------------------------------------------


def test_observatievenster_noemt_grens_en_laatste_peildatum():
    from mbo_bekostiging_bestanden.schooljaar import observatievenster

    leveringen = pl.DataFrame(
        {
            "levering": ["RO", "GR", "TB"],
            "DatumEindePeriode": [date(2026, 3, 24), None, None],
            "DatumAanmaak": [date(2026, 3, 25), date(2025, 9, 15), None],
        }
    )
    teldata = pl.DataFrame({"levering": ["TB"], "Teldatum": [date(2025, 10, 1)]})
    venster = {
        r["levering"]: r
        for r in observatievenster(leveringen, teldata).iter_rows(named=True)
    }
    assert venster["RO"]["Peilgrens_bron"] == "DatumEindePeriode"
    assert venster["RO"]["Laatste_peildatum"] == date(2025, 10, 1)
    assert venster["GR"]["Peilgrens_bron"] == "DatumAanmaak"
    assert venster["GR"]["Laatste_peildatum"] == date(2024, 10, 1)
    assert venster["TB"]["Peilgrens_bron"] == "Teldatum"
    assert venster["TB"]["Laatste_peildatum"] == date(2025, 10, 1)


def test_vroege_grondslag_levering_heeft_geen_schooljaarrijen_en_wordt_gemeld():
    """Aangemaakt op 15-9-2025: 1-10-2025 is niet waarneembaar, 1-10-2024 valt
    vóór de periode. Inhoudelijk juist, maar niet stil."""
    from mbo_bekostiging_bestanden.quality import compile_quality_report

    periode = _periode(date(2025, 8, 1), levering="GR")
    leveringen = _leveringen(GR=None).with_columns(
        pl.lit(date(2025, 9, 15)).alias("DatumAanmaak")
    )
    jaren = _bouw(periode, leveringen=leveringen)
    assert jaren.is_empty()
    star = {
        "fact_inschrijving": _inschrijvingen(periode),
        "fact_inschrijving_schooljaar": jaren,
    }
    rapport = compile_quality_report(star)
    assert rapport["star"]["leveringen_zonder_schooljaar"] == [
        {"levering": "GR", "inschrijvingen": 1}
    ]
    assert rapport["summary"]["total_warnings"] == 1


def test_demo_meta_leveringen_heeft_observatievenster(demo_star):
    meta = demo_star["meta_leveringen"]
    assert {"Peilgrens", "Peilgrens_bron", "Laatste_peildatum"} <= set(meta.columns)
    assert meta["Peilgrens"].null_count() == 0


def test_demo_heeft_geen_levering_zonder_schooljaar(demo_star):
    from mbo_bekostiging_bestanden.quality import compile_quality_report

    rapport = compile_quality_report(demo_star)
    assert rapport["star"]["leveringen_zonder_schooljaar"] == []


# ---------------------------------------------------------------------------
# Entree (niveau 1): wat gebeurt er in t+1 (#306)
# ---------------------------------------------------------------------------
# Populatie: de entree-hoofdinschrijving in t die Entree verlaat. Doorstroom =
# in t+1 niveau >= 2, bij welke instelling in de dataset ook (#118); uitstroom =
# in t+1 nergens meer ingeschreven. Wie in Entree blijft of van wie t+1 niet
# waarneembaar is, valt erbuiten — net als bij DR.


def _entree(df: pl.DataFrame) -> dict[int, tuple[bool, bool, bool]]:
    return {
        r["Schooljaar"]: (
            r["_entree_noemer"],
            r["_entree_doorstroom"],
            r["_entree_uitstroom"],
        )
        for r in df.filter(pl.col("Niveau") == "MBO-1").iter_rows(named=True)
    }


def test_entree_met_twee_perioden_telt_een_keer():
    """Periode-grain telde deze student twee keer (audit F-07)."""
    df = _bouw(
        _periode(date(2023, 8, 1), niveau="MBO-1", eind=date(2023, 12, 31)),
        _periode(date(2024, 1, 1), niveau="MBO-1", uitschrijving=date(2024, 7, 31)),
        _periode(date(2024, 8, 1), nr="2", niveau="MBO-2"),
    )
    assert _entree(df) == {2023: (True, True, False)}


def test_entree_zonder_inschrijving_volgend_jaar_is_uitstroom():
    df = _bouw(
        _periode(date(2023, 8, 1), niveau="MBO-1", uitschrijving=date(2024, 7, 31))
    )
    assert _entree(df) == {2023: (True, False, True)}


def test_entree_die_in_entree_blijft_valt_buiten_de_populatie():
    df = _bouw(
        _periode(date(2023, 8, 1), niveau="MBO-1", uitschrijving=date(2025, 7, 31))
    )
    assert _entree(df)[2023] == (False, False, False)


def test_entree_zonder_waarneembaar_volgend_jaar_valt_buiten_de_populatie():
    lev = _leveringen(L=date(2025, 11, 19))
    df = _bouw(_periode(date(2025, 8, 1), niveau="MBO-1"), leveringen=lev)
    assert _entree(df) == {2025: (False, False, False)}


def test_entree_doorstroom_naar_andere_instelling():
    """Net als DR instelling-onafhankelijk (#118)."""
    df = _bouw(
        _bij("A", date(2023, 8, 1), niveau="MBO-1", uitschrijving=date(2024, 7, 31)),
        _bij("B", date(2024, 8, 1), niveau="MBO-2"),
        leveringen=_TWEE_INSTELLINGEN,
    )
    assert _entree(df) == {2023: (True, True, False)}


def test_niveau_2_is_geen_entree():
    df = _bouw(_periode(date(2023, 8, 1), uitschrijving=date(2024, 7, 31)))
    assert not df["_entree_noemer"].any()
