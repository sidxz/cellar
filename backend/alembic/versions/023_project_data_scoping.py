"""023 — Project data scoping: molecule_projects + project_members tables.

Revision ID: 023
Revises: 022
"""

from alembic import op
import sqlalchemy as sa

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # molecule_projects join table
    op.create_table(
        "molecule_projects",
        sa.Column("molecule_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("molecule_id", "project_id"),
        sa.ForeignKeyConstraint(["molecule_id"], ["molecules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_molecule_projects_project", "molecule_projects", ["project_id"])

    # project_members table
    op.create_table(
        "project_members",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("project_id", "user_id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_project_members_user", "project_members", ["user_id"])

    # Seed: add existing project creators as managers
    op.execute(
        """
        INSERT INTO project_members (project_id, user_id, role)
        SELECT id, created_by, 'manager' FROM projects
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("project_members")
    op.drop_table("molecule_projects")
