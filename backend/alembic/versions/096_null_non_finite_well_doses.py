"""null non-finite well doses: clear NaN and infinite doses stored by the older importer

A well's dose must be a finite number (the Well entity refuses anything else,
also when a run is loaded). The plate importer used to store "nan" and "inf"
cells as they were, which would make such a run impossible to open.

Revision ID: 096_null_non_finite_well_doses
Revises: 095_measured_curve_x_label
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "096_null_non_finite_well_doses"
down_revision: str | None = "095_measured_curve_x_label"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE wells SET dose = NULL WHERE dose IN ('NaN', 'Infinity', '-Infinity')")


def downgrade() -> None:
    # Nothing to do: the cleared values were not doses and cannot be restored.
    pass
