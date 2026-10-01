"""Herkomst van de kolom ``Niveau`` in fact_inschrijving (#130).

Niveau valt terug in volgorde bron → CREBO → S-BB; ``KOLOM`` draagt die
herkomst per rij. Losstaand van ``opleidingsniveau.py`` (dat de kolom vult) zodat
``quality.py`` de ster onafhankelijk kan lezen zonder de transformatielaag
te importeren (#253).
"""

KOLOM = "_niveau_herkomst"
BRON = "bron"
CREBO = "crebo"
SBB = "sbb"
SBB_NVT = "sbb_nvt"  # S-BB kent de code, maar zonder niveau
ONBEKEND = "onbekend"
