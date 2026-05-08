"""Each SearchMode round-trips through the cartridge with sensible ranking.

Architecture note: ``morgan_bfp`` is populated from Python-computed stereo-aware
Morgan bytes via ``bfp_from_binary_text(fp_morgan)``.  This format is NOT
cross-comparable with ``morganbv_fp(mol_from_smiles(...))``, which is the
achiral cartridge function.  The correct way to build a query vector for
``morgan_bfp`` columns is ``bfp_from_binary_text(:q_bytes)`` where ``q_bytes``
are computed by ``MorganAlgorithm.compute_bytes`` — the same path used by the
production reader after the bfp_from_binary_text fix.

``fcfp_bfp`` is populated by a DB trigger using ``featmorganbv_fp(smiles, 2)``,
so querying via ``featmorganbv_fp(mol_from_smiles(:q), 2)`` IS cross-compatible.
"""

from __future__ import annotations

import uuid

import pytest
from rdkit import Chem
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm

from .conftest import _make_molecule_model

_morgan = MorganAlgorithm()


@pytest.fixture
async def small_corpus(
    db_session: AsyncSession, workspace_id: uuid.UUID, org_id: uuid.UUID
) -> dict[str, uuid.UUID]:
    """Three molecules: ethanol, isopropanol, benzene. Returns name->id."""
    ethanol = _make_molecule_model(workspace_id, org_id, smiles="CCO", name="ethanol")
    isopropanol = _make_molecule_model(
        workspace_id, org_id, smiles="CC(C)O", name="isopropanol"
    )
    benzene = _make_molecule_model(
        workspace_id, org_id, smiles="c1ccccc1", name="benzene"
    )
    db_session.add_all([ethanol, isopropanol, benzene])
    await db_session.flush()
    return {
        "ethanol": ethanol.id,
        "isopropanol": isopropanol.id,
        "benzene": benzene.id,
    }


class TestSimilarMode:
    """SearchMode.SIMILAR — morgan_bfp + tanimoto.

    Query vector is computed in Python via ``MorganAlgorithm.compute_bytes`` and
    passed to the cartridge via ``bfp_from_binary_text(:q_bytes)``.  This mirrors
    the production reader exactly and is the only format compatible with the
    ``morgan_bfp`` column (see module docstring).
    """

    @pytest.mark.asyncio
    async def test_self_similarity_is_max_and_topology_orders_above_alien(
        self,
        small_corpus: dict[str, uuid.UUID],
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> None:
        # Compute query bytes in Python — same path as the production reader.
        ethanol_mol = Chem.MolFromSmiles("CCO")
        q_bytes = _morgan.compute_bytes(ethanol_mol)

        result = await db_session.execute(
            text(
                "SELECT id, name, "
                "tanimoto_sml(morgan_bfp, bfp_from_binary_text(:q_bytes)) AS score "
                "FROM molecules WHERE workspace_id = :ws "
                "ORDER BY score DESC NULLS LAST"
            ),
            {"q_bytes": q_bytes, "ws": workspace_id},
        )
        rows = result.all()
        scores = {row.name: float(row.score) for row in rows}
        # Self-similarity must be 1.0 (query fp == stored fp).
        assert scores["ethanol"] == pytest.approx(1.0, abs=1e-6), (
            f"Expected ethanol self-similarity 1.0, got {scores['ethanol']}"
        )
        # Aliphatic alcohol (isopropanol) should rank above unrelated aromatic (benzene).
        assert scores["isopropanol"] > scores["benzene"], (
            f"isopropanol={scores['isopropanol']} should exceed benzene={scores['benzene']}"
        )


class TestScaffoldHopMode:
    """SearchMode.SCAFFOLD_HOP — fcfp_bfp + tanimoto.

    ``fcfp_bfp`` is populated by the DB trigger using ``featmorganbv_fp(smiles, 2)``,
    so querying via the same cartridge function IS cross-compatible.
    """

    @pytest.mark.asyncio
    async def test_fcfp_returns_scores_and_self_match_is_max(
        self,
        small_corpus: dict[str, uuid.UUID],
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> None:
        result = await db_session.execute(
            text(
                "SELECT id, name, "
                "tanimoto_sml(fcfp_bfp, featmorganbv_fp(mol_from_smiles(:q), 2)) AS score "
                "FROM molecules WHERE workspace_id = :ws "
                "ORDER BY score DESC NULLS LAST"
            ),
            {"q": "CCO", "ws": workspace_id},
        )
        rows = result.all()
        scores = {row.name: float(row.score) for row in rows}
        # Self should be max under FCFP too.
        assert scores["ethanol"] >= scores["isopropanol"]
        assert scores["ethanol"] >= scores["benzene"]
        # Ethanol should self-match exactly — same SMILES used to build both fps.
        assert scores["ethanol"] == pytest.approx(1.0, abs=1e-6), (
            f"FCFP self-similarity should be 1.0, got {scores['ethanol']}"
        )


class TestFragmentInTargetMode:
    """SearchMode.FRAGMENT_IN_TARGET — morgan_bfp + tversky(α=1, β=0).

    Tversky(1, 0) = |A ∩ B| / (|A ∩ B| + |A − B|) — i.e., fraction of query
    features present in target.  Here A = target ``morgan_bfp``, B = query fp.
    With α=1 and query==stored fp this reduces to |fp| / |fp| = 1.0.

    Query vector is computed in Python via ``MorganAlgorithm.compute_bytes`` and
    passed as ``bfp_from_binary_text(:q_bytes)`` — same pattern as the reader.
    """

    @pytest.mark.asyncio
    async def test_tversky_fragment_query_returns_scores(
        self,
        small_corpus: dict[str, uuid.UUID],
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
    ) -> None:
        # Compute query bytes in Python — same path as the production reader.
        ethanol_mol = Chem.MolFromSmiles("CCO")
        q_bytes = _morgan.compute_bytes(ethanol_mol)

        result = await db_session.execute(
            text(
                "SELECT id, name, "
                "tversky_sml(morgan_bfp, bfp_from_binary_text(:q_bytes), 1.0, 0.0) AS score "
                "FROM molecules WHERE workspace_id = :ws "
                "ORDER BY score DESC NULLS LAST"
            ),
            {"q_bytes": q_bytes, "ws": workspace_id},
        )
        rows = result.all()
        scores = {row.name: float(row.score) for row in rows}
        # Self should max out: all query features are present in the identical target.
        assert scores["ethanol"] == pytest.approx(1.0, abs=1e-6), (
            f"Tversky(α=1,β=0) self-similarity should be 1.0, got {scores['ethanol']}"
        )
        # Tversky(1,0): fraction-of-query-in-target.
        # Ethanol (smaller query) should score >= isopropanol against itself
        # because isopropanol has all ethanol's atoms plus extras.
        # (|ethanol ∩ isopropanol| / |ethanol ∩ isopropanol| + |ethanol - isopropanol|)
        # Benzene shares no aliphatic features, so scores lowest.
        assert scores["ethanol"] >= scores["isopropanol"]
        assert scores["isopropanol"] > scores["benzene"], (
            f"isopropanol={scores['isopropanol']} should exceed benzene={scores['benzene']}"
        )
