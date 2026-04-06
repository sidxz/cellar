"""registered_plates + import_templates tables, plates.registered_plate_id FK

Revision ID: 020
Revises: 019
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registered_plates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("barcode", sa.String(100), nullable=False),
        sa.Column("plate_label", sa.String(300), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("plate_type", sa.String(30), nullable=False),
        sa.Column("well_map", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="registered"),
        sa.Column("storage_location_id", sa.Uuid(), sa.ForeignKey("storage_locations.id"), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("template_id", sa.Uuid(), nullable=True),
        sa.Column("parent_plate_id", sa.Uuid(), sa.ForeignKey("registered_plates.id"), nullable=True),
        sa.Column("registered_by", sa.Uuid(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "barcode", name="uq_reg_plate_ws_barcode"),
    )
    op.create_index("ix_reg_plate_status", "registered_plates", ["workspace_id", "status"])
    op.create_index("ix_reg_plate_type", "registered_plates", ["workspace_id", "plate_type"])
    op.create_index("ix_reg_plate_location", "registered_plates", ["storage_location_id"])
    op.create_index("ix_reg_plate_project", "registered_plates", ["project_id"])
    op.create_index("ix_reg_plate_parent", "registered_plates", ["parent_plate_id"])

    op.create_table(
        "import_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("column_mappings", postgresql.JSONB(), nullable=False),
        sa.Column("default_protocol_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_template_ws", "import_templates", ["workspace_id"])

    # Add registered_plate_id FK to existing screening plates table
    op.add_column(
        "plates",
        sa.Column("registered_plate_id", sa.Uuid(), sa.ForeignKey("registered_plates.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plates", "registered_plate_id")
    op.drop_table("import_templates")
    op.drop_table("registered_plates")
