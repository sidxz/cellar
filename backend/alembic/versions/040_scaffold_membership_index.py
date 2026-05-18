"""040 — partial composite index for scaffold-membership lookups.

V4 Path A: enables server-side scaffold-membership filtering. The composite
(workspace_id, bemis_murcko_smiles) serves the always-present workspace
tenancy filter plus the scaffold equality predicate in one index seek.
The partial WHERE clause skips acyclic mols (empty string) — they go
through a different code path (mode='acyclic_only') and don't benefit
from this index.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "040_scaffold_membership_index"
down_revision: str | None = "039_umap_jobs"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_index(
        "ix_molecules_workspace_scaffold",
        "molecules",
        ["workspace_id", "bemis_murcko_smiles"],
        postgresql_where=sa.text("bemis_murcko_smiles != ''"),
    )


def downgrade() -> None:
    op.drop_index("ix_molecules_workspace_scaffold", table_name="molecules")
