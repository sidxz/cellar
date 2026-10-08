"""protocol categories: label + name pattern (replaces the "Protocol Categories" vocabulary)

Revision ID: 084_protocol_categories
Revises: 083_protocol_aliases
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "084_protocol_categories"
down_revision: str | None = "083_protocol_aliases"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

DEFAULT_PATTERNS = {  # copy of DEFAULT_CATEGORY_PATTERNS at the time of this migration
    "Enzyme inhibition": "{target} inhibition",
    "Enzyme activation": "{target} activation",
    "Binding": "{target} binding",
    "Receptor function": "{target} {discriminator}",
    "Ion-channel inhibition": "{target} inhibition",
    "Growth inhibition": "{organism} growth inhibition",
    "Bactericidal activity": "{organism} bactericidal activity",
    "Intracellular growth inhibition": "Intracellular {organism} growth inhibition",
    "Metabolite rescue": "{organism} metabolite rescue",
    "Membrane potential": "{organism} membrane potential",
    "Resistance selection": "{organism?} resistant mutant selection",
    "Combination (checkerboard)": "{subject?} combination",
    "Cytotoxicity": "{cell_line} cytotoxicity",
    "Infection inhibition": "{organism} infection inhibition",
    "In vitro translation inhibition": "{organism} in vitro translation inhibition",
    "Intrabacterial pH homeostasis": "{organism} intrabacterial pH disruption",
    "Detection interference": "{discriminator} interference",
    "Metabolic stability": "{matrix} stability",
    "Plasma stability": "Plasma stability",
    "Plasma protein binding": "Plasma protein binding",
    "Permeability": "{cell_line?} permeability",
    "Solubility": "{discriminator?} solubility",
    "Lipophilicity": "Lipophilicity",
    "Pharmacokinetics": "{organism?} pharmacokinetics",
    "In vivo efficacy": "{organism} in vivo efficacy",
    "Compound identity / purity": "Compound identity and purity",
    "Prediction": "{subject?} {discriminator} prediction",
}


def upgrade() -> None:
    op.create_table(
        "protocol_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("name_pattern", sa.String(400), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_protocol_categories_workspace_id", "protocol_categories", ["workspace_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_protocol_category_ws_label "
        "ON protocol_categories (workspace_id, lower(label))"
    )
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "select workspace_id, terms from controlled_vocabularies "
            "where name = 'Protocol Categories'"
        )
    ).all()
    for workspace_id, terms in rows:
        for label in terms:
            pattern = DEFAULT_PATTERNS.get(label) or "{subject?} " + label[:1].lower() + label[1:]
            conn.execute(
                sa.text(
                    "insert into protocol_categories "
                    "(id, workspace_id, label, name_pattern, created_at, updated_at, version) "
                    "values (gen_random_uuid(), :ws, :label, :pattern, now(), now(), 1)"
                ),
                {"ws": workspace_id, "label": label, "pattern": pattern},
            )
    conn.execute(sa.text("delete from controlled_vocabularies where name = 'Protocol Categories'"))


def downgrade() -> None:
    # The "Protocol Categories" vocabulary is not recreated: its terms live on as categories.
    op.drop_index("uq_protocol_category_ws_label", table_name="protocol_categories")
    op.drop_index("ix_protocol_categories_workspace_id", table_name="protocol_categories")
    op.drop_table("protocol_categories")
