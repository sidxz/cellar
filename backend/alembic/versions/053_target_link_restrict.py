"""target link FKs: CASCADE -> RESTRICT on the target side

Migration 051 created ``protocol_targets`` / ``run_targets`` with
``ondelete=CASCADE`` on ``target_id``, so deleting a target silently stripped
it from every protocol and run — a regression from the pre-051 scalar FK,
which blocked the delete. RESTRICT restores DB-level protection; the
``DeleteTarget`` use case now 409s with reference counts before the constraint
is ever hit. The owner side (``protocol_id``/``run_id``) keeps CASCADE:
deleting a protocol or run should still drop its link rows.

Revision ID: 053_target_link_restrict
Revises: 052_collection_type
Create Date: 2026-06-05
"""

from __future__ import annotations

from alembic import op

revision = "053_target_link_restrict"
down_revision = "052_collection_type"
branch_labels = None
depends_on = None

_FKS = [
    ("protocol_targets", "protocol_targets_target_id_fkey"),
    ("run_targets", "run_targets_target_id_fkey"),
]


def upgrade() -> None:
    for table, fk in _FKS:
        op.drop_constraint(fk, table, type_="foreignkey")
        op.create_foreign_key(
            fk, table, "targets", ["target_id"], ["id"], ondelete="RESTRICT"
        )


def downgrade() -> None:
    for table, fk in _FKS:
        op.drop_constraint(fk, table, type_="foreignkey")
        op.create_foreign_key(
            fk, table, "targets", ["target_id"], ["id"], ondelete="CASCADE"
        )
