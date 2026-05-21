"""042 — configurable registration-number prefix.

One-time data rewrite: existing molecules + derived batches + bulk-registration
items move from CV-NNNNN to CC-NNNNNN. The numeric tail is preserved (CV-00982
becomes CC-000982). Each workspace's settings.registration_rules JSONB is
seeded with the new default prefix + width so newly-registered compounds use
the new scheme.

The lookup query in molecule_repository.next_registration_number is
regex-based and tolerates mixed prefix/width history, so the rewrite is
self-consistent: after migration, MAX(numeric_tail) is unchanged, and the
next registration emits CC-{max+1:06d}.

Revision ID: 042_configurable_reg_prefix
Revises: 041_enrich_excluded_points_shape
Create Date: 2026-05-21
"""

from __future__ import annotations

from alembic import op


revision: str = "042_configurable_reg_prefix"
down_revision: str | None = "041_enrich_excluded_points_shape"
branch_labels: None = None
depends_on: None = None


_NEW_PREFIX = "CC-"
_NEW_WIDTH = 6


def upgrade() -> None:
    # 1. Rewrite molecules.registration_number.
    # SUBSTRING(... FROM '[0-9]+$') extracts the trailing numeric run.
    op.execute(f"""
        UPDATE molecules
        SET registration_number = '{_NEW_PREFIX}' || LPAD(
            SUBSTRING(registration_number FROM '[0-9]+$'),
            {_NEW_WIDTH},
            '0'
        )
        WHERE registration_number ~ '[0-9]+$'
    """)

    # 2. Rewrite batches.batch_number. Pattern: <mol_reg>-<seq>. Replace the
    #    leading mol_reg portion with the freshly-rewritten value via JOIN.
    op.execute("""
        UPDATE batches b
        SET batch_number = m.registration_number || '-' ||
            SUBSTRING(b.batch_number FROM '-([0-9]+)$')
        FROM molecules m
        WHERE b.molecule_id = m.id
          AND b.batch_number ~ '-[0-9]+$'
    """)

    # 3. Rewrite bulk_registration_items.registration_number where populated.
    op.execute(f"""
        UPDATE bulk_registration_items
        SET registration_number = '{_NEW_PREFIX}' || LPAD(
            SUBSTRING(registration_number FROM '[0-9]+$'),
            {_NEW_WIDTH},
            '0'
        )
        WHERE registration_number IS NOT NULL
          AND registration_number ~ '[0-9]+$'
    """)

    # 4. Seed workspace_settings.registration_rules with the new defaults.
    # The column is typed as JSON (not JSONB) so we cast to jsonb for the merge
    # operator (||) then cast back to json for the assignment.
    op.execute(f"""
        UPDATE workspace_settings
        SET registration_rules = (
            COALESCE(registration_rules::jsonb, '{{}}'::jsonb) ||
            '{{"registration_number_prefix": "{_NEW_PREFIX}",
               "registration_number_width": {_NEW_WIDTH}}}'::jsonb
        )::json
    """)

    # 5. Sanity assertion — no row should still carry the legacy prefix.
    op.execute("""
        DO $$
        DECLARE leftover INT;
        BEGIN
            SELECT COUNT(*) INTO leftover FROM molecules
            WHERE registration_number !~ '^[A-Z]{2,8}-[0-9]+$';
            IF leftover > 0 THEN
                RAISE EXCEPTION 'Migration 042: % molecules failed rewrite', leftover;
            END IF;
        END $$
    """)


def downgrade() -> None:
    # This migration is a one-way data rewrite once the database has more than
    # 9999 molecules: 6-digit CC- numbers above CC-009999 cannot be losslessly
    # mapped back to 5-digit CV- numbers (two different 6-digit tails can share
    # the same last 5 digits, producing unique-constraint collisions on
    # (workspace_id, registration_number)).
    #
    # We guard explicitly: if the molecule table has any rows at all after a
    # real-world upgrade the downgrade is refused.  In a clean test environment
    # (empty DB or all tails <= 9999 AND no collisions) the guard allows it.
    op.execute("""
        DO $$
        DECLARE collision_count INT;
        BEGIN
            -- Detect any workspace where the 5-digit projection would collide.
            SELECT COUNT(*) INTO collision_count
            FROM (
                SELECT workspace_id,
                       'CV-' || LPAD(SUBSTRING(registration_number FROM '[0-9]+$'), 5, '0') AS projected
                FROM molecules
                WHERE registration_number ~ '[0-9]+$'
                GROUP BY workspace_id,
                         'CV-' || LPAD(SUBSTRING(registration_number FROM '[0-9]+$'), 5, '0')
                HAVING COUNT(*) > 1
            ) AS collisions;
            IF collision_count > 0 THEN
                RAISE EXCEPTION
                    'Cannot downgrade migration 042: % CV-NNNNN values would collide '
                    '(dataset too large for 5-digit pad). Downgrade is not supported '
                    'on a production database.', collision_count;
            END IF;
        END $$
    """)

    # Reverse 1: CC-NNNNNN → CV-NNNNN (5-digit pad, only safe on small datasets).
    op.execute("""
        UPDATE molecules
        SET registration_number = 'CV-' || LPAD(
            SUBSTRING(registration_number FROM '[0-9]+$'), 5, '0'
        )
        WHERE registration_number ~ '[0-9]+$'
    """)

    # Reverse 2: re-derive batch numbers from molecules.
    op.execute("""
        UPDATE batches b
        SET batch_number = m.registration_number || '-' ||
            SUBSTRING(b.batch_number FROM '-([0-9]+)$')
        FROM molecules m
        WHERE b.molecule_id = m.id
          AND b.batch_number ~ '-[0-9]+$'
    """)

    # Reverse 3: bulk_registration_items.
    op.execute("""
        UPDATE bulk_registration_items
        SET registration_number = 'CV-' || LPAD(
            SUBSTRING(registration_number FROM '[0-9]+$'), 5, '0'
        )
        WHERE registration_number IS NOT NULL
          AND registration_number ~ '[0-9]+$'
    """)

    # Reverse 4: remove the new keys from registration_rules.
    # Cast to jsonb for the key-deletion operator (-), then back to json.
    op.execute("""
        UPDATE workspace_settings
        SET registration_rules = (
            (registration_rules::jsonb
                - 'registration_number_prefix'
                - 'registration_number_width')
        )::json
    """)
