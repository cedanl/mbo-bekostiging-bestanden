"""Opleidingsniveau aanvullen uit de referentiedata (bron → CREBO → S-BB).

De herkomstcodes staan in ``niveau.py``, dat afhankelijkheidsloos blijft zodat
``quality.py`` ze kan lezen zonder de referentiedata te laden (#253).
"""

import functools
from pathlib import Path

import polars as pl

from mbo_bekostiging_bestanden import niveau
from mbo_bekostiging_bestanden.enrich import laad_sbb_koppeltabel

_METADATA = Path(__file__).parent / "metadata"
_CREBO_PREFIX = "MBO-"
_SBB_GEEN_NIVEAU = "n.v.t."


@functools.cache
def _laad_sbb_niveau() -> pl.DataFrame:
    """S-BB-koppeltabel als mapping code → ``MBO-n`` of ``n.v.t.``."""
    sbb_niveau = pl.col("niveau")
    return laad_sbb_koppeltabel().select(
        pl.col("opleidingscode").alias("_sbb_code"),
        pl.when(sbb_niveau == _SBB_GEEN_NIVEAU)
        .then(sbb_niveau)
        .otherwise(_CREBO_PREFIX + sbb_niveau)
        .alias("_sbb_niveau"),
    )


@functools.cache
def _laad_crebo_niveau() -> pl.DataFrame:
    """CREBO-tabel als mapping Opleidingcode → Niveau (``MBO-n``)."""
    return (
        pl.read_csv(_METADATA / "crebo.csv", infer_schema_length=0)
        .select(["code", "niveau"])
        .filter(pl.col("niveau").is_not_null())
        .with_columns(
            (_CREBO_PREFIX + pl.col("niveau")).alias("_crebo_niveau"),
        )
        .select(
            pl.col("code").alias("Opleidingcode"),
            pl.col("_crebo_niveau"),
        )
        .unique(subset=["Opleidingcode"], keep="first", maintain_order=True)
    )


def niveau_numeriek(col: pl.Expr) -> pl.Expr:
    """Extraheer het numerieke deel uit Niveau (bijv. ``"MBO-4"`` → ``4``)."""
    return col.str.extract(r"(\d+)$").cast(pl.Int32, strict=False)


def vul_niveau_aan(df: pl.DataFrame) -> pl.DataFrame:
    """Vul ontbrekend Niveau aan via CREBO en daarna S-BB; leg de herkomst vast.

    ``crebo.csv`` kent de nieuwe codering (22xxx/23xxx/79xxx) zonder niveau; de
    S-BB-koppeltabel wel.  ``_niveau_herkomst`` is ``bron``, ``crebo``, ``sbb``,
    ``sbb_nvt`` (S-BB zonder niveau) of ``onbekend``.
    """
    if "Niveau" not in df.columns or "Opleidingcode" not in df.columns:
        return df
    df = df.join(_laad_crebo_niveau(), on="Opleidingcode", how="left").join(
        _laad_sbb_niveau(),
        left_on=pl.col("Opleidingcode").cast(pl.Int64, strict=False),
        right_on="_sbb_code",
        how="left",
    )
    sbb_zonder_niveau = pl.col("_sbb_niveau") == _SBB_GEEN_NIVEAU
    sbb_niveau = pl.when(~sbb_zonder_niveau).then(pl.col("_sbb_niveau"))
    herkomst = (
        pl.when(pl.col("Niveau").is_not_null())
        .then(pl.lit(niveau.BRON))
        .when(pl.col("_crebo_niveau").is_not_null())
        .then(pl.lit(niveau.CREBO))
        .when(sbb_niveau.is_not_null())
        .then(pl.lit(niveau.SBB))
        .when(sbb_zonder_niveau)
        .then(pl.lit(niveau.SBB_NVT))
        .otherwise(pl.lit(niveau.ONBEKEND))
    )
    # Een join op een expressie houdt de rechtersleutel _sbb_code apart (#145).
    return df.with_columns(
        pl.coalesce("Niveau", "_crebo_niveau", sbb_niveau).alias("Niveau"),
        herkomst.alias(niveau.KOLOM),
    ).drop("_crebo_niveau", "_sbb_niveau", "_sbb_code", strict=False)
