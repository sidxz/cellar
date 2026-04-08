"""Add cdd_vault_id and fix workspace_settings column types.

audit_reason_policy and formulation_number_scheme were incorrectly
typed as NOT NULL JSON (defaulting to {}). They are actually nullable
strings stored in JSON columns. custom_field_definitions is a list,
not a dict.

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

    # Allow NULL for fields that are actually optional strings
    op.alter_column("workspace_settings", "audit_reason_policy", nullable=True)
    op.alter_column("workspace_settings", "formulation_number_scheme", nullable=True)

    # Fix legacy {} values → NULL for string fields, {} → [] for list field
    op.execute("UPDATE workspace_settings SET audit_reason_policy = NULL WHERE audit_reason_policy::text = '{}'")
    op.execute("UPDATE workspace_settings SET formulation_number_scheme = NULL WHERE formulation_number_scheme::text = '{}'")
    op.execute("UPDATE workspace_settings SET custom_field_definitions = '[]'::json WHERE custom_field_definitions::text = '{}'")



def downgrade() -> None:
    op.alter_column("workspace_settings", "formulation_number_scheme", nullable=False, server_default=sa.text("'{}'::json"))
    op.alter_column("workspace_settings", "audit_reason_policy", nullable=False, server_default=sa.text("'{}'::json"))
    op.execute("UPDATE workspace_settings SET audit_reason_policy = '{}'::json WHERE audit_reason_policy IS NULL")
    op.execute("UPDATE workspace_settings SET formulation_number_scheme = '{}'::json WHERE formulation_number_scheme IS NULL")
    op.drop_column("workspace_settings", "cdd_vault_id")
