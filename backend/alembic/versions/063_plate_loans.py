"""063 — plate_loans + plate_loan_items tables

PlateLoan aggregate: the borrow/checkout workflow for registered plates.
``plate_loans`` is the aggregate root; ``plate_loan_items`` are owned children
(one row per plate in the loan), CASCADE-deleted with their parent.

``plate_loan_items.plate_id`` deliberately has NO foreign key — loans
reference plates loosely (like the legacy system) so a loan's history
survives deletion of the plate it once referenced.

The partial unique index enforces "one active loan per plate" at the DB
level, backstopping the use-case-level pre-check: a plate can appear in at
most one loan item whose status is in the four "active" statuses at a time.

Revision ID: 063_plate_loans
Revises: 062_plate_groups
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "063_plate_loans"
down_revision = "062_plate_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plate_loans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("owner_org_id", sa.Uuid(), nullable=False),
        sa.Column("borrower_org_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plate_loans_ws_status", "plate_loans", ["workspace_id", "status"])
    op.create_index("ix_plate_loans_owner_org", "plate_loans", ["owner_org_id"])
    op.create_index("ix_plate_loans_borrower_org", "plate_loans", ["borrower_org_id"])

    op.create_table(
        "plate_loan_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("loan_id", sa.Uuid(), nullable=False),
        sa.Column("plate_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["loan_id"], ["plate_loans.id"], name="fk_loan_items_loan", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_loan_items_loan", "plate_loan_items", ["loan_id"])
    op.create_index("ix_loan_items_plate", "plate_loan_items", ["plate_id"])
    # Partial UNIQUE index — raw SQL (049/062 precedent; op.create_index can't
    # express unique+where reliably across this repo's conventions).
    op.execute(
        """
        CREATE UNIQUE INDEX uq_loan_items_active_plate ON plate_loan_items (plate_id)
            WHERE status IN ('requested', 'approved', 'checked_out', 'return_pending');
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_loan_items_active_plate")
    op.drop_index("ix_loan_items_plate", table_name="plate_loan_items")
    op.drop_index("ix_loan_items_loan", table_name="plate_loan_items")
    op.drop_table("plate_loan_items")
    op.drop_index("ix_plate_loans_borrower_org", table_name="plate_loans")
    op.drop_index("ix_plate_loans_owner_org", table_name="plate_loans")
    op.drop_index("ix_plate_loans_ws_status", table_name="plate_loans")
    op.drop_table("plate_loans")
