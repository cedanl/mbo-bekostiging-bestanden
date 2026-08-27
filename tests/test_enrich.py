"""Tests voor enrich.py (verrijking van inschrijvingen met decodeertabellen).

Alle tests gebruiken in-memory DataFrames; geen file I/O.
De lookup-functies worden gemockt zodat de CSV-bestanden niet nodig zijn.
"""

from unittest.mock import patch

import polars as pl

from mbo_bekostiging_bestanden.enrich import enrich_inschrijvingen

# ---------------------------------------------------------------------------
# Hulpfuncties: minimale lookups in-memory
# ---------------------------------------------------------------------------


def _nationaliteit_lookup() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "code": ["0001", "0002", "1234"],
            "omschrijving": ["Nederlandse", "Behandeld als Nederlander", "Marokkaanse"],
            "migratieachtergrond_ln": ["Autochtoon", "Onbekend", "Niet-Westers Afrika"],
        }
    )


def _landcode_lookup() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "code": ["5001", "5002", "6001"],
            "naam_land": ["Canada", "Frankrijk", "Marokko"],
            "migratieachtergrond_ln": [
                "Westers Amerika",
                "Westers Europa",
                "Niet-Westers Afrika",
            ],
        }
    )


def _postcode_lookup() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "postcode": ["1234", "5678"],
            "gemeentecode": ["0363", "0599"],
            "gemeentenaam": ["Amsterdam", "Rotterdam"],
        }
    )


def _brin_lookup() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "brin": ["01AA", "02BB"],
            "naam": ["ROC West-Nederland", "Graafschap College"],
            "plaats": ["DEN HAAG", "DOETINCHEM"],
        }
    )


def _crebo_lookup() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "code": ["25655", "23301"],
            "naam": ["Applicatieontwikkelaar", "Entree"],
            "leerweg": ["BOL", "BOL"],
            "hoofdgroep_naam": ["ICT", "Entree"],
            "subgroep_naam": ["Software development", "Entree"],
            "dossier_code": ["23001", "23002"],
            "dossier_naam": ["Software development", "Entree"],
            "sectorkamer_naam": ["Techniek en gebouwde omgeving", "Entree"],
        }
    )


# ---------------------------------------------------------------------------
# Context-manager: patch alle vier lookups tegelijk
# ---------------------------------------------------------------------------


def _sbb_crebolijst_lookup() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "kwalificatiecode": ["25655", "23301"],
            "geldig_van": ["2015-08-01", "2015-08-01"],
            "geldig_tot": [None, "2023-08-01"],
            "prijsfactor": ["1.3", "1.0"],
            "soort_opleiding": ["Vakopleiding", "Entree opleiding"],
        }
    )


def _sbb_koppeltabel_lookup() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "opleidingscode": [25655, 23301],
            "beroepsnaam": ["Applicatieontwikkelaar", "Entree"],
            "niveau": ["3", "1"],
            "opvolger_kwalificatie": [0, 0],
            "eerste_schooljaar": ["2025-2026", "2025-2026"],
            "laatste_schooljaar": ["2026-2027", "2026-2027"],
        }
    )


