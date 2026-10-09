"""workspace protocol naming settings (code prefix/width, home organism)

Revision ID: 081_protocol_naming_settings
Revises: 080_campaign_collections
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "081_protocol_naming_settings"
down_revision: str | None = "080_campaign_collections"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace_settings",
        sa.Column("protocol_naming", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("workspace_settings", "protocol_naming")
