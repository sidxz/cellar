"""Round-trip: composer SQL must execute against the real cartridge.

These tests are the *binding-layer* gate for the search composer. Unit tests
verify the SQL text shape; these tests verify the SQL actually executes via
the asyncpg driver against the RDKit cartridge — catching bind-type
mismatches that don't surface until the wire format is negotiated.

Concretely: ``text(...).bindparams(q=value)`` infers Python str -> VARCHAR,
which asyncpg sends as ``character varying``. The cartridge's
``qmol_from_smarts`` and ``mol_from_smiles`` only accept ``cstring``, with
no implicit cast. Postgres rejects the call with::

    function qmol_from_smarts(character varying) does not exist

Unit tests can't see this because they compile with literal_binds (no driver
roundtrip). These tests pin the contract by composing the SQL exactly the
way the production code path does, then executing it.

ANY new clause shape that talks to the cartridge MUST have a test in this
file. Don't trust unit tests alone for cartridge-touching SQL.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (
    compose_criteria,
)

from .conftest import _make_molecule_model


@pytest.fixture
async def benzene(
    db_session: AsyncSession, workspace_id: uuid.UUID, org_id: uuid.UUID
) -> MoleculeModel:
    """A registered benzene with stereo-aware fp_morgan, used for hit assertions."""
    m = _make_molecule_model(workspace_id, org_id, smiles="c1ccccc1", name="benzene")
    db_session.add(m)
    await db_session.flush()
    return m


async def _execute_clause(
    db_session: AsyncSession,
    workspace_id: uuid.UUID,
    query: dict,
) -> list[uuid.UUID]:
    """Compose a query through the production composer and execute it."""
    clause = compose_criteria(query, workspace_id=workspace_id)
    stmt = select(MoleculeModel.id).where(
        MoleculeModel.workspace_id == workspace_id,
        MoleculeModel.merged_into_id.is_(None),
        MoleculeModel.smiles.is_not(None),
    )
    if clause is not None:
        stmt = stmt.where(clause)
    result = await db_session.execute(stmt)
    return [row.id for row in result.all()]


# ─── Substructure ──────────────────────────────────────────────────────────


class TestSubstructureExecutes:
    """Each substructure variant must execute without driver-level errors.

    The bug class this guards against: SQLAlchemy bindparam typing pushing
    VARCHAR/BYTEA where the cartridge needs cstring/bfp.
    """

    @pytest.mark.asyncio
    async def test_strict_substructure_kind_form(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        benzene: MoleculeModel,
    ) -> None:
        ids = await _execute_clause(
            db_session,
            workspace_id,
            {"criteria": [{
                "type": "structure",
                "kind": "substructure",
                "smiles_or_smarts": "c1ccccc1",
            }]},
        )
        assert benzene.id in ids

    @pytest.mark.asyncio
    async def test_strict_substructure_legacy_search_type(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        benzene: MoleculeModel,
    ) -> None:
        """Legacy {search_type, smarts} shape must continue to execute."""
        ids = await _execute_clause(
            db_session,
            workspace_id,
            {"criteria": [{
                "type": "structure",
                "search_type": "substructure",
                "smarts": "c1ccccc1",
            }]},
        )
        assert benzene.id in ids

    @pytest.mark.asyncio
    async def test_generalized_substructure(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        benzene: MoleculeModel,
    ) -> None:
        """@>> + mol_to_xqmol path. Asserts execution, not specific hits."""
        ids = await _execute_clause(
            db_session,
            workspace_id,
            {"criteria": [{
                "type": "structure",
                "kind": "substructure",
                "smiles_or_smarts": "c1ccccc1",
                "generalized": True,
            }]},
        )
        # Generalized must include strict matches, so benzene must appear.
        assert benzene.id in ids

    @pytest.mark.asyncio
    async def test_substructure_in_nested_group(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        benzene: MoleculeModel,
    ) -> None:
        """Group-recursion path must produce executable SQL too."""
        ids = await _execute_clause(
            db_session,
            workspace_id,
            {"criteria": [{
                "type": "group",
                "logic": "and",
                "criteria": [
                    {"type": "structure", "kind": "substructure",
                     "smiles_or_smarts": "c1ccccc1"},
                ],
            }]},
        )
        assert benzene.id in ids

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kekule_query",
        [
            "C1=CC=CC=C1",  # Kekulé SMILES
            "[#6]1-[#6]=[#6]-[#6]=[#6]-[#6]=1",  # exact Ketcher SMARTS export
        ],
    )
    async def test_kekule_benzene_matches_aromatic_storage(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        benzene: MoleculeModel,
        kekule_query: str,
    ) -> None:
        """Regression: a chemist drawing benzene in Ketcher exports Kekulé
        SMARTS. The cartridge stores molecules with aromaticity perceived,
        so explicit -/= bonds in the query never match aromatic bonds in
        storage without query-side aromatization. Without the normalizer,
        these queries return zero hits — the most common medchem search
        appears completely broken.
        """
        ids = await _execute_clause(
            db_session,
            workspace_id,
            {"criteria": [{
                "type": "structure",
                "kind": "substructure",
                "smiles_or_smarts": kekule_query,
            }]},
        )
        assert benzene.id in ids, (
            f"Kekulé query {kekule_query!r} failed to match aromatic-stored "
            f"benzene — query-side aromatization regression"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "smiles_query",
        ["c1ccccc1", "C1=CC=CC=C1"],
    )
    async def test_smiles_kind_path_matches_benzene(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        benzene: MoleculeModel,
        smiles_query: str,
    ) -> None:
        """SMILES dispatch: cartridge parses query via mol_from_smiles —
        aromaticity perception happens cartridge-side on both halves of
        the @> match. This is the path the new FE uses for plain drawn
        structures."""
        ids = await _execute_clause(
            db_session,
            workspace_id,
            {"criteria": [{
                "type": "structure",
                "kind": "substructure",
                "query_kind": "smiles",
                "smiles_or_smarts": smiles_query,
            }]},
        )
        assert benzene.id in ids

    @pytest.mark.asyncio
    async def test_smarts_kind_with_atom_list_executes(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        benzene: MoleculeModel,
    ) -> None:
        """SMARTS-only feature (atom list) survives the SMARTS dispatch —
        chemist's '4-halo-phenyl' style query."""
        ids = await _execute_clause(
            db_session,
            workspace_id,
            {"criteria": [{
                "type": "structure",
                "kind": "substructure",
                "query_kind": "smarts",
                "smiles_or_smarts": "[#6]1[#6][#6][#6][#6][#6]1",
            }]},
        )
        # Benzene matches "ring of 6 carbons" (no bond-order constraint).
        assert benzene.id in ids

    @pytest.mark.asyncio
    async def test_generalized_smiles_path_matches_benzene(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        benzene: MoleculeModel,
    ) -> None:
        """Generalized + SMILES: tautomer/variant matching path. This
        capability (the 'Match across tautomers and structural variants'
        toggle) only works correctly when the query reaches the cartridge
        as SMILES so mol_to_xqmol can expand it; SMARTS-tagged inputs are
        rejected at the API edge."""
        ids = await _execute_clause(
            db_session,
            workspace_id,
            {"criteria": [{
                "type": "structure",
                "kind": "substructure",
                "query_kind": "smiles",
                "smiles_or_smarts": "c1ccccc1",
                "generalized": True,
            }]},
        )
        assert benzene.id in ids


