"""Inventory tables — batches, samples, storage_locations.

Revision ID: 008
Revises: 007
Create Date: 2026-04-04
"""

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: str = "007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Storage locations first (samples FK to it)
    op.create_table(
        "storage_locations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("parent_id", sa.Uuid(), sa.ForeignKey("storage_locations.id")),
        sa.Column("parent_type", sa.String(30)),
        sa.Column("barcode", sa.String(100)),
        sa.Column("temperature", sa.String(50)),
        sa.Column("rows", sa.Integer()),
        sa.Column("columns", sa.Integer()),
        sa.Column("capacity", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_storage_ws_type", "storage_locations", ["workspace_id", "type"])
    op.create_index("ix_storage_parent", "storage_locations", ["parent_id"])

    # Batches
    op.create_table(
        "batches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("molecule_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("batch_number", sa.String(50), nullable=False),
        sa.Column("salt_form", sa.String(100)),
        sa.Column("purity", sa.Float()),
        sa.Column("amount_value", sa.Float(), nullable=False),
        sa.Column("amount_unit", sa.String(20), nullable=False),
        sa.Column("concentration_value", sa.Float()),
        sa.Column("concentration_unit", sa.String(20)),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("supplier_org_id", sa.Uuid()),
        sa.Column("vendor_catalog_number", sa.String(200)),
        sa.Column("vendor_lot_number", sa.String(200)),
        sa.Column("chemist", sa.Uuid(), nullable=False),
        sa.Column("synthesis_date", sa.Date()),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("notebook_reference", sa.String(200)),
        sa.Column("storage_temperature_celsius", sa.Float()),
        sa.Column("storage_humidity_percent", sa.Float()),
        sa.Column("storage_light_condition", sa.String(30)),
        sa.Column("storage_conditions_notes", sa.Text()),
        sa.Column("appearance", sa.String(500)),
        sa.Column("custom_fields", sa.JSON()),
        sa.Column("synthesis_route_id", sa.Uuid()),
        sa.Column("synthesis_step_id", sa.Uuid()),
        sa.Column("synthesis_request_id", sa.Uuid()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_unique_constraint(
        "uq_batch_ws_number", "batches", ["workspace_id", "batch_number"]
    )

    # Samples
    op.create_table(
        "samples",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column(
            "batch_id", sa.Uuid(), sa.ForeignKey("batches.id"), nullable=False
        ),
        sa.Column("barcode", sa.String(100), nullable=False),
        sa.Column("container_type", sa.String(30), nullable=False),
        sa.Column("amount_value", sa.Float(), nullable=False),
        sa.Column("amount_unit", sa.String(20), nullable=False),
        sa.Column("concentration_value", sa.Float()),
        sa.Column("concentration_unit", sa.String(20)),
        sa.Column("solvent", sa.String(100)),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="available",
        ),
        sa.Column(
            "location_id", sa.Uuid(), sa.ForeignKey("storage_locations.id")
        ),
        sa.Column(
            "freeze_thaw_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("low_stock_threshold", sa.Float()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_unique_constraint(
        "uq_sample_ws_barcode", "samples", ["workspace_id", "barcode"]
    )
    op.create_index("ix_sample_batch", "samples", ["batch_id"])
    op.create_index("ix_sample_location", "samples", ["location_id"])
    op.create_index("ix_sample_status", "samples", ["workspace_id", "status"])


def downgrade() -> None:
    op.drop_table("samples")
    op.drop_table("batches")
    op.drop_table("storage_locations")
