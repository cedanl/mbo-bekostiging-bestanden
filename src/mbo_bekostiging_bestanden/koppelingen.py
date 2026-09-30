"""Links-joins met een vastgelegde regel bij meervoudige matches (#209, #239).

Heeft een sleutel rechts meer dan één kandidaat, dan moet de pipeline er één
kiezen. Welke, staat per koppeling in ``KOPPELREGELS``, nooit in de rijvolgorde
van een bestand:

- ``uniek``: het PvE staat hoogstens één kandidaat toe; een tweede is een
  bronfout (error in ``quality.json``). De keuze valt dan op inhoud.
- ``hoogste``: de hoogste waarde in ``voorkeur`` wint (bijv. het recentste
  diploma), daarna de overige kolommen.
- ``ambigu``: er is geen businessregel; de keuze valt deterministisch op inhoud
  (warning).

Per koppeling worden regel, reden en aantal keuzes bijgehouden; dat overzicht
belandt als ``meta_koppelkeuzes`` in de ster en als ``join_keuzes`` in
``quality.json``.
"""

from dataclasses import dataclass

import polars as pl

UNIEK, HOOGSTE, AMBIGU = "uniek", "hoogste", "ambigu"

OVERZICHT_KOLOMMEN = pl.Schema(
    {
        "koppeling": pl.Utf8,
        "sleutel": pl.Utf8,
        "regel": pl.Utf8,
        "toelichting": pl.Utf8,
        "meervoudige_sleutels": pl.UInt32,
        "weggelaten_rijen": pl.UInt32,
    }
)


@dataclass(frozen=True)
class Koppelregel:
    """Welke kandidaat wint bij meer dan één match, en waarom."""

    soort: str
    toelichting: str
    voorkeur: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.soort not in (UNIEK, HOOGSTE, AMBIGU):
            raise ValueError(f"Onbekende soort koppelregel: {self.soort!r}")
        if self.soort == HOOGSTE and not self.voorkeur:
            raise ValueError("Een regel 'hoogste' heeft een voorkeur-kolom nodig")


_PVE_UNIEK_INSCHRIJVING = (
    "Inschrijvingvolgnummer is uniek per persoon binnen één instelling (PvE §16.5.1)"
)

# Koppeling (naam in meta_koppelkeuzes) → regel. Een koppeling zonder regel
# faalt in :meth:`Koppelingen.links`.
KOPPELREGELS: dict[str, Koppelregel] = {
    "PER": Koppelregel(
        UNIEK, "één PER-record opent alle records van een persoon (PvE §15.4)"
    ),
    "ISG": Koppelregel(UNIEK, _PVE_UNIEK_INSCHRIJVING),
    "VLP": Koppelregel(UNIEK, "één voorlooprecord per levering (PvE §15.4)"),
    "ISE": Koppelregel(
        AMBIGU,
        "het PvE staat meerdere ISE-perioden per inschrijving toe; de periode-grain "
        "heeft er één kolomset voor",
    ),
    "DIP": Koppelregel(
        HOOGSTE,
        "meerdere diploma's op één inschrijving: het recentste telt",
        voorkeur=("DIP_DatumResultaat",),
    ),
    "GEO": Koppelregel(UNIEK, "de GEO-pivot heeft één rij per inschrijving"),
    "BID.DIP": Koppelregel(
        HOOGSTE,
        "Resultaatvolgnummer is uniek per persoon binnen één instelling; bij een "
        "bronfout telt het recentste diploma",
        voorkeur=("DatumBehaald",),
    ),
    "meta_leveringen.VLP": Koppelregel(UNIEK, "één voorlooprecord per levering"),
    "meta_leveringen.SLR": Koppelregel(UNIEK, "één sluitrecord per levering"),
}


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
        suffix: str = "_r",
        regel: Koppelregel | None = None,
    ) -> pl.DataFrame:
        """LEFT JOIN op ``on`` met hoogstens één rij uit ``right`` per sleutel.

        Args:
            naam:  Koppeling in ``KOPPELREGELS``; die bepaalt de keuze.
            regel: Alleen voor tests: een regel buiten het register.

        Raises:
            KeyError: ``naam`` heeft geen regel.
        """
        if regel is None:
            if naam not in KOPPELREGELS:
                raise KeyError(f"Koppeling {naam!r} heeft geen regel in KOPPELREGELS")
            regel = KOPPELREGELS[naam]
        kandidaten = right.join(left.select(on).unique(), on=on, how="semi")
        per_sleutel = kandidaten.group_by(on).len()
        meervoudig = per_sleutel.filter(pl.col("len") > 1)
        self._rijen.append(
            {
                "koppeling": naam,
                "sleutel": ", ".join(on),
                "regel": regel.soort,
                "toelichting": regel.toelichting,
                "meervoudige_sleutels": meervoudig.height,
                "weggelaten_rijen": int(meervoudig["len"].sum()) - meervoudig.height,
            }
        )
        return left.join(
            _een_per_sleutel(right, on, list(regel.voorkeur)),
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
