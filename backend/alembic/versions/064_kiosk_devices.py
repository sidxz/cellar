"""064 — kiosk_devices table (spec §4.5)

KioskDevice aggregate: an org-bound scan-station credential for the kiosk
scan/confirm endpoints (S5). The plaintext token exists only at issuance
time (application layer); this table stores its sha256 hexdigest only.

``token_hash`` lookup is deliberately workspace-unscoped — the token IS the
identity — so its unique constraint doubles as the lookup index. No
standalone ``workspace_id`` index is created: ``ix_kiosk_devices_ws_org``
already covers workspace-only lookups via leftmost-column prefix (same
rationale as 063's ``ix_plate_loans_ws_status``).

Revision ID: 064_kiosk_devices
Revises: 063_plate_loans
"""

import sqlalchemy as sa
from alembic import op

revision = "064_kiosk_devices"
down_revision = "063_plate_loans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kiosk_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_kiosk_devices_ws_name"),
        sa.UniqueConstraint("token_hash", name="uq_kiosk_devices_token_hash"),
    )
    op.create_index("ix_kiosk_devices_ws_org", "kiosk_devices", ["workspace_id", "org_id"])


def downgrade() -> None:
    op.drop_index("ix_kiosk_devices_ws_org", table_name="kiosk_devices")
    op.drop_table("kiosk_devices")
