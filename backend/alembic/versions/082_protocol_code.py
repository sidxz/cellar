"""protocol code: immutable citation handle shared by a protocol's versions

Revision ID: 082_protocol_code
Revises: 081_protocol_naming_settings
Create Date: 2026-10-08
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "082_protocol_code"
down_revision: str | None = "081_protocol_naming_settings"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("protocols", sa.Column("code", sa.String(20), nullable=True))
    # Lineage roots numbered in creation order per workspace; versions inherit the root's code.
    op.execute(
        """
        WITH RECURSIVE roots AS (
            SELECT id, row_number() OVER (PARTITION BY workspace_id ORDER BY created_at, id) AS n
            FROM protocols WHERE parent_protocol_id IS NULL
        ), tree AS (
            SELECT p.id, r.n FROM protocols p JOIN roots r ON r.id = p.id
            UNION ALL
            SELECT c.id, t.n FROM protocols c JOIN tree t ON c.parent_protocol_id = t.id
        )
        UPDATE protocols p SET code = 'PRT-' || lpad(t.n::text, 5, '0') FROM tree t WHERE t.id = p.id
        """
    )
    op.create_index(
        "uq_protocol_ws_code_version", "protocols", ["workspace_id", "code", "protocol_version"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_protocol_ws_code_version", table_name="protocols")
    op.drop_column("protocols", "code")
