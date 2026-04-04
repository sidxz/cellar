"""Disclosure and merge tables — bulk_disclosures, disclosure_requests, merge_events.

Revision ID: 006
Revises: 005
Create Date: 2026-04-04
"""

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str = "005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Bulk disclosures (created first — disclosure_requests references it)
    op.create_table(
        "bulk_disclosures",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_file", sa.String(500), nullable=False),
        sa.Column("partner_org_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("disclosed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("merged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # Standard columns
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Disclosure requests
    op.create_table(
        "disclosure_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "bulk_disclosure_id",
            sa.Uuid(),
            sa.ForeignKey("bulk_disclosures.id"),
            nullable=True,
        ),
        sa.Column(
            "molecule_id",
            sa.Uuid(),
            sa.ForeignKey("molecules.id"),
            nullable=False,
        ),
        sa.Column("disclosed_smiles", sa.Text(), nullable=False),
        sa.Column("canonical_smiles", sa.Text(), nullable=True),
        sa.Column("inchi_key", sa.String(27), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("resolution_type", sa.String(30), nullable=True),
        sa.Column("resolved_to_molecule_id", sa.Uuid(), nullable=True),
        sa.Column("disclosing_org_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conflict_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        # Standard columns
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_disclosure_requests_molecule_id", "disclosure_requests", ["molecule_id"]
    )
    op.create_index(
        "ix_disclosure_requests_bulk_id", "disclosure_requests", ["bulk_disclosure_id"]
    )

    # Merge events (insert-only, no version column)
    op.create_table(
        "merge_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_molecule_id",
            sa.Uuid(),
            sa.ForeignKey("molecules.id"),
            nullable=False,
        ),
        sa.Column(
            "target_molecule_id",
            sa.Uuid(),
            sa.ForeignKey("molecules.id"),
            nullable=False,
        ),
        sa.Column(
            "disclosure_request_id",
            sa.Uuid(),
            sa.ForeignKey("disclosure_requests.id"),
            nullable=True,
        ),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("merged_by", sa.Uuid(), nullable=False),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        # Standard columns (no version — insert-only)
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_merge_events_source", "merge_events", ["source_molecule_id"])
    op.create_index("ix_merge_events_target", "merge_events", ["target_molecule_id"])


def downgrade() -> None:
    op.drop_table("merge_events")
    op.drop_table("disclosure_requests")
    op.drop_table("bulk_disclosures")
