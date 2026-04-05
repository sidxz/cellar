"""SampleRequest + Shipment tables.

Revision ID: 013
Revises: 012
Create Date: 2026-04-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sample_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("requester_id", UUID(as_uuid=True), nullable=False),
        sa.Column("molecule_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("batch_id", UUID(as_uuid=True)),
        sa.Column("requested_amount_value", sa.Float, nullable=False),
        sa.Column("requested_amount_unit", sa.String(30), nullable=False),
        sa.Column("purpose", sa.Text, nullable=False),
        sa.Column("priority", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("assigned_to", UUID(as_uuid=True)),
        sa.Column("fulfilled_sample_id", UUID(as_uuid=True)),
        sa.Column("rejection_reason", sa.Text),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "shipments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("destination_org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sender_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tracking_number", sa.String(255)),
        sa.Column("carrier", sa.String(100)),
        sa.Column("shipping_date", sa.Date),
        sa.Column("expected_arrival_date", sa.Date),
        sa.Column("received_date", sa.Date),
        sa.Column("shipping_conditions", sa.Text),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("notes", sa.Text),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "shipment_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shipment_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shipments.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("sample_id", UUID(as_uuid=True), nullable=False),
        sa.Column("amount_shipped_value", sa.Float, nullable=False),
        sa.Column("amount_shipped_unit", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("shipment_items")
    op.drop_table("shipments")
    op.drop_table("sample_requests")
