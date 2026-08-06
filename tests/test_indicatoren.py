"""Tests voor indicatoren.py (normen, oordeel, populatie, entree)."""

import polars as pl

from mbo_bekostiging_bestanden.indicatoren import (
    _MIN_NOEMER,
    _bepaal_oordeel,
    _laad_normen,
    bereken_oordeel,
    entree_indicatoren,
    entree_totaal,
    indicator_voldoet,
    norm_voor,
    normen_per_niveau,
    populatie_regele_filter,
)

# ---------------------------------------------------------------------------
# Normen
# ---------------------------------------------------------------------------


def test_normen_tabel_1_voldoende_jr():
    """Normen voor voldoende: JR 67/68/68 op niveau 2/3/4."""
    assert norm_voor("jr", 2, "voldoende") == 67
    assert norm_voor("jr", 3, "voldoende") == 68
    assert norm_voor("jr", 4, "voldoende") == 68


def test_normen_tabel_1_voldoende_dr_sr():
    assert norm_voor("dr", 2, "voldoende") == 61
    assert norm_voor("dr", 3, "voldoende") == 70
    assert norm_voor("dr", 4, "voldoende") == 70
    assert norm_voor("sr", 2, "voldoende") == 79
    assert norm_voor("sr", 3, "voldoende") == 82
    assert norm_voor("sr", 4, "voldoende") == 82


def test_normen_tabel_2_hoog_jr_dr():
    """Normen voor hoog: JR 82/85/85, DR 79/89/89. SR heeft geen hoge norm."""
    assert norm_voor("jr", 2, "hoog") == 82
    assert norm_voor("jr", 3, "hoog") == 85
    assert norm_voor("jr", 4, "hoog") == 85
    assert norm_voor("dr", 2, "hoog") == 79
    assert norm_voor("dr", 3, "hoog") == 89
    assert norm_voor("dr", 4, "hoog") == 89
    assert norm_voor("sr", 2, "hoog") is None


def test_normen_per_niveau_structuur():
    jr = normen_per_niveau("jr")
    assert set(jr.keys()) == {2, 3, 4}
    assert jr[3] == {"voldoende": 68, "hoog": 85}


def test_norm_voor_onbekend_geeft_none():
    assert norm_voor("jr", 1, "voldoende") is None
    assert norm_voor("zz", 2, "voldoende") is None
    assert norm_voor("jr", 2, "onzin") is None


def test_laad_normen_bevat_drie_indicatoren():
    normen = _laad_normen()
    assert set(normen.keys()) == {
        "jaarresultaat",
        "diplomaresultaat",
        "startersresultaat",
    }


# ---------------------------------------------------------------------------
# indicator_voldoet
# ---------------------------------------------------------------------------


def test_indicator_voldoet_true():
    assert indicator_voldoet(70.0, 15, 68) is True


def test_indicator_voldoet_false():
    assert indicator_voldoet(50.0, 15, 68) is False


def test_indicator_voldoet_grens():
    assert indicator_voldoet(68.0, 15, 68) is True


def test_indicator_voldoet_geen_noemer():
    assert indicator_voldoet(70.0, None, 68) is None


def test_indicator_voldoet_te_kleine_noemer():
    assert indicator_voldoet(90.0, _MIN_NOEMER - 1, 68) is None


def test_indicator_voldoet_geen_norm():
    assert indicator_voldoet(70.0, 15, None) is None


def test_indicator_voldoet_uiterste_waarde_excluded():
    assert indicator_voldoet(100.0, 15, 68, mag_niet_uiterste=True) is None
    assert indicator_voldoet(0.0, 15, 68, mag_niet_uiterste=True) is None
    assert indicator_voldoet(100.0, 15, 68, mag_niet_uiterste=False) is True


# ---------------------------------------------------------------------------
# bereken_oordeel – tabel 3
# ---------------------------------------------------------------------------

