"""rename the latest_approved_run selection rule to latest_run

The rule never meant "approved": search picked the newest run of any status and
campaigns pick the newest run passing the channel's QC filter. Every stored copy
of the value moves; the append-only audit trail is never touched.

Revision ID: 098_rename_latest_run_rule
Revises: 097_melting_steps
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "098_rename_latest_run_rule"
down_revision: str | None = "097_melting_steps"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_OLD = "latest_approved_run"
_NEW = "latest_run"

# (table, JSONB column, top-level key) — the only places the value is stored.
_JSON_KEYS: tuple[tuple[str, str, str], ...] = (
    ("saved_searches", "query", "aggregation"),
    ("export_jobs", "query_snapshot", "aggregation"),
    ("sar_activity_projections", "channel_spec", "selection_rule"),
    ("sar_activity_values", "snapshot", "selection_rule"),
)


def _rename(old: str, new: str) -> None:
    bind = op.get_bind()
    params = {"old": old, "new": new}
    bind.execute(
        sa.text("UPDATE campaign_channel SET selection_rule = :new WHERE selection_rule = :old"),
        params,
    )
    # Identifiers come from the fixed tuple above, never from input; values are bound.
    for table, column, key in _JSON_KEYS:
        sql = (
            f"UPDATE {table} "  # noqa: S608
            f"SET {column} = jsonb_set({column}, ARRAY['{key}'], to_jsonb(cast(:new AS text))) "
            f"WHERE {column}->>'{key}' = :old"
        )
        bind.execute(sa.text(sql), params)


def upgrade() -> None:
    _rename(_OLD, _NEW)


def downgrade() -> None:
    _rename(_NEW, _OLD)
