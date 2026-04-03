"""Enable RDKit PostgreSQL extension.

Revision ID: 001
Revises:
Create Date: 2026-04-03
"""

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS rdkit")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS rdkit")
