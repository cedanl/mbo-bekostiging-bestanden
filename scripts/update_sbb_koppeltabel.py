"""Haalt de S-BB Mbo-opleidingskoppeltabel en crebolijsten op en slaat ze op als Parquet.

Gebruik:
    uv run python scripts/update_sbb_koppeltabel.py

Het script combineert twee bronnen uit S-BB:

- **Groep 19 (koppeltabel)**: beroepsnaam, niveau en opvolgercode per opleidingscode.
  Output: ``src/mbo_bekostiging_bestanden/metadata/sbb_koppeltabel.parquet``

- **Groep 14 (crebolijsten)**: officiële geldigheidsperioden, prijsfactor en soort opleiding
  per opleidingscode op basis van de gepubliceerde crebolijsten (2015 t/m heden).
  Output: ``src/mbo_bekostiging_bestanden/metadata/sbb_crebolijst.parquet``

Commit beide bestanden in git zodat eindgebruikers ze direct hebben.
"""

from __future__ import annotations

import datetime
import io
import re
import urllib.request
from pathlib import Path

import polars as pl

_BASE_URL = "https://kwalificatie-mijn.s-bb.nl/Lijsten/Output/"
_METADATA = (
    Path(__file__).parent.parent / "src/mbo_bekostiging_bestanden/metadata"
)
_OUT_KOPPEL = _METADATA / "sbb_koppeltabel.parquet"
_OUT_CREBO = _METADATA / "sbb_crebolijst.parquet"

# ---------------------------------------------------------------------------
# Groep 19: Mbo-opleidingskoppeltabel (beroep / niveau / opvolger)
# ---------------------------------------------------------------------------

# Output IDs van de koppeltabel (Groep 19) in het nieuwe formaat.
# Voeg nieuwe IDs toe zodra S-BB een nieuw schooljaar publiceert.
_KOPPELTABEL_IDS = [
    "58496",  # 2025-2026 (versie 1)
    "58499",  # 2025-2026 (versie 2, bijgewerkt)
    "58526",  # 2025-2026 + 2026-2027 (meest recent)
]

_KOLOMMEN_KOPPEL = {
    "opleidingscode": pl.Int64,
    "opleidingsnaam": pl.String,
    "schooljaar": pl.String,
    "verwijzende opleidingscode kwalificatie schooljaar": pl.Int64,
    "verwijzende opleidingscode dossier schooljaar": pl.Int64,
    "beroep_id": pl.String,
    "beroep (kwalificatie)": pl.String,
    "niveau beroep": pl.String,
    "sectorkamer (op opleidingscode)": pl.String,
}


def _download_koppeltabel(file_id: str) -> pl.DataFrame | None:
    url = _BASE_URL + file_id
    print(f"  Groep 19 {url} …", end=" ")
    try:
        data = urllib.request.urlopen(url, timeout=30).read()
        df = pl.read_excel(io.BytesIO(data))
    except Exception as exc:
        print(f"FOUT: {exc}")
        return None

    if "opleidingscode" not in df.columns or "schooljaar" not in df.columns:
        print("overgeslagen (oud formaat zonder schooljaar-kolom)")
        return None

    df = df.select([k for k in _KOLOMMEN_KOPPEL if k in df.columns]).cast(
        {k: v for k, v in _KOLOMMEN_KOPPEL.items() if k in df.columns}
    )
    for col, dtype in _KOLOMMEN_KOPPEL.items():
        if col not in df.columns:
            df = df.with_columns(pl.lit(None).cast(dtype).alias(col))
    df = df.select(list(_KOLOMMEN_KOPPEL.keys()))
    jaren = df["schooljaar"].drop_nulls().unique().sort().to_list()
    print(f"OK ({df.height} rijen, schooljaar={jaren})")
    return df


def _bouw_koppeltabel() -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for fid in _KOPPELTABEL_IDS:
        df = _download_koppeltabel(fid)
        if df is not None:
            frames.append(df)

    if not frames:
        raise SystemExit("Geen bruikbare koppeltabel-bestanden gevonden.")

    combined = pl.concat(frames).unique(
        subset=["opleidingscode", "schooljaar"], keep="last", maintain_order=True
    )
    return (
        combined.sort("schooljaar")
        .group_by("opleidingscode")
        .agg(
            pl.col("opleidingsnaam").last(),
            pl.col("beroep_id").last(),
            pl.col("beroep (kwalificatie)").last().alias("beroepsnaam"),
            pl.col("niveau beroep").last().alias("niveau"),
            pl.col("sectorkamer (op opleidingscode)").last().alias("sectorkamer"),
            pl.col("verwijzende opleidingscode kwalificatie schooljaar")
            .last()
            .alias("opvolger_kwalificatie"),
            pl.col("verwijzende opleidingscode dossier schooljaar")
            .last()
            .alias("opvolger_dossier"),
            pl.col("schooljaar").min().alias("eerste_schooljaar"),
            pl.col("schooljaar").max().alias("laatste_schooljaar"),
        )
        .sort("opleidingscode")
    )


