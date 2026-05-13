"""screen campaign

Creates the four Screen Campaign aggregate tables (campaign,
campaign_channel, campaign_result, campaign_measurement), the
supporting indexes, the deferred FK from
collections.derived_from_campaign_id -> campaign.id (ON DELETE SET NULL,
deferred from migration 026), and a defense-in-depth PG trigger
function that rejects writes to campaign_result / campaign_measurement
whenever the owning campaign is in 'closed' or 'superseded' status.

Revision ID: 027_screen_campaign
Revises: 026_collection_frozen
Create Date: 2026-05-10
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "027_screen_campaign"
down_revision: str | None = "026_collection_frozen"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # campaign (aggregate root)
    # ------------------------------------------------------------------
    op.create_table(
        "campaign",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("compound_source", postgresql.JSONB(), nullable=False),
        sa.Column(
            "publishes_collection",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "source_protocols",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("signature_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "supersedes_campaign_id", sa.Uuid(as_uuid=True), nullable=True
        ),
        sa.Column(
            "superseded_by_campaign_id", sa.Uuid(as_uuid=True), nullable=True
        ),
        sa.Column(
            "published_collection_id", sa.Uuid(as_uuid=True), nullable=True
        ),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_campaign_workspace_id", "campaign", ["workspace_id"])
    op.create_index(
        "ix_campaign_workspace_project",
        "campaign",
        ["workspace_id", "project_id"],
    )
    op.create_index(
        "ix_campaign_supersedes", "campaign", ["supersedes_campaign_id"]
    )

    # ------------------------------------------------------------------
    # campaign_channel (one per protocol x readout in the campaign)
    # ------------------------------------------------------------------
    op.create_table(
        "campaign_channel",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("campaign.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("protocol_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "readout_definition_id", sa.Uuid(as_uuid=True), nullable=False
        ),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("selection_rule", sa.String(32), nullable=False),
        sa.Column("qualifier_handling", sa.String(32), nullable=False),
        sa.Column("qc_filter", postgresql.JSONB(), nullable=True),
        sa.Column("hit_threshold", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_campaign_channel_campaign_id",
        "campaign_channel",
        ["campaign_id"],
    )

    # ------------------------------------------------------------------
    # campaign_result (one row per molecule in the campaign)
    # ------------------------------------------------------------------
    op.create_table(
        "campaign_result",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("campaign.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("molecule_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "representative_batch_id", sa.Uuid(as_uuid=True), nullable=True
        ),
        sa.Column(
            "decision",
            sa.String(32),
            nullable=False,
            server_default="deferred",
        ),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_campaign_result_campaign_id",
        "campaign_result",
        ["campaign_id"],
    )
    op.create_index(
        "uq_campaign_result_molecule",
        "campaign_result",
        ["campaign_id", "molecule_id"],
        unique=True,
    )

    # ------------------------------------------------------------------
    # campaign_measurement (one row per result x channel)
    # ------------------------------------------------------------------
    op.create_table(
        "campaign_measurement",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "result_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("campaign_result.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channel_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("campaign_channel.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("value_qualifier", sa.String(16), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("hit_call", sa.String(16), nullable=True),
        sa.Column(
            "is_manual_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("source_run_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("source_curve_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("source_readout_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "protocol_name_snapshot", sa.String(255), nullable=False
        ),
        sa.Column(
            "protocol_version_snapshot", sa.Integer(), nullable=False
        ),
        sa.Column("run_date_snapshot", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_campaign_measurement_result_id",
        "campaign_measurement",
        ["result_id"],
    )
    op.create_index(
        "uq_campaign_measurement_result_channel",
        "campaign_measurement",
        ["result_id", "channel_id"],
        unique=True,
    )
    op.create_index(
        "ix_campaign_measurement_source_run",
        "campaign_measurement",
        ["source_run_id"],
    )

    # ------------------------------------------------------------------
    # Resolve the deferred FK from collections.derived_from_campaign_id
    # (added in migration 026 without a constraint).
    # ------------------------------------------------------------------
    op.create_foreign_key(
        "fk_collections_derived_from_campaign",
        "collections",
        "campaign",
        ["derived_from_campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ------------------------------------------------------------------
    # Defense-in-depth PG trigger: block writes to campaign_result /
    # campaign_measurement when the owning campaign is closed or
    # superseded. The domain layer enforces this too, but the trigger
    # is a last-line guarantee at the database boundary.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_locked_campaign_write() RETURNS trigger AS $$
        DECLARE
            cstat text;
        BEGIN
            IF TG_TABLE_NAME = 'campaign_result' THEN
                SELECT status INTO cstat
                  FROM campaign
                 WHERE id = COALESCE(NEW.campaign_id, OLD.campaign_id);
            ELSIF TG_TABLE_NAME = 'campaign_measurement' THEN
                SELECT c.status INTO cstat
                  FROM campaign_result r
                  JOIN campaign c ON c.id = r.campaign_id
                 WHERE r.id = COALESCE(NEW.result_id, OLD.result_id);
            END IF;
            IF cstat IN ('closed', 'superseded') THEN
                RAISE EXCEPTION 'Campaign is %, writes blocked', cstat USING ERRCODE = 'check_violation';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for tbl in ("campaign_result", "campaign_measurement"):
        op.execute(
            f"""
            CREATE TRIGGER {tbl}_reject_locked
            BEFORE INSERT OR UPDATE OR DELETE ON {tbl}
            FOR EACH ROW EXECUTE FUNCTION reject_locked_campaign_write();
            """
        )


def downgrade() -> None:
    # Triggers first (they depend on the function + tables).
    for tbl in ("campaign_measurement", "campaign_result"):
        op.execute(f"DROP TRIGGER IF EXISTS {tbl}_reject_locked ON {tbl};")
    op.execute("DROP FUNCTION IF EXISTS reject_locked_campaign_write();")

    # Drop the deferred FK on collections so the campaign table can be
    # dropped without dependency errors.
    op.drop_constraint(
        "fk_collections_derived_from_campaign",
        "collections",
        type_="foreignkey",
    )

    # Tables in reverse dependency order (indexes drop automatically).
    op.drop_table("campaign_measurement")
    op.drop_table("campaign_result")
    op.drop_table("campaign_channel")
    op.drop_table("campaign")
