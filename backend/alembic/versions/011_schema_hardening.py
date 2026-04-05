"""Schema hardening — workspace isolation, indexes, constraints.

Fixes identified in Phase 1 deep audit:
- DI-03: Partial unique index for single-active protocol per lineage
- DI-06: Add workspace_id to merge_events and bulk_disclosures
- IG-01: Batch number immutability trigger
- IG-03: Missing indexes for common query patterns

Revision ID: 011
Revises: 010
Create Date: 2026-04-04
"""

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: str = "010"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # DI-03: Single active protocol per lineage
    # Only one protocol with status='active' allowed per parent lineage.
    # ------------------------------------------------------------------
    op.create_index(
        "ix_protocol_single_active",
        "protocols",
        ["workspace_id", "parent_protocol_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND parent_protocol_id IS NOT NULL"),
    )

    # ------------------------------------------------------------------
    # DI-06a: Add workspace_id to merge_events
    # ------------------------------------------------------------------
    op.add_column("merge_events", sa.Column("workspace_id", sa.Uuid(), nullable=True))
    op.execute(
        sa.text("""
            UPDATE merge_events me
            SET workspace_id = m.workspace_id
            FROM molecules m
            WHERE me.target_molecule_id = m.id
        """)
    )
    op.alter_column("merge_events", "workspace_id", nullable=False)
    op.create_index("ix_merge_events_workspace", "merge_events", ["workspace_id"])

    # ------------------------------------------------------------------
    # DI-06b: Add workspace_id to bulk_disclosures
    # ------------------------------------------------------------------
    op.add_column("bulk_disclosures", sa.Column("workspace_id", sa.Uuid(), nullable=True))
    op.execute(
        sa.text("""
            UPDATE bulk_disclosures bd
            SET workspace_id = dr.workspace_id
            FROM (
                SELECT DISTINCT bulk_disclosure_id, m.workspace_id
                FROM disclosure_requests d
                JOIN molecules m ON m.id = d.molecule_id
                WHERE d.bulk_disclosure_id IS NOT NULL
            ) dr
            WHERE bd.id = dr.bulk_disclosure_id
        """)
    )
    # For any bulk_disclosures not linked to a DR yet, set a default
    op.execute(
        sa.text("""
            UPDATE bulk_disclosures
            SET workspace_id = '00000000-0000-0000-0000-000000000000'
            WHERE workspace_id IS NULL
        """)
    )
    op.alter_column("bulk_disclosures", "workspace_id", nullable=False)
    op.create_index("ix_bulk_disclosures_workspace", "bulk_disclosures", ["workspace_id"])

    # ------------------------------------------------------------------
    # IG-01: Batch number immutability trigger
    # ------------------------------------------------------------------
    op.execute(
        sa.text("""
            CREATE OR REPLACE FUNCTION prevent_batch_number_update()
            RETURNS TRIGGER AS $$
            BEGIN
                IF OLD.batch_number IS DISTINCT FROM NEW.batch_number THEN
                    RAISE EXCEPTION 'batch_number is immutable and cannot be changed';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
    )
    op.execute(
        sa.text("""
            CREATE TRIGGER trg_batch_number_immutable
            BEFORE UPDATE ON batches
            FOR EACH ROW
            EXECUTE FUNCTION prevent_batch_number_update();
        """)
    )

    # ------------------------------------------------------------------
    # IG-03: Missing indexes for common query patterns
    # ------------------------------------------------------------------
    # disclosure_requests doesn't have workspace_id (scoped via molecules join).

    op.create_index(
        "ix_readout_data_ws_molecule",
        "readout_data",
        ["workspace_id", "molecule_id"],
    )
    op.create_index(
        "ix_dose_response_ws_molecule",
        "dose_response_curves",
        ["workspace_id", "molecule_id"],
    )
    op.create_index(
        "ix_molecule_relationships_source",
        "molecule_relationships",
        ["source_molecule_id"],
    )
    op.create_index(
        "ix_molecule_relationships_target",
        "molecule_relationships",
        ["target_molecule_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_molecule_relationships_target", "molecule_relationships")
    op.drop_index("ix_molecule_relationships_source", "molecule_relationships")
    op.drop_index("ix_dose_response_ws_molecule", "dose_response_curves")
    op.drop_index("ix_readout_data_ws_molecule", "readout_data")

    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_batch_number_immutable ON batches"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_batch_number_update()"))

    op.drop_index("ix_bulk_disclosures_workspace", "bulk_disclosures")
    op.drop_column("bulk_disclosures", "workspace_id")

    op.drop_index("ix_merge_events_workspace", "merge_events")
    op.drop_column("merge_events", "workspace_id")

    op.drop_index("ix_protocol_single_active", "protocols")