# ---------------------------------------------------------------------------
# Groep 14: Crebolijsten (geldigheid / prijsfactor / soort opleiding)
# ---------------------------------------------------------------------------

# Alle Output-IDs van Groep 14 met een bruikbare code-kolom (2015 t/m 2026).
# Oudere bestanden (53729–53731, vóór 2015) hebben een afwijkend formaat zonder
# herkenbare code-kolom en worden niet meegenomen.
_CREBOLIJST_IDS = [
    "58436",  # HKS 2015
    "58454",  # HKS 2016
    "58455",  # HKS 2016 juli
    "58458",  # HKS 2017 jan
    "58459",  # HKS 2017 mei
    "58460",  # HKS 2017 juli
    "58461",  # HKS 2018 jan
    "58464",  # HKS 2018/2019 (amendement)
    "58466",  # HKS 2019 jan (amendement)
    "58467",  # HKS 2019 apr (amendement)
    "58468",  # HKS 2019 juli (amendement)
    "58469",  # HKS 2020 (amendement)
    "58470",  # HKS 2020 (amendement)
    "58471",  # HKS 2020 (amendement)
    "58472",  # HKS 2020 (amendement)
    "58474",  # HKS 2021 (amendement)
    "58484",  # HKS 2022
    "58479",  # HKS 2023 jan
    "58488",  # HKS 2023 juli
    "58490",  # HKS 2024
    "58493",  # HKS 2024 apr
    "58494",  # HKS 2024 okt → geldig 2025-08-01
    "58498",  # HKS 2025 apr
    "58500",  # HKS 2025 okt → geldig 2026-08-01
    "58502",  # HKS 2026 apr
]

# Kolomnamen voor de opleidingscode per versiejaar
_CODE_COLS = ["Crebonummer", "Erkende opleidingscode", "Opleidingscode"]

# Bestanden met ≥ dit aantal codes zijn volledige lijsten (niet tussentijdse amendements)
_FULL_MIN = 200


def _parse_geldig_datum(header: str) -> datetime.date | None:
    """Extraheer 'geldig vanaf'-datum uit de kolomnaamkoptekst van het Excel-bestand."""
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", header)
    if m:
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"\b(20\d{2})\b", header)
    if m:
        return datetime.date(int(m.group(1)), 8, 1)
    return None


def _download_crebolijst(
    file_id: str,
) -> tuple[datetime.date | None, pl.DataFrame | None, bool]:
    """Download één crebolijst.

    Retourneert ``(geldig_van, df, is_volledig)``.
    ``df`` heeft kolommen: ``kwalificatiecode`` (String), ``prijsfactor`` (String),
    ``soort_opleiding`` (String).
    """
    url = _BASE_URL + file_id
    print(f"  Groep 14 {url} …", end=" ")
    try:
        data = urllib.request.urlopen(url, timeout=30).read()
        df = pl.read_excel(io.BytesIO(data), infer_schema_length=0)
    except Exception as exc:
        print(f"FOUT: {exc}")
        return None, None, False

    geldig_van = _parse_geldig_datum(df.columns[0])
    code_col = next((c for c in _CODE_COLS if c in df.columns), None)
    if code_col is None:
        print("overgeslagen (geen code-kolom)")
        return None, None, False

    # Selecteer code + beschikbare attribuutkolommen
    select_map: dict[str, str] = {code_col: "kwalificatiecode"}
    if "Prijsfactor" in df.columns:
        select_map["Prijsfactor"] = "prijsfactor"
    if "Soort opleiding" in df.columns:
        select_map["Soort opleiding"] = "soort_opleiding"

    result = (
        df.select(list(select_map.keys()))
        .rename(select_map)
        .filter(pl.col("kwalificatiecode").is_not_null())
    )
    for missing in ("prijsfactor", "soort_opleiding"):
        if missing not in result.columns:
            result = result.with_columns(pl.lit(None).alias(missing))

    is_full = result.height >= _FULL_MIN
    print(f"OK ({result.height} codes, geldig_van={geldig_van}, volledig={is_full})")
    return geldig_van, result, is_full


