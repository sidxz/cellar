"""104 — each campaign stage owns its runs and columns; cells record their facts.

Schema:
  * campaign_channel.stage_id — the stage owning the column (FK campaign_stage,
    ON DELETE CASCADE, indexed); NULL for a campaign column.
  * campaign_channel.test_concentration — JSONB {value, unit}, NULL unless pinned.
  * campaign_measurement.batch_ids (uuid[]), basis (varchar 16),
    concentration_series (bool, default false), unresolved_reason (varchar 32),
    concentrations_found (JSONB list of {value, unit}).

Existing campaigns (spec §11), by one generic rule and without recomputing a value:
  1. A column named by exactly one stage's criteria moves to that stage.
  2. A column named by several stages moves to the first of them (display order,
     then id) and is cloned for each other one, with its measurements copied under
     new ids and that stage's criteria repointed to the clone.
  3. A column named by no stage stays a campaign column.
  4. Each seed run gets ``stage_ids``: the stages owning a column of its protocol.
  5. A stage column whose protocol has no seed run (it read protocol-wide) gets
     ``resolve_from_all_runs = true``, so it keeps reading the same runs.

Step 2 writes campaign_stage and campaign_measurement, whose reject_locked
triggers (migrations 027/074) block writes under closed campaigns. Earlier data
migrations never met them (074 backfilled before attaching its trigger, 075 only
dropped columns, 079 wrote ``campaign``, which has none), so this one disables the
two triggers around its data steps and re-enables them.

Lock (spec §9): after the data steps, the 074 trigger function gains two branches
and two triggers, so a closed or superseded campaign also refuses at the database
any write of its columns (``campaign_channel``: stage, test concentration, ...) and
any change of its stage runs (``campaign.seed_runs``; the campaign's other fields,
such as the status reopen flips, stay writable).

Downgrade drops those two triggers and restores 074's function body, then drops
the new columns and strips ``stage_ids`` from every seed run. Stage membership is
lost and clones stay as ordinary campaign columns (their criteria still point at
them, which the old schema allows); nothing is un-cloned.

Revision ID: 104_stage_owned_campaign_values
Revises: 103_readout_data_replicate_count
Create Date: 2026-11-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "104_stage_owned_campaign_values"
down_revision = "103_readout_data_replicate_count"

_LOCKED = ("campaign_stage", "campaign_measurement")

# Migration 074's reject_locked_campaign_write(); ``-- 104 branches`` marks where
# this migration adds its own (and where the downgrade leaves none).
_LOCK_FUNCTION = """
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
    -- 104 branches
    END IF;
    IF cstat IN ('closed', 'superseded') THEN
        RAISE EXCEPTION 'Campaign is %, writes blocked', cstat USING ERRCODE = 'check_violation';
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;
"""

_BRANCHES_104 = """
    ELSIF TG_TABLE_NAME = 'campaign_channel' THEN
        SELECT status INTO cstat
          FROM campaign
         WHERE id = COALESCE(NEW.campaign_id, OLD.campaign_id);
    ELSIF TG_TABLE_NAME = 'campaign' THEN
        -- Fired only by a change of seed_runs: locked while the campaign was.
        cstat := OLD.status;
"""

# (trigger, table, when it fires); each runs reject_locked_campaign_write().
_TRIGGERS_104 = (
    (
        "campaign_channel_reject_locked",
        "campaign_channel",
        "BEFORE INSERT OR UPDATE OR DELETE ON campaign_channel FOR EACH ROW",
    ),
    (
        "campaign_seed_runs_reject_locked",
        "campaign",
        "BEFORE UPDATE OF seed_runs ON campaign FOR EACH ROW"
        " WHEN (OLD.seed_runs IS DISTINCT FROM NEW.seed_runs)",
    ),
)

# Every (stage, column) a criterion names; the first stage per column keeps it,
# every other stage gets a fresh id for its clone.
_REFS = """
CREATE TEMP TABLE m104_ref AS
SELECT stage_id, channel_id,
       CASE WHEN rank = 1 THEN channel_id ELSE gen_random_uuid() END AS new_channel_id
  FROM (
    SELECT r.stage_id, r.channel_id,
           row_number() OVER (PARTITION BY r.channel_id ORDER BY s.display_order, s.id) AS rank
      FROM (SELECT DISTINCT s.id AS stage_id, (crit->>'channel_id')::uuid AS channel_id
              FROM campaign_stage s, jsonb_array_elements(s.criteria) crit) r
      JOIN campaign_stage s ON s.id = r.stage_id
      JOIN campaign_channel ch ON ch.id = r.channel_id AND ch.campaign_id = s.campaign_id
     WHERE ch.stage_id IS NULL
  ) ranked
