"""037 — bemis_murcko_smiles on molecule.

Per-molecule Bemis-Murcko scaffold SMILES, populated at registration.
NULL distinguishes "not yet computed" from "" (acyclic — RDKit convention).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "037_bemis_murcko_smiles"
down_revision: str | None = "036_export_jobs"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column(
        "molecules",
        sa.Column("bemis_murcko_smiles", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("molecules", "bemis_murcko_smiles")
