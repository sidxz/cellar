"""041 — enrich excluded_points JSONB shape.

Legacy shape on dose_response_curves.excluded_points is [{idx, reason?}].
Sprint 2 of the DR edit-points redesign requires the enriched shape
[{idx, source, excluded, reason, note, author_id, ts}] to distinguish:
  - user manual exclusions vs. auto-3sigma suggestions
  - suggested-but-not-yet-applied vs. actually-excluded points
  - audit metadata (who, when, why)

Legacy rows are backfilled as source=auto_3sigma, excluded=true because we
cannot reconstruct user intent retroactively.

Revision ID: 041_enrich_excluded_points_shape
Revises: 040_scaffold_membership_index
Create Date: 2026-05-19
"""

from __future__ import annotations

from alembic import op

revision: str = "041_enrich_excluded_points_shape"
down_revision: str | None = "040_scaffold_membership_index"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    # Backfill existing rows: every legacy excluded_points entry becomes
    # {idx, source: "auto_3sigma", excluded: true, reason: <existing or null>,
    #  note: null, author_id: null, ts: <curve.updated_at or now()>}
    op.execute("""
        UPDATE dose_response_curves
        SET excluded_points = (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'idx', (entry->>'idx')::int,
                    'source', COALESCE(entry->>'source', 'auto_3sigma'),
                    'excluded', true,
                    'reason', COALESCE(entry->>'reason', 'auto_3sigma'),
                    'note', NULL,
                    'author_id', NULL,
                    'ts', to_char(COALESCE(updated_at, NOW()), 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
                )
            )
            FROM jsonb_array_elements(excluded_points) AS entry
        )
        WHERE excluded_points IS NOT NULL
          AND jsonb_array_length(excluded_points) > 0
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE dose_response_curves
        SET excluded_points = (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'idx', (entry->>'idx')::int,
                    'reason', entry->>'reason'
                )
            )
            FROM jsonb_array_elements(excluded_points) AS entry
        )
        WHERE excluded_points IS NOT NULL
          AND jsonb_array_length(excluded_points) > 0
    """)
