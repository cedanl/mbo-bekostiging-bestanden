"""Links-joins met een vastgelegde keuze bij meervoudige matches (#209).

Heeft een sleutel rechts meer dan één kandidaat, dan moet de pipeline er één
kiezen. Die keuze hangt nooit af van de rijvolgorde in een bestand: eerst de
inhoudelijke ``voorkeur`` (hoogste waarde wint), daarna de overige kolommen.
Per koppeling wordt geteld hoe vaak er gekozen is; dat overzicht belandt als
``meta_koppelkeuzes`` in de ster en als ``join_keuzes`` in ``quality.json``.
"""

import polars as pl

OVERZICHT_KOLOMMEN = pl.Schema(
    {
        "koppeling": pl.Utf8,
        "sleutel": pl.Utf8,
        "meervoudige_sleutels": pl.UInt32,
        "weggelaten_rijen": pl.UInt32,
    }
)


class Koppelingen:
    """Voert links-joins uit en houdt per koppeling de gemaakte keuzes bij."""

    def __init__(self) -> None:
        self._rijen: list[dict] = []

    def links(
        self,
        left: pl.DataFrame,
        right: pl.DataFrame,
        on: list[str],
        naam: str,
        voorkeur: list[str] | None = None,
        suffix: str = "_r",
    ) -> pl.DataFrame:
        """LEFT JOIN op ``on`` met hoogstens één rij uit ``right`` per sleutel.

        Args:
            voorkeur: Kolommen in ``right``; bij meerdere kandidaten wint de
                      hoogste waarde (nulls achteraan).
        """
        kandidaten = right.join(left.select(on).unique(), on=on, how="semi")
        per_sleutel = kandidaten.group_by(on).len()
        meervoudig = per_sleutel.filter(pl.col("len") > 1)
        self._rijen.append(
            {
                "koppeling": naam,
                "sleutel": ", ".join(on),
                "meervoudige_sleutels": meervoudig.height,
                "weggelaten_rijen": int(meervoudig["len"].sum()) - meervoudig.height,
            }
        )
        return left.join(
            _een_per_sleutel(right, on, voorkeur or []),
            on=on,
            how="left",
            suffix=suffix,
        )

    def overzicht(self) -> pl.DataFrame:
        return pl.DataFrame(self._rijen, schema=OVERZICHT_KOLOMMEN)


def _een_per_sleutel(
    right: pl.DataFrame, on: list[str], voorkeur: list[str]
) -> pl.DataFrame:
    rest = [c for c in right.columns if c not in (*on, *voorkeur)]
    volgorde = [*voorkeur, *rest]
    if not volgorde:
        return right.unique(subset=on)
    geordend = right.sort(
        volgorde,
        descending=[True] * len(voorkeur) + [False] * len(rest),
        nulls_last=True,
    )
    return geordend.unique(subset=on, keep="first", maintain_order=True)
