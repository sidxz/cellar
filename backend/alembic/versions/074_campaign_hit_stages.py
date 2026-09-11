"""campaign hit stages

Adds two owned-child tables under the Campaign aggregate:

  * campaign_stage — a named AND-combination of numeric rules over the
    campaign's channels (zero-criteria "scaffold" stages are valid). Stages
    form a forest via parent_stage_id.
  * campaign_stage_override — a per-(result, stage) manual hit/miss
    override with an audited reason, owned by campaign_result.

Backfills one campaign_stage per existing campaign_channel.hit_threshold
(skipping the string-based "in" operator, which StageCriterion — unlike
HitCriterion — does not support; those channels get no stage and are
triaged manually going forward). Stage name is "<channel label> hits";
case-insensitive name collisions within a campaign are suffixed " (2)",
" (3)", ... in the order the channel rows are read.

Extends the migration-027 reject_locked_campaign_write() trigger function
with two more branches (same defense-in-depth as campaign_result /
campaign_measurement) and attaches it to both new tables. The backfill
INSERT runs before the trigger exists on campaign_stage, so channels
belonging to closed/superseded campaigns backfill too.

Also adds campaign.close_note (Text, nullable), recorded by CloseCampaign
and cleared by ReopenCampaign.

Revision ID: 074_campaign_hit_stages
Revises: 073_molecules_inchi_key_unique
Create Date: 2026-09-11
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "074_campaign_hit_stages"
down_revision: str | None = "073_molecules_inchi_key_unique"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def build_stage_rows(channel_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure function: one campaign_stage row per channel with a usable hit_threshold.

    ``channel_rows`` — dicts with ``id``, ``campaign_id``, ``label``,
    ``display_order``, ``hit_threshold`` (a HitCriterion-shaped dict, or
    None). Rows with no threshold, or whose operator is the string-based
    "in" (not representable as a StageCriterion), are skipped.

    Returned rows are shaped for ``campaign_stage``: ``id`` (new uuid4),
    ``campaign_id``, ``name`` (``"<label> hits"``, deduplicated
    case-insensitively per campaign with " (2)", " (3)", ... suffixes in
    input order), ``parent_stage_id`` (always None), ``display_order``
    (copied from the channel), and ``criteria`` (a single-element list of a
    StageCriterion dict: ``channel_id`` as a string, ``operator``, ``value``).
    """
    seen_names: dict[Any, dict[str, int]] = {}
    stage_rows: list[dict[str, Any]] = []
    for row in channel_rows:
        threshold = row["hit_threshold"]
        if not threshold or threshold.get("operator") == "in":
            continue
        campaign_id = row["campaign_id"]
        base_name = f"{row['label']} hits"
        dedup_key = base_name.casefold()
        counts = seen_names.setdefault(campaign_id, {})
        occurrence = counts.get(dedup_key, 0) + 1
        counts[dedup_key] = occurrence
        name = base_name if occurrence == 1 else f"{base_name} ({occurrence})"
        stage_rows.append(
            {
                "id": uuid.uuid4(),
                "campaign_id": campaign_id,
                "name": name,
                "parent_stage_id": None,
                "display_order": row["display_order"],
                "criteria": [
                    {
                        "channel_id": str(row["id"]),
                        "operator": threshold["operator"],
                        "value": threshold["value"],
                    }
                ],
            }
        )
    return stage_rows


def upgrade() -> None:
    # ------------------------------------------------------------------
    # campaign_stage
    # ------------------------------------------------------------------
    op.create_table(
        "campaign_stage",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("campaign.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "parent_stage_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("campaign_stage.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "criteria",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
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
    op.create_index("ix_campaign_stage_campaign_id", "campaign_stage", ["campaign_id"])
    op.create_index(
        "uq_campaign_stage_name",
        "campaign_stage",
        ["campaign_id", sa.text("lower(name)")],
        unique=True,
    )

    # ------------------------------------------------------------------
    # campaign_stage_override
    # ------------------------------------------------------------------
    op.create_table(
        "campaign_stage_override",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "result_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("campaign_result.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stage_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("campaign_stage.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("forced_outcome", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("overridden_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=False),
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
        "ix_campaign_stage_override_result_id", "campaign_stage_override", ["result_id"]
    )
    op.create_index(
        "uq_campaign_stage_override_result_stage",
        "campaign_stage_override",
        ["result_id", "stage_id"],
        unique=True,
    )

    # ------------------------------------------------------------------
    # Backfill one stage per existing hit_threshold — runs before the
    # reject-locked trigger is attached to campaign_stage below, so
    # channels on closed/superseded campaigns backfill too.
    # ------------------------------------------------------------------
    conn = op.get_bind()
    channel_rows = [
        dict(row)
        for row in conn.execute(
            sa.text(
                "SELECT id, campaign_id, label, display_order, hit_threshold "
                "FROM campaign_channel WHERE hit_threshold IS NOT NULL"
            )
        ).mappings()
    ]
    stage_rows = build_stage_rows(channel_rows)
    if stage_rows:
        conn.execute(
            sa.text(
                "INSERT INTO campaign_stage "
                "(id, campaign_id, name, parent_stage_id, display_order, criteria) "
                "VALUES (:id, :campaign_id, :name, :parent_stage_id, :display_order, "
                "CAST(:criteria AS jsonb))"
            ),
            [{**r, "criteria": json.dumps(r["criteria"])} for r in stage_rows],
        )

    # ------------------------------------------------------------------
    # Extend the migration-027 trigger function with campaign_stage /
    # campaign_stage_override branches (same defense-in-depth as
    # campaign_result / campaign_measurement), then attach it.
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
            ELSIF TG_TABLE_NAME = 'campaign_stage' THEN
                SELECT status INTO cstat
                  FROM campaign
                 WHERE id = COALESCE(NEW.campaign_id, OLD.campaign_id);
            ELSIF TG_TABLE_NAME = 'campaign_stage_override' THEN
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
    for tbl in ("campaign_stage", "campaign_stage_override"):
        op.execute(
            f"""
            CREATE TRIGGER {tbl}_reject_locked
            BEFORE INSERT OR UPDATE OR DELETE ON {tbl}
            FOR EACH ROW EXECUTE FUNCTION reject_locked_campaign_write();
            """
        )

    # ------------------------------------------------------------------
    # campaign.close_note — recorded by CloseCampaign, cleared by ReopenCampaign.
    # ------------------------------------------------------------------
    op.add_column("campaign", sa.Column("close_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("campaign", "close_note")

    for tbl in ("campaign_stage_override", "campaign_stage"):
        op.execute(f"DROP TRIGGER IF EXISTS {tbl}_reject_locked ON {tbl};")

    # Restore the migration-027 function body verbatim — campaign_result /
    # campaign_measurement triggers still reference this function and stay.
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

    op.drop_table("campaign_stage_override")
    op.drop_table("campaign_stage")