_JR_VOLD = {"waarde": 75.0, "noemer": 15}
_DR_VOLD = {"waarde": 80.0, "noemer": 15}
_SR_VOLD = {"waarde": 85.0, "noemer": 15}
_JR_LAAG = {"waarde": 40.0, "noemer": 15}
_DR_LAAG = {"waarde": 40.0, "noemer": 15}
_SR_LAAG = {"waarde": 40.0, "noemer": 15}
_JR_HOOG = {"waarde": 90.0, "noemer": 15}
_DR_HOOG = {"waarde": 95.0, "noemer": 15}


def test_oordeel_hoog():
    """Alle drie voldoende én JR ≥ hoge norm → hoog."""
    oordeel, _, _ = bereken_oordeel(_JR_HOOG, _DR_HOOG, _SR_VOLD, niveau=3)
    assert oordeel == "hoog"


def test_oordeel_hoog_via_dr_alleen():
    """JR voldoet niet aan hoge norm, DR wel → nog steeds hoog."""
    oordeel, _, _ = bereken_oordeel(_JR_VOLD, _DR_HOOG, _SR_VOLD, niveau=3)
    assert oordeel == "hoog"


def test_oordeel_voldoende_alle_drie_maar_geen_hoog():
    """Alle drie voldoende maar JR en DR beide onder hoge norm → voldoende."""
    oordeel, _, _ = bereken_oordeel(_JR_VOLD, _DR_VOLD, _SR_VOLD, niveau=3)
    assert oordeel == "voldoende"


def test_oordeel_voldoende_twee_van_drie():
    oordeel, _, _ = bereken_oordeel(_JR_VOLD, _DR_LAAG, _SR_VOLD, niveau=3)
    assert oordeel == "voldoende"


def test_oordeel_onvoldoende_een_van_drie():
    oordeel, _, _ = bereken_oordeel(_JR_VOLD, _DR_LAAG, _SR_LAAG, niveau=3)
    assert oordeel == "onvoldoende"


def test_oordeel_onvoldoende_geen_van_drie():
    oordeel, _, _ = bereken_oordeel(_JR_LAAG, _DR_LAAG, _SR_LAAG, niveau=3)
    assert oordeel == "onvoldoende"


def test_oordeel_norm_is_niveau_afhankelijk():
    """Niveau 2: JR 67 voldoet aan de norm; op niveau 4 niet."""
    jr = {"waarde": 67.0, "noemer": 15}
    dr = {"waarde": 70.0, "noemer": 15}
    sr = {"waarde": 80.0, "noemer": 15}
    oordeel_2, _, _ = bereken_oordeel(jr, dr, sr, niveau=2)
    oordeel_4, _, _ = bereken_oordeel(jr, dr, sr, niveau=4)
    assert oordeel_2 == "voldoende"
    assert oordeel_4 == "onvoldoende"


# ---------------------------------------------------------------------------
# bereken_oordeel – ontbrekende indicatoren (§3.5)
# ---------------------------------------------------------------------------


def test_oordeel_een_indicator_ontbreekt_zelfde_richting():
    """SR ontbreekt, JR en DR beide voldoende → voldoende."""
    oordeel, statuses, _ = bereken_oordeel(_JR_VOLD, _DR_VOLD, None, niveau=3)
    assert oordeel == "voldoende"
    assert statuses[2] is None


def test_oordeel_een_indicator_ontbreekt_verschillende_richting():
    """SR ontbreekt, JR voldoende en DR onvoldoende → niet te bepalen."""
    oordeel, _, _ = bereken_oordeel(_JR_VOLD, _DR_LAAG, None, niveau=3)
    assert oordeel == "niet_te_bepalen"


def test_oordeel_een_indicator_ontbreekt_beide_onvoldoende():
    oordeel, _, _ = bereken_oordeel(_JR_LAAG, _DR_LAAG, None, niveau=3)
    assert oordeel == "onvoldoende"


