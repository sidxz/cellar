"""Move concentration unit ownership to Protocol; rename well concentration_value -> dose.

Single source of truth: each protocol declares its dose unit. Wells store
just the dose value. Curves drop fitted_unit (always equals protocol unit).

Revision ID: 017
Revises: 016
"""

import sqlalchemy as sa
from alembic import op

revision = "017"
down_revision = "016"


def upgrade() -> None:
    # 1. Add Protocol.dose_unit (default uM for all existing protocols).
    op.add_column(
        "protocols",
        sa.Column(
            "dose_unit",
            sa.String(10),
            nullable=False,
            server_default="uM",
        ),
    )

    # 2. Wells: rename concentration_value -> dose, drop concentration_unit.
    op.alter_column("wells", "concentration_value", new_column_name="dose")
    op.drop_column("wells", "concentration_unit")

    # 3. Curves: drop fitted_unit (derived from protocol.dose_unit at read time).
    op.drop_column("dose_response_curves", "fitted_unit")

    # 4. RunImportTemplate: drop concentration_unit (now lives on protocol).
    op.drop_column("run_import_templates", "concentration_unit")


def downgrade() -> None:
    op.add_column(
        "run_import_templates",
        sa.Column(
            "concentration_unit",
            sa.String(20),
            nullable=False,
            server_default="uM",
        ),
    )

    op.add_column(
        "dose_response_curves",
        sa.Column(
            "fitted_unit", sa.String(20), nullable=False, server_default="uM"
        ),
    )

    op.add_column(
        "wells",
        sa.Column("concentration_unit", sa.String(20), nullable=True),
    )
    op.alter_column("wells", "dose", new_column_name="concentration_value")

    op.drop_column("protocols", "dose_unit")
