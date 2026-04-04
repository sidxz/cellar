"""Screening & Assay tables — targets, plate_templates, protocols,
readout_definitions, condition_definitions, runs, plates, wells,
readout_data, dose_response_curves.

Revision ID: 009
Revises: 008
Create Date: 2026-04-04
"""

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: str = "008"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. targets (referenced by protocols)
    # ------------------------------------------------------------------
    op.create_table(
        "targets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("organism", sa.String(200)),
        sa.Column("gene_name", sa.String(200)),
        sa.Column("uniprot_id", sa.String(20)),
        sa.Column("ncbi_gene_id", sa.String(30)),
        sa.Column("description", sa.Text()),
        sa.Column("target_class", sa.String(100)),
        sa.Column("sequence", sa.Text()),
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
    )
    op.create_index("ix_target_ws_name", "targets", ["workspace_id", "name"])

    # ------------------------------------------------------------------
    # 2. plate_templates
    # ------------------------------------------------------------------
    op.create_table(
        "plate_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column(
            "template_map",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column("description", sa.Text()),
        sa.Column("created_by", sa.Uuid(), nullable=False),
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
    )
    op.create_index("ix_plate_template_ws", "plate_templates", ["workspace_id"])

    # ------------------------------------------------------------------
    # 3. protocols (FK -> targets)
    # ------------------------------------------------------------------
    op.create_table(
        "protocols",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("protocol_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.Uuid(), sa.ForeignKey("targets.id")),
        sa.Column("category", sa.String(100)),
        sa.Column(
            "protocol_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "parent_protocol_id", sa.Uuid(), sa.ForeignKey("protocols.id")
        ),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="draft"
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
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
    op.create_index(
        "ix_protocol_ws_name", "protocols", ["workspace_id", "name"]
    )
    op.create_index("ix_protocol_parent", "protocols", ["parent_protocol_id"])
    op.create_index(
        "ix_protocol_ws_status", "protocols", ["workspace_id", "status"]
    )

    # ------------------------------------------------------------------
    # 4. readout_definitions (FK -> protocols, CASCADE)
    # ------------------------------------------------------------------
    op.create_table(
        "readout_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "protocol_id",
            sa.Uuid(),
            sa.ForeignKey("protocols.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("data_type", sa.String(20), nullable=False),
        sa.Column("unit", sa.String(50)),
        sa.Column(
            "aggregation", sa.String(30), nullable=False, server_default="none"
        ),
        sa.Column("precision", sa.Integer()),
        sa.Column(
            "normalization",
            sa.String(30),
            nullable=False,
            server_default="none",
        ),
        sa.Column(
            "is_calculated",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("calculation_formula", sa.Text()),
        sa.Column(
            "display_order", sa.Integer(), nullable=False, server_default="0"
        ),
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
    )
    op.create_index(
        "ix_readout_def_protocol", "readout_definitions", ["protocol_id"]
    )

    # ------------------------------------------------------------------
    # 5. condition_definitions (FK -> protocols, CASCADE)
    # ------------------------------------------------------------------
    op.create_table(
        "condition_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "protocol_id",
            sa.Uuid(),
            sa.ForeignKey("protocols.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("data_type", sa.String(20), nullable=False),
        sa.Column("unit", sa.String(50)),
        sa.Column("pick_list_values", sa.dialects.postgresql.JSONB()),
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
    )
    op.create_index(
        "ix_condition_def_protocol", "condition_definitions", ["protocol_id"]
    )

    # ------------------------------------------------------------------
    # 6. runs (FK -> protocols, self-ref parent_run_id)
    # ------------------------------------------------------------------
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column(
            "protocol_id",
            sa.Uuid(),
            sa.ForeignKey("protocols.id"),
            nullable=False,
        ),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("operator", sa.Uuid(), nullable=False),
        sa.Column("performed_at_org_id", sa.Uuid()),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="draft"
        ),
        sa.Column("parent_run_id", sa.Uuid(), sa.ForeignKey("runs.id")),
        sa.Column("run_relationship_type", sa.String(30)),
        sa.Column("plate_format", sa.String(10)),
        sa.Column("conditions", sa.dialects.postgresql.JSONB()),
        sa.Column("qc_metrics", sa.dialects.postgresql.JSONB()),
        sa.Column(
            "is_locked",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("locked_by", sa.Uuid()),
        sa.Column("lock_reason", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("eln_entry_id", sa.Uuid()),
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
    op.create_index("ix_run_protocol", "runs", ["protocol_id"])
    op.create_index("ix_run_ws_status", "runs", ["workspace_id", "status"])
    op.create_index("ix_run_parent", "runs", ["parent_run_id"])

    # ------------------------------------------------------------------
    # 7. plates (FK -> runs, CASCADE)
    # ------------------------------------------------------------------
    op.create_table(
        "plates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plate_number", sa.Integer(), nullable=False),
        sa.Column("barcode", sa.String(100)),
        sa.Column("format", sa.String(10)),
        sa.Column("plate_map", sa.dialects.postgresql.JSONB()),
        sa.Column("parent_plate_id", sa.Uuid()),
        sa.Column("template_id", sa.Uuid()),
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
    )
    op.create_index("ix_plate_run", "plates", ["run_id"])

    # ------------------------------------------------------------------
    # 8. wells (FK -> plates, CASCADE)
    # ------------------------------------------------------------------
    op.create_table(
        "wells",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "plate_id",
            sa.Uuid(),
            sa.ForeignKey("plates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row", sa.String(2), nullable=False),
        sa.Column("column", sa.Integer(), nullable=False),
        sa.Column(
            "well_type",
            sa.String(30),
            nullable=False,
            server_default="sample",
        ),
        sa.Column("batch_id", sa.Uuid()),
        sa.Column("concentration_value", sa.Float()),
        sa.Column("concentration_unit", sa.String(20)),
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
    )
    op.create_index("ix_well_plate", "wells", ["plate_id"])

    # ------------------------------------------------------------------
    # 9. readout_data (FK -> runs, readout_definitions)
    # ------------------------------------------------------------------
    op.create_table(
        "readout_data",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("runs.id"),
            nullable=False,
        ),
        sa.Column("well_id", sa.Uuid()),
        sa.Column("molecule_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column(
            "readout_definition_id",
            sa.Uuid(),
            sa.ForeignKey("readout_definitions.id"),
            nullable=False,
        ),
        sa.Column("value_numeric", sa.Float()),
        sa.Column("value_qualifier", sa.String(5)),
        sa.Column("value_text", sa.Text()),
        sa.Column(
            "is_outlier",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
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
    )
    op.create_index("ix_readout_data_run", "readout_data", ["run_id"])
    op.create_index("ix_readout_data_molecule", "readout_data", ["molecule_id"])
    op.create_index(
        "ix_readout_data_definition",
        "readout_data",
        ["readout_definition_id"],
    )

    # ------------------------------------------------------------------
    # 10. dose_response_curves (FK -> protocols, runs)
    # ------------------------------------------------------------------
    op.create_table(
        "dose_response_curves",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("molecule_id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column(
            "protocol_id",
            sa.Uuid(),
            sa.ForeignKey("protocols.id"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("runs.id"),
            nullable=False,
        ),
        sa.Column("curve_type", sa.String(20), nullable=False),
        sa.Column("fitted_value", sa.Float(), nullable=False),
        sa.Column("fitted_unit", sa.String(20), nullable=False),
        sa.Column("hill_slope", sa.Float(), nullable=False),
        sa.Column("top", sa.Float(), nullable=False),
        sa.Column("bottom", sa.Float(), nullable=False),
        sa.Column("r_squared", sa.Float(), nullable=False),
        sa.Column("confidence_interval_low", sa.Float()),
        sa.Column("confidence_interval_high", sa.Float()),
        sa.Column("num_points", sa.Integer(), nullable=False),
        sa.Column("curve_class", sa.String(20)),
        sa.Column("raw_data", sa.dialects.postgresql.JSONB()),
        sa.Column("excluded_points", sa.dialects.postgresql.JSONB()),
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
    )
    op.create_index("ix_drc_run", "dose_response_curves", ["run_id"])
    op.create_index("ix_drc_molecule", "dose_response_curves", ["molecule_id"])
    op.create_index("ix_drc_protocol", "dose_response_curves", ["protocol_id"])


def downgrade() -> None:
    op.drop_table("dose_response_curves")
    op.drop_table("readout_data")
    op.drop_table("wells")
    op.drop_table("plates")
    op.drop_table("runs")
    op.drop_table("condition_definitions")
    op.drop_table("readout_definitions")
    op.drop_table("protocols")
    op.drop_table("plate_templates")
    op.drop_table("targets")