def test_oordeel_twee_indicatoren_ontbreken():
    """SR en DR ontbreken → geen berekend oordeel mogelijk."""
    oordeel, _, _ = bereken_oordeel(_JR_VOLD, None, None, niveau=3)
    assert oordeel == "niet_te_bepalen"


def test_oordeel_alle_indicatoren_ontbreken():
    oordeel, statuses, _ = bereken_oordeel(None, None, None, niveau=3)
    assert oordeel == "niet_te_bepalen"
    assert statuses == [None, None, None]


def test_oordeel_te_kleine_noemer_niet_te_bepalen():
    """Kleine noemer per indicator → status None → geen oordeel.

    DR heeft een te kleine noemer (onbeoordeelbaar); JR en SR wijzen
    dezelfde richting uit → voldoende.  Wijzen ze tegenovergesteld, dan
    is er geen oordeel.
    """
    klein = {"waarde": 80.0, "noemer": _MIN_NOEMER - 1}
    oordeel, statuses, _ = bereken_oordeel(_JR_VOLD, klein, _SR_VOLD, niveau=3)
    assert statuses[1] is None
    assert oordeel == "voldoende"

    oordeel_tegen, _, _ = bereken_oordeel(_JR_VOLD, klein, _SR_LAAG, niveau=3)
    assert oordeel_tegen == "niet_te_bepalen"


def test_oordeel_alle_indicatoren_te_kleine_noemer():
    """Alle noemers te klein → volledig onbeoordeelbaar."""
    klein = {"waarde": 80.0, "noemer": _MIN_NOEMER - 1}
    oordeel, statuses, _ = bereken_oordeel(klein, klein, klein, niveau=3)
    assert oordeel == "niet_te_bepalen"
    assert statuses == [None, None, None]


# ---------------------------------------------------------------------------
# _bepaal_oordeel – directe status-input
# ---------------------------------------------------------------------------


def test_bepaal_oordeel_geen_ontbrekend_twee_voldoen():
    assert _bepaal_oordeel([True, False, True]) == "voldoende"


def test_bepaal_oordeel_geen_ontbrekend_een_voldoet():
    assert _bepaal_oordeel([True, False, False]) == "onvoldoende"


def test_bepaal_oordeel_geen_ontbrekend_geen_voldoet():
    assert _bepaal_oordeel([False, False, False]) == "onvoldoende"


def test_bepaal_oordeel_een_ontbreekt_gelijk():
    assert _bepaal_oordeel([True, None, True]) == "voldoende"
    assert _bepaal_oordeel([False, None, False]) == "onvoldoende"


def test_bepaal_oordeel_een_ontbreekt_ongelijk():
    assert _bepaal_oordeel([True, None, False]) == "niet_te_bepalen"


def test_bepaal_oordeel_twee_ontbreken():
    assert _bepaal_oordeel([True, None, None]) == "niet_te_bepalen"


# ---------------------------------------------------------------------------
# populatie_regele_filter
# ---------------------------------------------------------------------------


def _obt_met_leerweg_niveau():
    return pl.DataFrame({
        "Leertraject": ["BOL", "BBL", "ODT", "OV", "OD"],
        "Niveau": ["MBO-2", "MBO-3", "MBO-4", "MBO-2", "MBO-2"],
    })


def test_populatie_filter_verwijdert_ov_od():
    result = populatie_regele_filter(_obt_met_leerweg_niveau())
    assert result["Leertraject"].to_list() == ["BOL", "BBL", "ODT"]


def test_populatie_filter_verwijdert_niveau_1():
    df = pl.DataFrame({
        "Leertraject": ["BOL", "BOL", "BOL"],
        "Niveau": ["MBO-1", "MBO-2", "MBO-4"],
    })
    result = populatie_regele_filter(df)
    assert result["Niveau"].to_list() == ["MBO-2", "MBO-4"]


