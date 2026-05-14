"""033 — dose_response_curves.readout_definition_id (identity by readout-def).

Pre-this-fix curves were keyed by (workspace, molecule, batch, protocol,
run, curve_type) — but ``curve_type`` is a *label* (IC50/EC50/Ki/...),
not identity. A protocol can declare N dose-response readouts (target
IC50, counter-screen IC50, cytotoxicity LD50, ...) and each one's fit
must round-trip through storage independently. Without this column,
channel-resolution queries that find candidates for a (protocol,
molecule) tuple silently pick among N ambiguous rows.

The right anchor is the ``ReadoutDefinition`` the fit was computed for
— the same entity that owns the ``DoseResponseConfig`` that drove the
fit (``backend/src/cellar/domain/screening_assay/protocol.py:185``).
This matches industry practice across CDD Vault, Genedata Screener,
Dotmatics, LiveDesign, Benchling, and PubChem BioAssay: a fitted curve
is owned by exactly one readout/column entity, identified by that
entity's UUID. ``curve_type`` stays on the row as descriptive metadata
(display label + IC vs EC intercept language) but is no longer
identifying.

Dev-mode change with no backward-compat: the column is NOT NULL FK with
no safe synthetic backfill (rows with two DR readouts of the same
curve_type are genuinely ambiguous), so we truncate
``dose_response_curves`` and null out the campaign_measurement audit
FKs that pointed at the wiped rows. Operators refit the runs they care
about; the fitter is idempotent.

Adds:
  * ``readout_definition_id`` NOT NULL FK (CASCADE on delete — readout-def
    removal is draft-only so cascading is safe).
  * ``ix_drc_resolver`` composite index for the channel-resolver hot path
    ``(workspace_id, molecule_id, protocol_id, readout_definition_id)``.
  * ``uq_drc_run_well_readout`` unique constraint
    ``(workspace_id, run_id, molecule_id, batch_id, readout_definition_id)``
    — one fit per (run, well-group, readout) — enforces the invariant the
    wipe-then-rewrite fitter already produces.

Revision ID: 033_drc_readout_definition_id
Revises: 032_repair_orphan_dr_y_readout
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "033_drc_readout_definition_id"
down_revision: str | None = "032_repair_orphan_dr_y_readout"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    conn = op.get_bind()

    # Null the campaign_measurement audit fields that reference about-to-be-
    # wiped curves. Cells will re-resolve on the next campaign refresh.
    conn.execute(
        sa.text(
            "UPDATE campaign_measurement "
            "SET source_curve_id = NULL, curve_snapshot = NULL "
            "WHERE source_curve_id IS NOT NULL OR curve_snapshot IS NOT NULL"
        )
    )

    # Truncate the curves table — no safe synthetic backfill exists for
    # multi-DR protocols (two DRs sharing a curve_type are indistinguishable
    # under the old schema).
    conn.execute(sa.text("TRUNCATE TABLE dose_response_curves"))

    op.add_column(
        "dose_response_curves",
        sa.Column(
            "readout_definition_id",
            sa.Uuid(),
            sa.ForeignKey("readout_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_drc_resolver",
        "dose_response_curves",
        ["workspace_id", "molecule_id", "protocol_id", "readout_definition_id"],
    )
    op.create_unique_constraint(
        "uq_drc_run_well_readout",
        "dose_response_curves",
        ["workspace_id", "run_id", "molecule_id", "batch_id", "readout_definition_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_drc_run_well_readout", "dose_response_curves", type_="unique")
    op.drop_index("ix_drc_resolver", table_name="dose_response_curves")
    op.drop_column("dose_response_curves", "readout_definition_id")
