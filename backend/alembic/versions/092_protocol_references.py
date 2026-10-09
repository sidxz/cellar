"""protocols carry typed references (ChEMBL assay, PubChem AID, DOI, PMID, URL)

Revision ID: 092_protocol_references
Revises: 091_condition_fixed_value
Create Date: 2026-10-08

A JSONB list of {kind, value}, not null with default []. Existing protocols (locked ones
included) get the empty list from the default; no row is rewritten beyond that.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "092_protocol_references"
down_revision: str | None = "091_condition_fixed_value"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "protocols",
        sa.Column(
            "references",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("protocols", "references")
