"""Add morgan_bfp column with trigger and GiST index for similarity search.

Revision ID: 015
Revises: 014
Create Date: 2026-04-05
"""

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add morgan_bfp column (RDKit cartridge bfp type)
    op.execute("ALTER TABLE molecules ADD COLUMN morgan_bfp bfp")

    # 2. Create trigger function that auto-computes fingerprint from SMILES
    op.execute("""
        CREATE OR REPLACE FUNCTION compute_morgan_bfp()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.smiles IS NOT NULL THEN
                BEGIN
                    NEW.morgan_bfp := morganbv_fp(mol_from_smiles(NEW.smiles));
                EXCEPTION WHEN OTHERS THEN
                    NEW.morgan_bfp := NULL;
                END;
            ELSE
                NEW.morgan_bfp := NULL;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    # 3. Create trigger on INSERT or UPDATE of smiles column
    op.execute("""
        CREATE TRIGGER trg_compute_morgan_bfp
        BEFORE INSERT OR UPDATE OF smiles ON molecules
        FOR EACH ROW
        EXECUTE FUNCTION compute_morgan_bfp()
    """)

    # 4. GiST index on morgan_bfp for Tanimoto % operator
    op.execute(
        "CREATE INDEX ix_molecules_morgan_bfp ON molecules USING gist (morgan_bfp)"
    )

    # 5. Populate existing disclosed molecules (trigger fires on UPDATE of smiles)
    op.execute(
        "UPDATE molecules SET smiles = smiles WHERE smiles IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_compute_morgan_bfp ON molecules")
    op.execute("DROP FUNCTION IF EXISTS compute_morgan_bfp()")
    op.execute("DROP INDEX IF EXISTS ix_molecules_morgan_bfp")
    op.execute("ALTER TABLE molecules DROP COLUMN IF EXISTS morgan_bfp")