# ─── Similarity ────────────────────────────────────────────────────────────


class TestSimilarityExecutes:
    """Each similarity mode + algorithm + metric combination must execute."""

    @pytest.mark.asyncio
    async def test_similar_mode_morgan_tanimoto(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        benzene: MoleculeModel,
    ) -> None:
        ids = await _execute_clause(
            db_session,
            workspace_id,
            {"criteria": [{
                "type": "structure",
                "kind": "similarity",
                "smiles": "c1ccccc1",
                "mode": "similar",
            }]},
        )
        assert benzene.id in ids

    @pytest.mark.asyncio
    async def test_scaffold_hop_mode_fcfp_tanimoto(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        benzene: MoleculeModel,
    ) -> None:
        """FCFP path uses cartridge featmorganbv_fp; must accept str query via CAST."""
        ids = await _execute_clause(
            db_session,
            workspace_id,
            {"criteria": [{
                "type": "structure",
                "kind": "similarity",
                "smiles": "c1ccccc1",
                "mode": "scaffold_hop",
            }]},
        )
        assert benzene.id in ids

    @pytest.mark.asyncio
    async def test_fragment_in_target_mode_morgan_tversky(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        benzene: MoleculeModel,
    ) -> None:
        """Tversky on Morgan: bytes path via bfp_from_binary_text."""
        ids = await _execute_clause(
            db_session,
            workspace_id,
            {"criteria": [{
                "type": "structure",
                "kind": "similarity",
                "smiles": "c1ccccc1",
                "mode": "fragment_in_target",
            }]},
        )
        assert benzene.id in ids

    @pytest.mark.asyncio
    async def test_legacy_similarity_shape(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        benzene: MoleculeModel,
    ) -> None:
        """Pre-discriminator {search_type, smiles, threshold} shape."""
        ids = await _execute_clause(
            db_session,
            workspace_id,
            {"criteria": [{
                "type": "structure",
                "search_type": "similarity",
                "smiles": "c1ccccc1",
                "threshold": 0.5,
            }]},
        )
        assert benzene.id in ids

    @pytest.mark.asyncio
    async def test_explicit_algorithm_metric_override(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        benzene: MoleculeModel,
    ) -> None:
        """Power-user path: algorithm + metric + threshold without mode."""
        ids = await _execute_clause(
            db_session,
            workspace_id,
            {"criteria": [{
                "type": "structure",
                "kind": "similarity",
                "smiles": "c1ccccc1",
                "algorithm": "fcfp",
                "metric": {"kind": "tanimoto"},
                "threshold": 0.4,
            }]},
        )
        assert benzene.id in ids


# ─── Exact ─────────────────────────────────────────────────────────────────


class TestExactExecutes:
    @pytest.mark.asyncio
    async def test_exact_inchi_key(
        self,
        db_session: AsyncSession,
        workspace_id: uuid.UUID,
        benzene: MoleculeModel,
    ) -> None:
        ids = await _execute_clause(
            db_session,
            workspace_id,
            {"criteria": [{
                "type": "structure",
                "kind": "exact",
                "inchi_key": benzene.inchi_key,
            }]},
        )
        assert benzene.id in ids
