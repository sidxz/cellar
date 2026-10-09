"""canonical units again (later spelling rules) and inside saved searches

Revision ID: 090_canonical_units_again
Revises: 089_protocol_form_category
Create Date: 2026-10-08

Re-runs 088's rewrite, which is idempotent, so databases already past 088 pick up the rules
added since: dotted abbreviations and a lone "um" stay as typed; a power-of-ten factor with
an explicit marker (10^-6, 1e-6, x10-6) becomes ×10⁻⁶, while a bare 10-6 stays. Then
rewrites the units inside saved searches' any-protocol readout criteria: saved searches are
live queries, and their units must match the stored readouts' spelling.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from cellar.infrastructure.persistence.unit_rewrite import (
    rewrite_saved_search_units,
    rewrite_stored_units,
)

revision: str = "090_canonical_units_again"
down_revision: str | None = "089_protocol_form_category"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    rewrite_stored_units(conn)
    rewrite_saved_search_units(conn)


def downgrade() -> None:
    # Spelling only; the old variants carry nothing worth restoring.
    pass
