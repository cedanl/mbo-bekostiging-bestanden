"""Herkomst van de referentietabellen in ``metadata/`` (#132).

``metadata/referentiedata.json`` legt per databestand vast:

- ``bron``: waar het vandaan komt (``bron_url``/``bron_ids`` als het script het
  ophaalt); ``onbekend`` als dat niet is vastgelegd bij opname.
- ``opgenomen``: wanneer deze inhoud in de repo kwam.
- ``dekking_tot``: laatste datum waarvoor het bestand de opleidingen dekt
  (alleen bekend voor de S-BB-lijsten, per schooljaar gepubliceerd).
- ``sha256`` en ``rijen``: de inhoud; een test bewaakt dat ze kloppen.

De ster neemt het manifest over als ``meta_referentiedata``, met ``afwijkend``
als het bestand op schijf niet meer de inhoud uit het manifest heeft.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

METADATA = Path(__file__).parent / "metadata"
_MANIFEST = "referentiedata.json"
TABEL = "meta_referentiedata"
# Referenties waaruit Opleidingcode → niveau komt (zie transform._vul_niveau_aan).
OPLEIDINGSREFERENTIES = ("crebo.csv", "sbb_koppeltabel.parquet")
_OPLEIDINGSCODE = {"crebo.csv": "code", "sbb_koppeltabel.parquet": "opleidingscode"}
_SCHEMA = {
    "bestand": pl.Utf8,
    "bron": pl.Utf8,
    "opgenomen": pl.Date,
    "dekking_tot": pl.Date,
    "sha256": pl.Utf8,
    "rijen": pl.Int64,
    "afwijkend": pl.Boolean,
}


def laad_manifest() -> dict[str, dict[str, Any]]:
    """Het manifest: bestandsnaam → herkomst (zie moduledocstring)."""
    return json.loads((METADATA / _MANIFEST).read_text(encoding="utf-8"))


def werk_manifest_bij(bestand: str, **velden: Any) -> None:
    """Zet velden van één bestand, en sha256 en rijen naar de inhoud op schijf."""
    manifest = laad_manifest()
    pad = METADATA / bestand
    manifest[bestand] = {
        **manifest.get(bestand, {}),
        **velden,
        "sha256": sha256(pad),
        "rijen": rijen(pad),
    }
    (METADATA / _MANIFEST).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def sha256(pad: Path) -> str:
    return hashlib.sha256(pad.read_bytes()).hexdigest()


def rijen(pad: Path) -> int:
    if pad.suffix == ".parquet":
        return pl.scan_parquet(pad).select(pl.len()).collect().item()
    return pl.read_csv(pad, infer_schema_length=0).height


def meta_referentiedata() -> pl.DataFrame:
    """Eén rij per referentiebestand, met ``afwijkend`` als de inhoud verschilt."""
    rijen_ = [
        {
            "bestand": bestand,
            "bron": regel["bron"],
            "opgenomen": date.fromisoformat(regel["opgenomen"]),
            "dekking_tot": (
                date.fromisoformat(regel["dekking_tot"])
                if regel.get("dekking_tot")
                else None
            ),
            "sha256": regel["sha256"],
            "rijen": regel["rijen"],
            "afwijkend": (METADATA / bestand).exists()
            and sha256(METADATA / bestand) != regel["sha256"],
        }
        for bestand, regel in sorted(laad_manifest().items())
    ]
    return pl.DataFrame(rijen_, schema=_SCHEMA)


def bekende_opleidingscodes() -> set[str]:
    """Alle opleidingscodes die de niveau-referenties kennen."""
    codes: set[str] = set()
    for bestand in OPLEIDINGSREFERENTIES:
        pad = METADATA / bestand
        kolom = pl.col(_OPLEIDINGSCODE[bestand]).cast(pl.Utf8)
        tabel = (
            pl.scan_parquet(pad)
            if pad.suffix == ".parquet"
            else pl.scan_csv(pad, infer_schema_length=0)
        )
        codes |= set(tabel.select(kolom).collect().to_series().drop_nulls())
    return codes