"""

_STEPS = (
    # 1 + 2: the first naming stage takes the column.
    """
    UPDATE campaign_channel ch SET stage_id = r.stage_id
      FROM m104_ref r
     WHERE r.channel_id = ch.id AND r.new_channel_id = r.channel_id
    """,
    # 2: a clone for every other naming stage ...
    """
    INSERT INTO campaign_channel
        (id, campaign_id, stage_id, label, display_order, protocol_id,
         readout_definition_id, source_kind, selection_rule, qualifier_handling,
         qc_filter, normalization_applied, intercept_key, resolve_from_all_runs)
    SELECT r.new_channel_id, ch.campaign_id, r.stage_id, ch.label, ch.display_order,
           ch.protocol_id, ch.readout_definition_id, ch.source_kind, ch.selection_rule,
           ch.qualifier_handling, ch.qc_filter, ch.normalization_applied, ch.intercept_key,
           ch.resolve_from_all_runs
      FROM m104_ref r JOIN campaign_channel ch ON ch.id = r.channel_id
     WHERE r.new_channel_id <> r.channel_id
    """,
    # ... carrying a copy of every cell ...
    """
    INSERT INTO campaign_measurement
        (id, result_id, channel_id, value, value_qualifier, unit, is_manual_override,
         source_run_id, source_curve_id, source_readout_id, protocol_name_snapshot,
         protocol_version_snapshot, run_date_snapshot, override_reason,
         test_concentration_value, test_concentration_unit, replicate_count, qc_pass,
         contributing_run_ids, curve_snapshot)
    SELECT gen_random_uuid(), m.result_id, r.new_channel_id, m.value, m.value_qualifier,
           m.unit, m.is_manual_override, m.source_run_id, m.source_curve_id,
           m.source_readout_id, m.protocol_name_snapshot, m.protocol_version_snapshot,
           m.run_date_snapshot, m.override_reason, m.test_concentration_value,
           m.test_concentration_unit, m.replicate_count, m.qc_pass,
           m.contributing_run_ids, m.curve_snapshot
      FROM m104_ref r JOIN campaign_measurement m ON m.channel_id = r.channel_id
     WHERE r.new_channel_id <> r.channel_id
    """,
    # ... and the stage's criteria pointing at it.
    """
    UPDATE campaign_stage s
       SET criteria = (
           SELECT jsonb_agg(
                      CASE WHEN r.new_channel_id IS NULL THEN e.crit
                           ELSE jsonb_set(e.crit, '{channel_id}', to_jsonb(r.new_channel_id::text))
                      END
                      ORDER BY e.ord)
             FROM jsonb_array_elements(s.criteria) WITH ORDINALITY AS e(crit, ord)
             LEFT JOIN m104_ref r
               ON r.stage_id = s.id
              AND r.channel_id = (e.crit->>'channel_id')::uuid
              AND r.new_channel_id <> r.channel_id)
     WHERE s.id IN (SELECT stage_id FROM m104_ref WHERE new_channel_id <> channel_id)
    """,
    # 4: each seed run serves the stages owning a column of its protocol.
    """
    UPDATE campaign c
       SET seed_runs = (
           SELECT jsonb_agg(
                      e.run || jsonb_build_object('stage_ids', COALESCE((
                          SELECT jsonb_agg(st.id::text ORDER BY st.display_order, st.id)
                            FROM campaign_stage st
                           WHERE st.campaign_id = c.id
                             AND EXISTS (
                                 SELECT 1 FROM campaign_channel ch
                                  WHERE ch.stage_id = st.id
                                    AND ch.protocol_id = (e.run->>'protocol_id')::uuid)
                      ), '[]'::jsonb))
                      ORDER BY e.ord)
             FROM jsonb_array_elements(c.seed_runs) WITH ORDINALITY AS e(run, ord))
     WHERE jsonb_array_length(c.seed_runs) > 0
    """,
    # 5: a stage column with no seed run of its protocol read protocol-wide; keep that.
    """
    UPDATE campaign_channel ch SET resolve_from_all_runs = true
      FROM campaign c
     WHERE c.id = ch.campaign_id
       AND ch.stage_id IS NOT NULL
       AND NOT ch.resolve_from_all_runs
       AND NOT EXISTS (
           SELECT 1 FROM jsonb_array_elements(c.seed_runs) e
            WHERE (e->>'protocol_id')::uuid = ch.protocol_id)
    """,
)


def upgrade() -> None:
    op.add_column(
        "campaign_channel",
        sa.Column(
            "stage_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("campaign_stage.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_campaign_channel_stage_id", "campaign_channel", ["stage_id"])
    op.add_column("campaign_channel", sa.Column("test_concentration", postgresql.JSONB()))
    op.add_column(
        "campaign_measurement",
        sa.Column("batch_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
    )
    op.add_column("campaign_measurement", sa.Column("basis", sa.String(16)))
    op.add_column(
        "campaign_measurement",
        sa.Column("concentration_series", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("campaign_measurement", sa.Column("unresolved_reason", sa.String(32)))
    op.add_column("campaign_measurement", sa.Column("concentrations_found", postgresql.JSONB()))

    for table in _LOCKED:
        op.execute(f"ALTER TABLE {table} DISABLE TRIGGER {table}_reject_locked")
    op.execute(_REFS)
    for step in _STEPS:
        op.execute(step)
    op.execute("DROP TABLE m104_ref")
    for table in _LOCKED:
        op.execute(f"ALTER TABLE {table} ENABLE TRIGGER {table}_reject_locked")

    op.execute(_LOCK_FUNCTION.replace("    -- 104 branches\n", _BRANCHES_104))
    for name, _, fires in _TRIGGERS_104:
        op.execute(
            f"CREATE TRIGGER {name} {fires} EXECUTE FUNCTION reject_locked_campaign_write()"
        )


def downgrade() -> None:
    for name, table, _ in _TRIGGERS_104:
        op.execute(f"DROP TRIGGER IF EXISTS {name} ON {table}")
    op.execute(_LOCK_FUNCTION.replace("    -- 104 branches\n", ""))
    op.execute(
        """
        UPDATE campaign c
           SET seed_runs = (
               SELECT jsonb_agg(e.run - 'stage_ids' ORDER BY e.ord)
                 FROM jsonb_array_elements(c.seed_runs) WITH ORDINALITY AS e(run, ord))
         WHERE jsonb_array_length(c.seed_runs) > 0
        """
    )
    for column in (
        "concentrations_found",
        "unresolved_reason",
        "concentration_series",
        "basis",
        "batch_ids",
    ):
        op.drop_column("campaign_measurement", column)
    op.drop_column("campaign_channel", "test_concentration")
    op.drop_index("ix_campaign_channel_stage_id", table_name="campaign_channel")
    op.drop_column("campaign_channel", "stage_id")
