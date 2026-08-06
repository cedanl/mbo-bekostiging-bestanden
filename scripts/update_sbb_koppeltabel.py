"""Haalt de S-BB Mbo-opleidingskoppeltabel op en slaat hem op als Parquet.

Gebruik:
    uv run python scripts/update_sbb_koppeltabel.py

Het script downloadt alle beschikbare koppeltabel-bestanden in het nieuwe
formaat (met schooljaar-kolom) en combineert ze tot één lookup-tabel per
opleidingscode. Het resultaat wordt weggeschreven naar:

    src/mbo_bekostiging_bestanden/metadata/sbb_koppeltabel.parquet

Commit dit bestand daarna in git zodat eindgebruikers het direct hebben.
"""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path

import polars as pl

# Output IDs van de Mbo-opleidingskoppeltabel (Groep 19) in het nieuwe formaat.
# Kolommen beginnen met 'opleidingscode' en bevatten een 'schooljaar'-kolom.
# Voeg nieuwe IDs toe zodra S-BB een nieuw schooljaar publiceert.
_KOPPELTABEL_IDS = [
    "58496",  # 2025-2026 (versie 1)
    "58499",  # 2025-2026 (versie 2, bijgewerkt)
    "58526",  # 2025-2026 + 2026-2027 (meest recent)
]
_BASE_URL = "https://kwalificatie-mijn.s-bb.nl/Lijsten/Output/"

_OUT = (
    Path(__file__).parent.parent
    / "src/mbo_bekostiging_bestanden/metadata/sbb_koppeltabel.parquet"
)

_KOLOMMEN = {
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

_HERNOEM = {
    "verwijzende opleidingscode kwalificatie schooljaar": "opvolger_kwalificatie",
    "verwijzende opleidingscode dossier schooljaar": "opvolger_dossier",
    "beroep (kwalificatie)": "beroepsnaam",
    "niveau beroep": "niveau",
}


def _download(file_id: str) -> pl.DataFrame | None:
    url = _BASE_URL + file_id
    print(f"  Downloading {url} …", end=" ")
    try:
        data = urllib.request.urlopen(url, timeout=30).read()
        df = pl.read_excel(io.BytesIO(data))
    except Exception as exc:
        print(f"FOUT: {exc}")
        return None

    if "opleidingscode" not in df.columns or "schooljaar" not in df.columns:
        print("overgeslagen (oud formaat zonder schooljaar-kolom)")
        return None

    # Selecteer alleen aanwezige kolommen; vul ontbrekende met null
    df = df.select([k for k in _KOLOMMEN if k in df.columns]).cast(
        {k: v for k, v in _KOLOMMEN.items() if k in df.columns}
    )
    for col, dtype in _KOLOMMEN.items():
        if col not in df.columns:
            df = df.with_columns(pl.lit(None).cast(dtype).alias(col))
    df = df.select(list(_KOLOMMEN.keys()))
    jaren = df["schooljaar"].drop_nulls().unique().sort().to_list()
    print(f"OK ({df.height} rijen, schooljaar={jaren})")
    return df


def main() -> None:
    print("S-BB koppeltabel ophalen …")
    frames: list[pl.DataFrame] = []
    for fid in _KOPPELTABEL_IDS:
        df = _download(fid)
        if df is not None:
            frames.append(df)

    if not frames:
        raise SystemExit("Geen bruikbare bestanden gevonden.")

    combined = pl.concat(frames).unique(
        subset=["opleidingscode", "schooljaar"], keep="last", maintain_order=True
    )

    # Aggregeer per opleidingscode: meest recente naam/beroep, min/max schooljaar
    lookup = (
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

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    lookup.write_parquet(_OUT, compression="zstd")
    print(f"\nGeschreven: {_OUT} ({_OUT.stat().st_size // 1024} KB, {lookup.height} codes)")
    print(f"Kolommen: {lookup.columns}")


if __name__ == "__main__":
    main()
