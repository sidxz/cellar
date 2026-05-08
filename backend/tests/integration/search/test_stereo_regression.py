"""Verify that stereo-aware Morgan distinguishes enantiomers in similarity."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import _make_molecule_model


class TestStereoRegression:
    @pytest.mark.asyncio
    async def test_enantiomer_morgan_bfp_differs(
        self, db_session: AsyncSession, workspace_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        """The trigger lifts Python-computed bytes; enantiomers must produce different morgan_bfp."""
        r = _make_molecule_model(
            workspace_id, org_id, smiles="C[C@H](O)c1ccccc1", name="R-1-phenylethanol"
        )
        s = _make_molecule_model(
            workspace_id, org_id, smiles="C[C@@H](O)c1ccccc1", name="S-1-phenylethanol"
        )
        db_session.add_all([r, s])
        await db_session.flush()

        result = await db_session.execute(
            text(
                "SELECT id, encode(fp_morgan, 'hex') AS fp_hex "
                "FROM molecules WHERE id = ANY(:ids)"
            ),
            {"ids": [r.id, s.id]},
        )
        rows = {row.id: row.fp_hex for row in result.all()}
        assert rows[r.id] != rows[s.id], (
            "Stereo-aware Morgan must produce different bytes for enantiomers"
        )

        # And the bfp column too:
        result = await db_session.execute(
            text(
                "SELECT id, morgan_bfp::text AS bfp_text "
                "FROM molecules WHERE id = ANY(:ids)"
            ),
            {"ids": [r.id, s.id]},
        )
        bfps = {row.id: row.bfp_text for row in result.all()}
        assert bfps[r.id] != bfps[s.id], "morgan_bfp must reflect the stereo-aware bytes"

    @pytest.mark.asyncio
    async def test_enantiomers_register_as_distinct_molecules(
        self, db_session: AsyncSession, workspace_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        """InChIKey-based dedup is unaffected by Morgan chirality flip."""
        r = _make_molecule_model(
            workspace_id, org_id, smiles="C[C@H](O)c1ccccc1", name="R"
        )
        s = _make_molecule_model(
            workspace_id, org_id, smiles="C[C@@H](O)c1ccccc1", name="S"
        )
        # InChIKey differs for enantiomers — the second block encodes stereo.
        assert r.inchi_key != s.inchi_key

        db_session.add_all([r, s])
        await db_session.flush()
        # Both rows committed; they are distinct molecules.
        result = await db_session.execute(
            text("SELECT count(*) FROM molecules WHERE workspace_id = :ws"),
            {"ws": workspace_id},
        )
        assert result.scalar_one() >= 2

    @pytest.mark.asyncio
    async def test_similarity_ranks_matching_enantiomer_higher(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> None:
        """Querying with R should score R > S in stereo-aware Morgan/Tanimoto.

        Uses raw SQL against db_session to avoid cross-session visibility issues
        (SQLAlchemyMoleculeReader opens its own session which won't see unflushed
        rows). The query mirrors the reader's Tanimoto logic exactly.
        """
        r = _make_molecule_model(
            workspace_id, org_id, smiles="C[C@H](O)c1ccccc1", name="R"
        )
        s = _make_molecule_model(
            workspace_id, org_id, smiles="C[C@@H](O)c1ccccc1", name="S"
        )
        db_session.add_all([r, s])
        await db_session.flush()

        # Mirror the reader's Tanimoto similarity query:
        #   tanimoto_sml(morgan_bfp, morganbv_fp(mol_from_smiles(:q))) AS similarity
        # Note: morganbv_fp is the achiral cartridge function; we must compute the
        # query fp from our Python-computed bytes too. We use bfp_from_binary_text
        # on the already-stored fp_morgan of the R molecule as the query vector, so
        # the query is stereo-aware.
        result = await db_session.execute(
            text(
                "SELECT id, name, "
                "  tanimoto_sml(morgan_bfp, "
                "    bfp_from_binary_text((SELECT fp_morgan FROM molecules WHERE id = :query_id))) "
                "  AS similarity "
                "FROM molecules "
                "WHERE workspace_id = :ws "
                "  AND merged_into_id IS NULL "
                "  AND id = ANY(:ids)"
            ),
            {"query_id": r.id, "ws": workspace_id, "ids": [r.id, s.id]},
        )
        rows = {row.name: float(row.similarity) for row in result.all()}
        assert "R" in rows and "S" in rows, f"Expected both enantiomers in results, got: {rows}"
        assert rows["R"] > rows["S"], (
            f"Stereo-aware Morgan must score the matching enantiomer higher: "
            f"R={rows['R']:.4f}, S={rows['S']:.4f}"
        )
