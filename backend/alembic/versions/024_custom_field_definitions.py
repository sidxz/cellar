"""024 — Custom field definitions table.

Revision ID: 024
Revises: 023
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_field_definitions",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("data_type", sa.String(20), nullable=False),
        sa.Column("applies_to", sa.String(20), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_value", sa.JSON(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pick_list_values", sa.JSON(), nullable=True),
        sa.Column("vocabulary_id", UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["vocabulary_id"],
            ["controlled_vocabularies.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "workspace_id", "name", "applies_to", name="uq_cfd_ws_name_target"
        ),
    )
    op.create_index(
        "ix_custom_field_definitions_workspace",
        "custom_field_definitions",
        ["workspace_id"],
    )

    op.create_table(
        "salt_catalog",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("smiles", sa.String(500), nullable=False),
        sa.Column("molecular_weight", sa.Float(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "code", name="uq_salt_ws_code"),
    )
    op.create_index(
        "ix_salt_catalog_workspace",
        "salt_catalog",
        ["workspace_id"],
    )

    # Batch salt field restructuring
    op.alter_column("batches", "salt_form", new_column_name="salt_name", type_=sa.String(200))
    op.add_column("batches", sa.Column("salt_entry_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_batch_salt_entry", "batches", "salt_catalog", ["salt_entry_id"], ["id"], ondelete="SET NULL")
    op.add_column("batches", sa.Column("salt_smiles", sa.String(500), nullable=True))
    op.add_column("batches", sa.Column("salt_stoichiometry", sa.Integer, nullable=False, server_default="1"))
    op.add_column("batches", sa.Column("formula_weight", sa.Float, nullable=True))


def downgrade() -> None:
    # Reverse batch salt field restructuring
    op.drop_column("batches", "formula_weight")
    op.drop_column("batches", "salt_stoichiometry")
    op.drop_column("batches", "salt_smiles")
    op.drop_constraint("fk_batch_salt_entry", "batches", type_="foreignkey")
    op.drop_column("batches", "salt_entry_id")
    op.alter_column("batches", "salt_name", new_column_name="salt_form", type_=sa.String(100))

    op.drop_index("ix_salt_catalog_workspace", table_name="salt_catalog")
    op.drop_table("salt_catalog")
    op.drop_index(
        "ix_custom_field_definitions_workspace", table_name="custom_field_definitions"
    )
    op.drop_table("custom_field_definitions")
