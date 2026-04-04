"""Create audit tables (append-only, 21 CFR Part 11).

Revision ID: 002
Revises: 001
Create Date: 2026-04-03
"""

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str = "001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # --- audit_operations ---
    op.create_table(
        "audit_operations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("operation_type", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False, server_default="user"),
        sa.Column(
            "correlation_id",
            sa.Uuid(),
            sa.ForeignKey("audit_operations.id"),
            nullable=True,
        ),
        sa.Column("entity_type", sa.String(128), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_audit_operations_entity",
        "audit_operations",
        ["entity_type", "entity_id"],
    )
    op.create_index(
        "ix_audit_operations_user_id",
        "audit_operations",
        ["user_id"],
    )
    op.create_index(
        "ix_audit_operations_correlation_id",
        "audit_operations",
        ["correlation_id"],
    )

    # --- audit_entries ---
    op.create_table(
        "audit_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "operation_id",
            sa.Uuid(),
            sa.ForeignKey("audit_operations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("entity_type", sa.String(128), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("field_name", sa.String(256), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_audit_entries_entity",
        "audit_entries",
        ["entity_type", "entity_id"],
    )

    # --- electronic_signatures ---
    op.create_table(
        "electronic_signatures",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "operation_id",
            sa.Uuid(),
            sa.ForeignKey("audit_operations.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("meaning", sa.Text(), nullable=False),
        sa.Column("auth_method", sa.String(32), nullable=False),
        sa.Column(
            "signed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # --- 21 CFR Part 11: prevent UPDATE/DELETE on audit tables ---
    # Triggers are more robust than REVOKE — they enforce immutability
    # regardless of the connecting user's ownership/privileges.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Modification of audit records is not permitted (21 CFR Part 11)';
        END;
        $$ LANGUAGE plpgsql
        """
    )

    for table in ("audit_operations", "audit_entries", "electronic_signatures"):
        op.execute(
            f"CREATE TRIGGER no_update_{table} "
            f"BEFORE UPDATE ON {table} FOR EACH ROW "
            f"EXECUTE FUNCTION prevent_audit_modification()"
        )
        op.execute(
            f"CREATE TRIGGER no_delete_{table} "
            f"BEFORE DELETE ON {table} FOR EACH ROW "
            f"EXECUTE FUNCTION prevent_audit_modification()"
        )


def downgrade() -> None:
    for table in ("electronic_signatures", "audit_entries", "audit_operations"):
        op.execute(f"DROP TRIGGER IF EXISTS no_update_{table} ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS no_delete_{table} ON {table}")

    op.execute("DROP FUNCTION IF EXISTS prevent_audit_modification()")

    op.drop_table("electronic_signatures")
    op.drop_table("audit_entries")
    op.drop_table("audit_operations")
