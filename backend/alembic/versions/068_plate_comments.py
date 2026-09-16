"""068 — plate_comments (spec 2026-08-25 §7)

Append-only comments on plate loans / groups / plates. target_id has no FK
(polymorphic); loan_id is a context link that survives loan deletion as NULL.

Revision ID: 068_plate_comments
Revises: 067_plate_group_metadata
"""

import sqlalchemy as sa
from alembic import op

revision = "068_plate_comments"
down_revision = "067_plate_group_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plate_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("loan_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("author_name", sa.String(200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["loan_id"], ["plate_loans.id"], name="fk_plate_comments_loan", ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_plate_comments_ws_target",
        "plate_comments",
        ["workspace_id", "target_type", "target_id", "created_at"],
    )
    op.create_index("ix_plate_comments_ws_loan", "plate_comments", ["workspace_id", "loan_id"])


def downgrade() -> None:
    op.drop_index("ix_plate_comments_ws_loan", table_name="plate_comments")
    op.drop_index("ix_plate_comments_ws_target", table_name="plate_comments")
    op.drop_table("plate_comments")
