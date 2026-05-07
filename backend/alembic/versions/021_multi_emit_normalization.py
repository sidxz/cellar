"""Multi-emit normalization: JSONB array on readout_definitions, normalization_applied on readout_data.

CDD parity: one ReadoutDefinition can emit several normalized columns at
once (raw + %inh + z-score). The single-value ``normalization`` column
becomes a JSONB array ``normalizations``; existing rows are backfilled
(``"none"`` -> ``[]``, otherwise ``[value]``). ReadoutData gets a new
``normalization_applied`` column tagging which formula produced each
computed row (NULL for raw rows).

Revision ID: 021
Revises: 020
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "021"
down_revision = "020"


def upgrade() -> None:
    # 1. Add the new JSONB column on readout_definitions, default empty array.
    op.add_column(
        "readout_definitions",
        sa.Column(
            "normalizations",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # 2. Backfill from the old single-value column.
    op.execute(
        """
        UPDATE readout_definitions
        SET normalizations = CASE
            WHEN normalization = 'none' OR normalization IS NULL THEN '[]'::jsonb
            ELSE jsonb_build_array(normalization)
        END
        """
    )

    # 3. Drop the old column.
    op.drop_column("readout_definitions", "normalization")

    # 4. New tagging column on readout_data.
    op.add_column(
        "readout_data",
        sa.Column("normalization_applied", sa.String(40), nullable=True),
    )

    # 5. Backfill existing computed rows with their def's first formula.
    #    Raw rows (is_computed=false) stay NULL.
    op.execute(
        """
        UPDATE readout_data rd
        SET normalization_applied = (
            SELECT def.normalizations->>0
            FROM readout_definitions def
            WHERE def.id = rd.readout_definition_id
        )
        WHERE rd.is_computed = TRUE
          AND rd.normalization_applied IS NULL
        """
    )


def downgrade() -> None:
    op.add_column(
        "readout_definitions",
        sa.Column(
            "normalization",
            sa.String(30),
            nullable=False,
            server_default="none",
        ),
    )
    op.execute(
        """
        UPDATE readout_definitions
        SET normalization = COALESCE(normalizations->>0, 'none')
        """
    )
    op.drop_column("readout_definitions", "normalizations")
    op.drop_column("readout_data", "normalization_applied")