def test_populatie_filter_min_niveau():
    df = pl.DataFrame({
        "Leertraject": ["BOL", "BOL", "BOL"],
        "Niveau": ["MBO-3", "MBO-4", "MBO-2"],
    })
    result = populatie_regele_filter(df, min_niveau=3)
    assert result["Niveau"].to_list() == ["MBO-3", "MBO-4"]


def test_populatie_filter_ontbrekende_kolommen_geen_crash():
    df = pl.DataFrame({"_persoon_id": ["P1"]})
    result = populatie_regele_filter(df)
    assert result.height == 1


def test_populatie_filter_leerweg_case_insensitief():
    df = pl.DataFrame({
        "Leertraject": ["bol", "OV"],
        "Niveau": ["MBO-2", "MBO-2"],
    })
    result = populatie_regele_filter(df)
    assert result["Leertraject"].to_list() == ["bol"]


# ---------------------------------------------------------------------------
# entree_indicatoren
# ---------------------------------------------------------------------------


def _entree_obt():
    """Vier niveau-1 studenten in de vier categorieën + één niveau-2 rij."""
    return pl.DataFrame({
        "Niveau": ["MBO-1", "MBO-1", "MBO-1", "MBO-1", "MBO-2"],
        "_entree_doorstroom": [True, True, False, False, False],
        "_entree_uitstroom": [False, False, True, True, False],
        "_gediplomeerd_in_jaar": [True, False, True, False, False],
    })


def test_entree_indicatoren_vier_categorieen():
    result = entree_indicatoren(_entree_obt())
    assert result.height == 4
    cats = dict(
        zip(
            result["Categorie"].to_list(),
            result["Aantal"].to_list(),
            strict=True,
        )
    )
    assert cats == {
        "Doorstroom met diploma": 1,
        "Doorstroom zonder diploma": 1,
        "Uitstroom met diploma": 1,
        "Uitstroom zonder diploma": 1,
    }


def test_entree_indicatoren_aandelen_tellen_op_100():
    result = entree_indicatoren(_entree_obt())
    assert result["Aandeel (%)"].round().sum() == 100


def test_entree_totaal():
    assert entree_totaal(_entree_obt()) == 4


def test_entree_indicatoren_geen_niveau_1():
    df = pl.DataFrame({
        "Niveau": ["MBO-2", "MBO-3"],
        "_entree_doorstroom": [False, False],
        "_entree_uitstroom": [False, False],
        "_gediplomeerd_in_jaar": [False, False],
    })
    assert entree_indicatoren(df).is_empty()


def test_entree_indicatoren_ontbrekende_kolommen():
    df = pl.DataFrame({"Niveau": ["MBO-1"]})
    result = entree_indicatoren(df)
    assert set(result.columns) == {"Categorie", "Aantal", "Aandeel (%)"}
    assert result.is_empty()


def test_entree_indicatoren_ongeclassificeerde_rijen_vallen_in_uitstroom():
    """Rij die nergens een vlag heeft (geen doorstroom/uitstroom) → uitval."""
    df = pl.DataFrame({
        "Niveau": ["MBO-1"],
        "_entree_doorstroom": [False],
        "_entree_uitstroom": [False],
        "_gediplomeerd_in_jaar": [False],
    })
    result = entree_indicatoren(df)
    row = result.filter(pl.col("Categorie") == "Uitstroom zonder diploma")
    assert row["Aantal"].to_list() == [1]


# ---------------------------------------------------------------------------
# Demo-data integratie
# ---------------------------------------------------------------------------


def test_normen_en_populatie_in_demo_obt(demo_obt):
    obt = demo_obt["obt_inschrijvingen"]
    populatie = populatie_regele_filter(obt)
    assert "OV" not in populatie["Leertraject"].to_list()
    assert "MBO-1" not in populatie["Niveau"].to_list()

    entree = entree_indicatoren(obt)
    if not entree.is_empty():
        assert set(entree["Categorie"].to_list()) <= {
            "Doorstroom met diploma",
            "Doorstroom zonder diploma",
            "Uitstroom met diploma",
            "Uitstroom zonder diploma",
        }
