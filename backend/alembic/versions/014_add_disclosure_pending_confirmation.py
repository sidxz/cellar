"""Add pending_confirmation support to disclosure_requests.

- Widen status column from String(20) to String(30)
- Add matched_molecule_id column (FK to molecules)
- Add scientist_name column for disclosure provenance

Revision ID: 014
Revises: 013
"""

import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"


def upgrade() -> None:
    op.alter_column(
        "disclosure_requests",
        "status",
        type_=sa.String(30),
        existing_type=sa.String(20),
        existing_nullable=False,
        existing_server_default="pending",
    )
    op.add_column(
        "disclosure_requests",
        sa.Column("matched_molecule_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "disclosure_requests",
        sa.Column("scientist_name", sa.String(200), nullable=True),
    )
    op.create_foreign_key(
        "fk_disclosure_requests_matched_molecule",
        "disclosure_requests",
        "molecules",
        ["matched_molecule_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_disclosure_requests_matched_molecule",
        "disclosure_requests",
        type_="foreignkey",
    )
    op.drop_column("disclosure_requests", "scientist_name")
    op.drop_column("disclosure_requests", "matched_molecule_id")
    op.alter_column(
        "disclosure_requests",
        "status",
        type_=sa.String(20),
        existing_type=sa.String(30),
        existing_nullable=False,
        existing_server_default="pending",
    )
