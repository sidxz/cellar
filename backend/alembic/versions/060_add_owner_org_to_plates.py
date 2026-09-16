"""060 — owner_org_id on registered_plates (Duar org ownership)

Revision ID: 060_add_owner_org_to_plates
Revises: 059_protocol_fingerprint
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "060_add_owner_org_to_plates"
down_revision = "059_protocol_fingerprint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("registered_plates", sa.Column("owner_org_id", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_reg_plate_owner_org", "registered_plates", ["workspace_id", "owner_org_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_reg_plate_owner_org", table_name="registered_plates")
    op.drop_column("registered_plates", "owner_org_id")
