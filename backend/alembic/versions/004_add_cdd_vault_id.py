"""Add cdd_vault_id to workspace_settings.

Revision ID: 004
Revises: 003
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workspace_settings", sa.Column("cdd_vault_id", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("workspace_settings", "cdd_vault_id")
