"""069 — plates.registered_plate_id (spec 2026-08-26 §4)

Optional link from a run plate to the physical inventory plate it was run on.
FK SET NULL on inventory-plate delete. Back-fills existing rows: exact barcode
match, else exact plate_map->>'name' = plate_label, same workspace as the run,
only when exactly one candidate matches.

Revision ID: 069_run_plate_registered_plate
Revises: 068_plate_comments
"""

import sqlalchemy as sa
from alembic import op

revision = "069_run_plate_registered_plate"
down_revision = "068_plate_comments"
branch_labels = None
depends_on = None

# ponytail: exact matches only; the app resolver handles zero-padding for new
# links. Re-run by hand if a wider backfill is ever needed.
BACKFILL_SQL = """
WITH candidates AS (
  SELECT p.id AS plate_id, rp.id AS registered_plate_id
  FROM plates p
  JOIN runs r ON r.id = p.run_id
  JOIN registered_plates rp ON rp.workspace_id = r.workspace_id
   AND (rp.barcode = p.barcode OR rp.plate_label = p.plate_map->>'name')
  WHERE p.registered_plate_id IS NULL
), unique_candidates AS (
  SELECT plate_id, MIN(registered_plate_id::text)::uuid AS registered_plate_id
  FROM candidates GROUP BY plate_id HAVING COUNT(*) = 1
)
UPDATE plates p SET registered_plate_id = u.registered_plate_id
FROM unique_candidates u WHERE u.plate_id = p.id
"""


def upgrade() -> None:
    op.add_column("plates", sa.Column("registered_plate_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_plates_registered_plate",
        "plates",
        "registered_plates",
        ["registered_plate_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_plates_registered_plate", "plates", ["registered_plate_id"])
    op.execute(BACKFILL_SQL)


def downgrade() -> None:
    op.drop_index("ix_plates_registered_plate", table_name="plates")
    op.drop_constraint("fk_plates_registered_plate", "plates", type_="foreignkey")
    op.drop_column("plates", "registered_plate_id")
