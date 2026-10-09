"""campaign measurement protocol name snapshot: 400 characters, like protocol names

Revision ID: 087_campaign_name_snapshot_width
Revises: 086_protocol_name_fields
Create Date: 2026-10-08
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "087_campaign_name_snapshot_width"
down_revision: str | None = "086_protocol_name_fields"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "campaign_measurement",
        "protocol_name_snapshot",
        type_=sa.String(400),
        existing_type=sa.String(255),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "campaign_measurement",
        "protocol_name_snapshot",
        type_=sa.String(255),
        existing_type=sa.String(400),
        existing_nullable=False,
    )
