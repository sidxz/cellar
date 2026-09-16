"""071 — shipment as the container for the trip (spec 2026-08-26 §2)

shipment_items become polymorphic (plate | sample): item_type + sample_id
renamed to item_id, amount nullable (plates ship whole). shipments gain a
direction (outbound | inbound) and an optional loan link (FK SET NULL).
Existing rows: item_type='sample', direction='outbound' via server defaults.

Revision ID: 071_shipment_container
Revises: 070_plate_group_collection
"""

import sqlalchemy as sa
from alembic import op

revision = "071_shipment_container"
down_revision = "070_plate_group_collection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shipment_items",
        sa.Column("item_type", sa.String(20), nullable=False, server_default="sample"),
    )
    op.alter_column("shipment_items", "sample_id", new_column_name="item_id")
    op.alter_column("shipment_items", "amount_shipped_value", nullable=True)
    op.alter_column("shipment_items", "amount_shipped_unit", nullable=True)
    op.create_index("ix_shipment_items_item", "shipment_items", ["item_type", "item_id"])
    op.add_column(
        "shipments",
        sa.Column("direction", sa.String(10), nullable=False, server_default="outbound"),
    )
    op.add_column("shipments", sa.Column("loan_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_shipments_loan", "shipments", "plate_loans", ["loan_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_shipments_loan", "shipments", ["loan_id"])


def downgrade() -> None:
    # Plate items have no pre-071 representation; drop them before restoring NOT NULL.
    op.execute("DELETE FROM shipment_items WHERE item_type <> 'sample'")
    op.drop_index("ix_shipments_loan", table_name="shipments")
    op.drop_constraint("fk_shipments_loan", "shipments", type_="foreignkey")
    op.drop_column("shipments", "loan_id")
    op.drop_column("shipments", "direction")
    op.drop_index("ix_shipment_items_item", table_name="shipment_items")
    op.alter_column("shipment_items", "amount_shipped_unit", nullable=False)
    op.alter_column("shipment_items", "amount_shipped_value", nullable=False)
    op.alter_column("shipment_items", "item_id", new_column_name="sample_id")
    op.drop_column("shipment_items", "item_type")
