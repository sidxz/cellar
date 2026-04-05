"""SynthesisRequest table.

Revision ID: 014
Revises: 013
Create Date: 2026-04-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "synthesis_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("requester_id", UUID(as_uuid=True), nullable=False),
        sa.Column("molecule_id", UUID(as_uuid=True), nullable=False, index=True),
        # Target structure (flattened ChemicalStructure VO)
        sa.Column("target_smiles", sa.Text),
        sa.Column("target_inchi", sa.Text),
        sa.Column("target_inchi_key", sa.String(27)),
        # Requested amount (flattened Amount VO)
        sa.Column("requested_amount_value", sa.Float, nullable=False),
        sa.Column("requested_amount_unit", sa.String(30), nullable=False),
        sa.Column("target_purity", sa.Float),
        sa.Column("purpose", sa.Text, nullable=False),
        sa.Column("priority", sa.String(30), nullable=False, server_default="routine"),
        sa.Column("status", sa.String(30), nullable=False, index=True, server_default="draft"),
        sa.Column("project_id", UUID(as_uuid=True)),
        sa.Column("parent_request_id", UUID(as_uuid=True)),
        sa.Column("bulk_request_id", UUID(as_uuid=True)),
        sa.Column("approved_by", UUID(as_uuid=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("rejection_reason", sa.Text),
        # Assignment (flattened SynthesisAssignment VO)
        sa.Column("assignment_type", sa.String(30)),
        sa.Column("assigned_to", UUID(as_uuid=True)),
        sa.Column("assigned_org_id", UUID(as_uuid=True)),
        sa.Column("proposed_route_id", UUID(as_uuid=True)),
        sa.Column("feasibility_notes", sa.Text),
        sa.Column("feasibility_status", sa.String(30)),
        # Estimated cost (flattened Amount VO)
        sa.Column("estimated_cost_value", sa.Float),
        sa.Column("estimated_cost_unit", sa.String(30)),
        # Actual cost (flattened Amount VO)
        sa.Column("actual_cost_value", sa.Float),
        sa.Column("actual_cost_unit", sa.String(30)),
        sa.Column("estimated_completion_date", sa.Date),
        sa.Column("actual_completion_date", sa.Date),
        sa.Column("fulfilled_batch_id", UUID(as_uuid=True)),
        sa.Column("failure_reason", sa.Text),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index(
        "ix_synthesis_requests_workspace_status",
        "synthesis_requests",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_synthesis_requests_molecule",
        "synthesis_requests",
        ["workspace_id", "molecule_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_synthesis_requests_molecule", table_name="synthesis_requests")
    op.drop_index("ix_synthesis_requests_workspace_status", table_name="synthesis_requests")
    op.drop_table("synthesis_requests")
