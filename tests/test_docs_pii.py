"""De gedocumenteerde PII-patronen zijn precies die uit ``pii.py`` (#179).

Downloads en previews verbergen kolommen op basis van deze patronen; wie de
docs leest, moet dezelfde lijst zien als de code toepast.
"""

import re
from pathlib import Path

from mbo_bekostiging_bestanden.pii import _PII_PATTERNS

DOC = Path("docs/aan-de-slag.md")


def test_docs_noemen_precies_de_pii_patronen():
    tekst = DOC.read_text(encoding="utf-8")
    sectie = tekst[
        tekst.index("<!-- pii-patronen -->") : tekst.index("<!-- /pii-patronen -->")
    ]
    assert set(re.findall(r"`([^`]+)`", sectie)) == set(_PII_PATTERNS)
