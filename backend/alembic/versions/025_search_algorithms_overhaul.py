"""search algorithms overhaul: stereo-aware Morgan + FCFP + cleanup.

- Drop unused Python-side fingerprint columns (fp_rdkit, fp_maccs,
  fp_topological_torsion, fp_atom_pair).
- Drop the achiral cartridge trigger that computed morgan_bfp from smiles.
- Replace with a trigger that lifts Python-computed bytes (in fp_morgan)
  into morgan_bfp via bfp_from_binary_text.
- Add fcfp_bfp column with cartridge trigger from smiles + GiST index.

Revision ID: 020_search_algorithms_overhaul
Revises: 019_pos_control_signal_on_protocol
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "020_search_algorithms_overhaul"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop unused Python-side fingerprint columns.
    op.drop_column("molecules", "fp_rdkit")
    op.drop_column("molecules", "fp_maccs")
    op.drop_column("molecules", "fp_topological_torsion")
    op.drop_column("molecules", "fp_atom_pair")

    # 2. Drop the old achiral Morgan trigger and helper function (from migration 001).
    op.execute("DROP TRIGGER IF EXISTS trg_compute_morgan_bfp ON molecules")
    op.execute("DROP FUNCTION IF EXISTS compute_morgan_bfp()")

    # 3. New trigger: lift Python-computed bytes (fp_morgan) into morgan_bfp.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sync_morgan_bfp() RETURNS trigger AS $$
        BEGIN
            IF NEW.fp_morgan IS NULL THEN
                NEW.morgan_bfp := NULL;
            ELSE
                NEW.morgan_bfp := bfp_from_binary_text(NEW.fp_morgan);
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_sync_morgan_bfp
        BEFORE INSERT OR UPDATE OF fp_morgan ON molecules
        FOR EACH ROW EXECUTE FUNCTION sync_morgan_bfp();
        """
    )

    # 4. Add fcfp_bfp + GiST index + cartridge-managed trigger.
    op.execute("ALTER TABLE molecules ADD COLUMN fcfp_bfp bfp")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION compute_fcfp_bfp() RETURNS trigger AS $$
        BEGIN
            IF NEW.smiles IS NULL THEN
                NEW.fcfp_bfp := NULL;
            ELSE
                BEGIN
                    NEW.fcfp_bfp := featmorganbv_fp(mol_from_smiles(NEW.smiles), 2);
                EXCEPTION WHEN OTHERS THEN
                    NEW.fcfp_bfp := NULL;
                END;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_compute_fcfp_bfp
        BEFORE INSERT OR UPDATE OF smiles ON molecules
        FOR EACH ROW EXECUTE FUNCTION compute_fcfp_bfp();
        """
    )
    op.execute(
        "CREATE INDEX ix_molecules_fcfp_bfp ON molecules USING gist (fcfp_bfp)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_molecules_fcfp_bfp")
    op.execute("DROP TRIGGER IF EXISTS trg_compute_fcfp_bfp ON molecules")
    op.execute("DROP FUNCTION IF EXISTS compute_fcfp_bfp()")
    op.execute("ALTER TABLE molecules DROP COLUMN IF EXISTS fcfp_bfp")

    op.execute("DROP TRIGGER IF EXISTS trg_sync_morgan_bfp ON molecules")
    op.execute("DROP FUNCTION IF EXISTS sync_morgan_bfp()")

    # Restore the original achiral Morgan trigger from migration 001.
    op.execute(
        """
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
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_compute_morgan_bfp
        BEFORE INSERT OR UPDATE OF smiles ON molecules
        FOR EACH ROW EXECUTE FUNCTION compute_morgan_bfp()
        """
    )

    # Restore deleted columns.
    op.add_column("molecules", sa.Column("fp_atom_pair", sa.LargeBinary, nullable=True))
    op.add_column("molecules", sa.Column("fp_topological_torsion", sa.LargeBinary, nullable=True))
    op.add_column("molecules", sa.Column("fp_maccs", sa.LargeBinary, nullable=True))
    op.add_column("molecules", sa.Column("fp_rdkit", sa.LargeBinary, nullable=True))
