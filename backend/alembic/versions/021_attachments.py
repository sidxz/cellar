"""Create attachments table.

Revision ID: 021
Revises: 020
"""

from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("attachable_type", sa.String(50), nullable=False),
        sa.Column("attachable_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
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
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("file_size > 0", name="ck_attachments_file_size_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attachments_entity", "attachments", ["attachable_type", "attachable_id"])
    op.create_index("ix_attachments_workspace_id", "attachments", ["workspace_id"])
    op.create_unique_constraint(
        "uq_attachment_entity_filename",
        "attachments",
        ["workspace_id", "attachable_type", "attachable_id", "file_name"],
    )


def downgrade() -> None:
    op.drop_table("attachments")
