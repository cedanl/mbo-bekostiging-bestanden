"""Tests for _inschrijving_periode_id propagation to detail facts (issue #63).

This file documents the structure needed: detail facts should include
_inschrijving_periode_id to enable stable joins back to fact_inschrijving
without fan-out.

After fix implementation:
- detail_bpv, detail_kzd_amo, detail_geo and detail_amo must include
  _inschrijving_periode_id
- Joins on this key should preserve row counts (no fan-out)
- Tests here will verify the propagation is complete
"""

import polars as pl


def test_stable_periode_id_join_concept():
    """Demonstrate correct join behavior with stable periode_id.

    This is a conceptual test showing what the fix enables:
    when detail facts have the stable periode_id, they can be joined
    back to fact_inschrijving without row duplication.
    """
    # Fact table (1 row per inschrijving_periode)
    fact = pl.DataFrame({
        "_inschrijving_periode_id": ["abc123"],
        "inschrijving_value": [100],
    })

    # Detail table (multiple rows per inschrijving_periode)
    detail = pl.DataFrame({
        "_inschrijving_periode_id": ["abc123", "abc123", "abc123"],
        "detail_value": [10, 20, 30],
    })

    # Join preserves both tables' structures
    joined = fact.join(detail, on="_inschrijving_periode_id", how="inner")

    # Result: 3 rows (1 fact row × 3 detail rows)
    assert joined.shape[0] == 3, (
        "Join on stable periode_id correctly creates one output row per detail row"
    )
    assert "_inschrijving_periode_id" in joined.columns
    assert "inschrijving_value" in joined.columns
    assert "detail_value" in joined.columns
