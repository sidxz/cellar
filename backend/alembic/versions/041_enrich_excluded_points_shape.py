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
    # Backfill existing rows: legacy [{concentration, response, reason?}] →
    # [{idx: null, concentration, response, source, excluded, reason, note, author_id, ts}].
    # Legacy entries have no idx (curve_fitter.py:177 writes by value, not by index);
    # preserve concentration+response so the chart can still render X markers.
    op.execute("""
        UPDATE dose_response_curves
        SET excluded_points = (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'idx', NULL,
                    'concentration', (entry->>'concentration')::float,
                    'response', (entry->>'response')::float,
                    'source', 'auto_3sigma',
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
    # Restore legacy shape, preserving concentration+response.
    op.execute("""
        UPDATE dose_response_curves
        SET excluded_points = (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'concentration', (entry->>'concentration')::float,
                    'response', (entry->>'response')::float,
                    'reason', entry->>'reason'
                )
            )
            FROM jsonb_array_elements(excluded_points) AS entry
        )
        WHERE excluded_points IS NOT NULL
          AND jsonb_array_length(excluded_points) > 0
    """)