def _patch_lookups():
    """Patch alle zeven laad-functies met in-memory tabellen.

    Gebruik: ``with *_patch_lookups():`` of
    ``mocks = _patch_lookups(); with mocks[0], ..., mocks[6]:``.
    """
    return (
        patch(
            "mbo_bekostiging_bestanden.enrich._laad_nationaliteitscode",
            return_value=_nationaliteit_lookup(),
        ),
        patch(
            "mbo_bekostiging_bestanden.enrich._laad_landcode",
            return_value=_landcode_lookup(),
        ),
        patch(
            "mbo_bekostiging_bestanden.enrich._laad_postcodecijfers",
            return_value=_postcode_lookup(),
        ),
        patch(
            "mbo_bekostiging_bestanden.enrich._laad_brinnummer",
            return_value=_brin_lookup(),
        ),
        patch(
            "mbo_bekostiging_bestanden.enrich._laad_crebo",
            return_value=_crebo_lookup(),
        ),
        patch(
            "mbo_bekostiging_bestanden.enrich._laad_sbb_koppeltabel",
            return_value=_sbb_koppeltabel_lookup(),
        ),
        patch(
            "mbo_bekostiging_bestanden.enrich._laad_sbb_crebolijst",
            return_value=_sbb_crebolijst_lookup(),
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_nationaliteit1_naam_en_migratieachtergrond():
    """Nationaliteit1 krijgt naam en migratieachtergrond na join."""
    df = pl.DataFrame({"Nationaliteit1": ["0001", "1234"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert "Nationaliteit1_naam" in result.columns
    assert "Nationaliteit1_migratieachtergrond" in result.columns
    assert result["Nationaliteit1_naam"].to_list() == ["Nederlandse", "Marokkaanse"]
    assert result["Nationaliteit1_migratieachtergrond"].to_list() == [
        "Autochtoon",
        "Niet-Westers Afrika",
    ]


def test_nationaliteit_zonder_voorloopnullen_matcht():
    """Codes zonder voorloopnullen (bijv. na Excel-export) worden gepad en matchen."""
    df = pl.DataFrame({"Nationaliteit1": ["1", "1234", ""]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    # "1" -> "0001" -> Nederlandse; "1234" blijft; "" blijft leeg (geen match).
    assert result["Nationaliteit1"].to_list() == ["0001", "1234", ""]
    assert result["Nationaliteit1_naam"].to_list() == [
        "Nederlandse",
        "Marokkaanse",
        None,
    ]


def test_nationaliteit2_naam_en_migratieachtergrond():
    """Nationaliteit2 krijgt aparte kolommen, onafhankelijk van Nationaliteit1."""
    df = pl.DataFrame(
        {
            "Nationaliteit1": ["0001"],
            "Nationaliteit2": ["0002"],
        }
    )

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert "Nationaliteit2_naam" in result.columns
    assert result["Nationaliteit2_naam"][0] == "Behandeld als Nederlander"
    assert result["Nationaliteit2_migratieachtergrond"][0] == "Onbekend"


def test_codegeboorteland_naam():
    """CodeGeboorteland krijgt naam_land en migratieachtergrond na join."""
    df = pl.DataFrame({"CodeGeboorteland": ["5002"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert "CodeGeboorteland_naam" in result.columns
    assert result["CodeGeboorteland_naam"][0] == "Frankrijk"
    assert result["CodeGeboorteland_migratieachtergrond"][0] == "Westers Europa"


def test_postcodecijfers_naar_gemeente():
    """Postcodecijfers levert Gemeente en Gemeentecode op."""
    df = pl.DataFrame({"Postcodecijfers": ["1234", "5678"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert "Gemeente" in result.columns
    assert "Gemeentecode" in result.columns
    assert result["Gemeente"].to_list() == ["Amsterdam", "Rotterdam"]
    assert result["Gemeentecode"].to_list() == ["0363", "0599"]


def test_brin_naar_instelling():
    """BRIN levert Instelling_naam en Instelling_plaats op."""
    df = pl.DataFrame({"BRIN": ["01AA", "02BB"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert "Instelling_naam" in result.columns
    assert "Instelling_plaats" in result.columns
    assert result["Instelling_naam"].to_list() == [
        "ROC West-Nederland",
        "Graafschap College",
    ]
    assert result["Instelling_plaats"].to_list() == ["DEN HAAG", "DOETINCHEM"]


def test_ontbrekende_bronkolommen_geen_crash():
    """Als bronkolommen ontbreken, geen KeyError — kolommen worden overgeslagen."""
    # Helemaal leeg DataFrame
    df = pl.DataFrame({"irrelevant": ["x"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    # Geen verrijkingskolommen toegevoegd (bronkolommen ontbreken)
    assert "Nationaliteit1_naam" not in result.columns
    assert "CodeGeboorteland_naam" not in result.columns
    assert "Gemeente" not in result.columns
    assert "Instelling_naam" not in result.columns
    # Oorspronkelijke kolom intact
    assert "irrelevant" in result.columns


def test_ontbrekende_kolom_per_type():
    """Elke join sla je apart over als de bronkolom ontbreekt."""
    df = pl.DataFrame({"Nationaliteit1": ["0001"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    # Nationaliteit1 wel verrijkt
    assert "Nationaliteit1_naam" in result.columns
    # Andere join-kolommen ontbreken correct
    assert "Nationaliteit2_naam" not in result.columns
    assert "CodeGeboorteland_naam" not in result.columns
    assert "Gemeente" not in result.columns
    assert "Instelling_naam" not in result.columns


def test_onbekende_code_geeft_null():
    """Code die niet in de lookup staat → null, geen crash."""
    df = pl.DataFrame({"Nationaliteit1": ["9999"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert result["Nationaliteit1_naam"][0] is None
    assert result["Nationaliteit1_migratieachtergrond"][0] is None


def test_onbekende_brin_geeft_null():
    """BRIN die niet in de lookup staat → null voor naam en plaats."""
    df = pl.DataFrame({"BRIN": ["ZZZZ"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert result["Instelling_naam"][0] is None
    assert result["Instelling_plaats"][0] is None


def test_lege_string_code_geeft_null():
    """Lege-string code → join levert null, geen crash."""
    df = pl.DataFrame({"CodeGeboorteland": [""]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert result["CodeGeboorteland_naam"][0] is None


def test_originele_kolommen_ongewijzigd():
    """Bronkolommen blijven onveranderd na verrijking."""
    df = pl.DataFrame(
        {
            "BRIN": ["01AA"],
            "Nationaliteit1": ["0001"],
            "extra": ["waarde"],
        }
    )

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert result["BRIN"][0] == "01AA"
    assert result["Nationaliteit1"][0] == "0001"
    assert result["extra"][0] == "waarde"


def test_crebo_verrijking_naam_en_domein():
    """Opleidingcode krijgt naam, domein, subgroep na join."""
    df = pl.DataFrame({"Opleidingcode": ["25655", "23301"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert "Opleiding_naam" in result.columns
    assert "Opleiding_domein" in result.columns
    assert "Opleiding_subgroep" in result.columns
    assert "Opleiding_leerweg" in result.columns
    assert result["Opleiding_naam"].to_list() == ["Applicatieontwikkelaar", "Entree"]
    assert result["Opleiding_domein"].to_list() == ["ICT", "Entree"]


def test_crebo_onbekende_code_geeft_null():
    """CREBO-code niet in lookup → null."""
    df = pl.DataFrame({"Opleidingcode": ["99999"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert result["Opleiding_naam"][0] is None
    assert result["Opleiding_domein"][0] is None


def test_crebo_ontbrekende_kolom_geen_crash():
    """Zonder Opleidingcode → geen CREBO-kolommen, geen crash."""
    df = pl.DataFrame({"irrelevant": ["x"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert "Opleiding_naam" not in result.columns


def test_sbb_koppeltabel_verrijking():
    """Opleidingcode krijgt beroep, niveau en opvolger na join met S-BB koppeltabel."""
    df = pl.DataFrame({"Opleidingcode": ["25655", "23301"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert "Opleiding_beroep" in result.columns
    assert "Opleiding_niveau" in result.columns
    assert "Opleiding_opvolger" in result.columns
    assert "Opleiding_eerste_schooljaar" in result.columns
    assert "Opleiding_laatste_schooljaar" in result.columns
    assert result["Opleiding_beroep"].to_list() == ["Applicatieontwikkelaar", "Entree"]
    assert result["Opleiding_niveau"].to_list() == ["3", "1"]


def test_sbb_koppeltabel_onbekende_code_geeft_null():
    """CREBO-code niet in S-BB koppeltabel → null voor beroep/niveau."""
    df = pl.DataFrame({"Opleidingcode": ["99999"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert result["Opleiding_beroep"][0] is None
    assert result["Opleiding_niveau"][0] is None


def test_crebolijst_verrijking_geldigheid_en_prijsfactor():
    """Opleidingcode krijgt geldig_van, geldig_tot, prijsfactor en soort_opleiding."""
    df = pl.DataFrame({"Opleidingcode": ["25655", "23301"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert "Opleiding_geldig_van" in result.columns
    assert "Opleiding_geldig_tot" in result.columns
    assert "Opleiding_prijsfactor" in result.columns
    assert "Opleiding_soort_opleiding" in result.columns
    assert result["Opleiding_geldig_van"].to_list() == ["2015-08-01", "2015-08-01"]
    assert result["Opleiding_geldig_tot"].to_list() == [None, "2023-08-01"]
    assert result["Opleiding_prijsfactor"].to_list() == ["1.3", "1.0"]


def test_crebolijst_onbekende_code_geeft_null():
    """Code niet in crebolijst → null voor geldigheidskolommen."""
    df = pl.DataFrame({"Opleidingcode": ["99999"]})

    mocks = _patch_lookups()
    with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], mocks[5], mocks[6]:
        result = enrich_inschrijvingen(df)

    assert result["Opleiding_geldig_van"][0] is None
    assert result["Opleiding_geldig_tot"][0] is None