def _bouw_sbb_crebolijst() -> pl.DataFrame:
    """Bouw crebolijst-opzoektabel op basis van Groep 14.

    Retourneert een DataFrame met:
        ``kwalificatiecode`` (String),
        ``geldig_van`` (String, bijv. '2015-08-01'),
        ``geldig_tot`` (String nullable),
        ``prijsfactor`` (String nullable),
        ``soort_opleiding`` (String nullable).

    Aanpak:
    - ``geldig_van``: vroegste datum waarop de code verschijnt (alle bestanden).
    - ``geldig_tot``: datum van de eerste *volledige* lijst waarop de code niet meer
      voorkomt; null als de code nog in de meest recente volledige lijst staat.
    - ``prijsfactor`` / ``soort_opleiding``: waarden uit de meest recente lijst
      waar de code voorkomt.
    """
    full_snapshots: dict[datetime.date, set[str]] = {}
    # per code: (earliest_date, {date: (prijsfactor, soort_opleiding)})
    first_seen: dict[str, datetime.date] = {}
    attribs: dict[str, dict[datetime.date, tuple[str | None, str | None]]] = {}

    for file_id in _CREBOLIJST_IDS:
        geldig_van, df, is_full = _download_crebolijst(file_id)
        if geldig_van is None or df is None:
            continue
        for row in df.iter_rows(named=True):
            code: str = row["kwalificatiecode"]
            if not code:
                continue
            if code not in first_seen or geldig_van < first_seen[code]:
                first_seen[code] = geldig_van
            attribs.setdefault(code, {})[geldig_van] = (
                row.get("prijsfactor"),
                row.get("soort_opleiding"),
            )
        if is_full:
            snap = full_snapshots.setdefault(geldig_van, set())
            for row in df.iter_rows(named=True):
                if row["kwalificatiecode"]:
                    snap.add(row["kwalificatiecode"])

    if not full_snapshots:
        return pl.DataFrame(
            schema={
                "kwalificatiecode": pl.String,
                "geldig_van": pl.String,
                "geldig_tot": pl.String,
                "prijsfactor": pl.String,
                "soort_opleiding": pl.String,
            }
        )

    sorted_dates = sorted(full_snapshots.keys())
    latest_date = sorted_dates[-1]

    rows: list[dict] = []
    for code in sorted(first_seen.keys()):
        gv = first_seen[code]

        dates_in_full = [d for d in sorted_dates if code in full_snapshots[d]]
        if not dates_in_full:
            geldig_tot: datetime.date | None = None
        else:
            last_full = dates_in_full[-1]
            if last_full == latest_date:
                geldig_tot = None
            else:
                idx = sorted_dates.index(last_full)
                geldig_tot = sorted_dates[idx + 1]

        # Attribuutwaarden uit de meest recente listing
        code_attribs = attribs.get(code, {})
        if code_attribs:
            last_attrib_date = max(code_attribs.keys())
            prijsfactor, soort = code_attribs[last_attrib_date]
        else:
            prijsfactor, soort = None, None

        rows.append({
            "kwalificatiecode": code,
            "geldig_van": gv.isoformat(),
            "geldig_tot": geldig_tot.isoformat() if geldig_tot else None,
            "prijsfactor": prijsfactor,
            "soort_opleiding": soort,
        })

    return pl.DataFrame(rows, schema={
        "kwalificatiecode": pl.String,
        "geldig_van": pl.String,
        "geldig_tot": pl.String,
        "prijsfactor": pl.String,
        "soort_opleiding": pl.String,
    })


# ---------------------------------------------------------------------------
# Hoofdprogramma
# ---------------------------------------------------------------------------


def main() -> None:
    print("=== Groep 19: koppeltabel ophalen ===")
    koppel = _bouw_koppeltabel()
    _METADATA.mkdir(parents=True, exist_ok=True)
    koppel.write_parquet(_OUT_KOPPEL, compression="zstd")
    print(
        f"Geschreven: {_OUT_KOPPEL} "
        f"({_OUT_KOPPEL.stat().st_size // 1024} KB, {koppel.height} codes)"
    )
    print(f"Kolommen: {koppel.columns}\n")

    print("=== Groep 14: crebolijsten ophalen ===")
    crebo = _bouw_sbb_crebolijst()
    crebo.write_parquet(_OUT_CREBO, compression="zstd")
    n_actief = crebo["geldig_tot"].is_null().sum()
    n_verlopen = crebo["geldig_tot"].drop_nulls().len()
    print(
        f"Geschreven: {_OUT_CREBO} "
        f"({_OUT_CREBO.stat().st_size // 1024} KB, {crebo.height} codes)"
    )
    print(f"Kolommen: {crebo.columns}")
    print(f"Geldigheid: {n_actief} nog actief, {n_verlopen} verlopen")


if __name__ == "__main__":
    main()
