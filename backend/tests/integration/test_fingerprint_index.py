"""Integration tests for morgan_bfp trigger and indexed similarity search."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    OrganizationModel,
)


class _FakeUoW:
    """Minimal UoW shim that wraps a test session for repository construction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    def track(self, aggregate: object) -> None:  # noqa: ARG002
        pass


@pytest.fixture
async def org_id(db_session: AsyncSession, workspace_id: uuid.UUID) -> uuid.UUID:
    """Create a minimal Organization row to satisfy the FK on molecules."""
    oid = uuid.uuid4()
    org = OrganizationModel(
        id=oid,
        workspace_id=workspace_id,
        name=f"TestOrg-{oid.hex[:6]}",
        org_type="internal",
        is_active=True,
        version=1,
    )
    db_session.add(org)
    await db_session.flush()
    return oid


# Minimal structure + descriptor data for each test SMILES so ChemicalStructure
# and ComputedDescriptors VOs validate (both require all-null or all-populated).
_MOLECULE_DATA: dict[str, dict[str, object]] = {
    "c1ccccc1": {
        # ChemicalStructure fields
        "cxsmiles": "c1ccccc1",
        "inchi": "InChI=1S/C6H6/c1-2-4-6-5-3-1/h1-6H",
        "inchi_key": "UHOVQNZJYSORNB-UHFFFAOYSA-N",
        "molfile": "benzene",
        # ComputedDescriptors fields
        "molecular_formula": "C6H6",
        "molecular_weight": 78.11,
        "exact_mass": 78.047,
        "logp": 1.56,
        "tpsa": 0.0,
        "hbd": 0,
        "hba": 0,
        "rotatable_bonds": 0,
        "aromatic_rings": 1,
        "ring_count": 1,
        "heavy_atom_count": 6,
        "ro5_violations": 0,
    },
    "Cc1ccccc1": {
        "cxsmiles": "Cc1ccccc1",
        "inchi": "InChI=1S/C7H8/c1-7-5-3-2-4-6-7/h2-6H,1H3",
        "inchi_key": "YXFVVABEGXRONW-UHFFFAOYSA-N",
        "molfile": "toluene",
        "molecular_formula": "C7H8",
        "molecular_weight": 92.14,
        "exact_mass": 92.063,
        "logp": 2.07,
        "tpsa": 0.0,
        "hbd": 0,
        "hba": 0,
        "rotatable_bonds": 0,
        "aromatic_rings": 1,
        "ring_count": 1,
        "heavy_atom_count": 7,
        "ro5_violations": 0,
    },
    "CCO": {
        "cxsmiles": "CCO",
        "inchi": "InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3",
        "inchi_key": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
        "molfile": "ethanol",
        "molecular_formula": "C2H6O",
        "molecular_weight": 46.07,
        "exact_mass": 46.042,
        "logp": -0.31,
        "tpsa": 20.23,
        "hbd": 1,
        "hba": 1,
        "rotatable_bonds": 0,
        "aromatic_rings": 0,
        "ring_count": 0,
        "heavy_atom_count": 3,
        "ro5_violations": 0,
    },
}


def _make_molecule_model(
    workspace_id: uuid.UUID,
    org_id: uuid.UUID,
    *,
    smiles: str | None = "c1ccccc1",
    name: str = "benzene",
    reg_num: str | None = None,
) -> MoleculeModel:
    """Create a minimal MoleculeModel for testing."""
    extra: dict[str, object] = {}
    if smiles and smiles in _MOLECULE_DATA:
        extra = dict(_MOLECULE_DATA[smiles])
    return MoleculeModel(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        registration_number=reg_num or f"CV-{uuid.uuid4().hex[:5]}",
        name=name,
        molecule_type="small_molecule",
        smiles=smiles,
        # ChemicalStructure fields
        cxsmiles=extra.get("cxsmiles"),
        inchi=extra.get("inchi"),
        inchi_key=extra.get("inchi_key"),
        molfile=extra.get("molfile"),
        # ComputedDescriptors fields
        molecular_formula=extra.get("molecular_formula"),
        molecular_weight=extra.get("molecular_weight"),
        exact_mass=extra.get("exact_mass"),
        logp=extra.get("logp"),
        tpsa=extra.get("tpsa"),
        hbd=extra.get("hbd"),
        hba=extra.get("hba"),
        rotatable_bonds=extra.get("rotatable_bonds"),
        aromatic_rings=extra.get("aromatic_rings"),
        ring_count=extra.get("ring_count"),
        heavy_atom_count=extra.get("heavy_atom_count"),
        ro5_violations=extra.get("ro5_violations"),
        structure_status="disclosed",
        registration_status="approved",
        synthesis_status="virtual",
        lifecycle_stage="active",
        originating_org_id=org_id,
        version=1,
    )


class TestMorganBfpTrigger:
    """Verify the DB trigger computes morgan_bfp from smiles."""

    @pytest.mark.asyncio
    async def test_trigger_computes_fingerprint_on_insert(
        self, db_session: AsyncSession, workspace_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        mol = _make_molecule_model(workspace_id, org_id, smiles="c1ccccc1")
        db_session.add(mol)
        await db_session.flush()

        result = await db_session.execute(
            text("SELECT morgan_bfp IS NOT NULL AS has_fp FROM molecules WHERE id = :id"),
            {"id": mol.id},
        )
        assert result.scalar_one() is True

    @pytest.mark.asyncio
    async def test_trigger_sets_null_for_no_smiles(
        self, db_session: AsyncSession, workspace_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        mol = _make_molecule_model(workspace_id, org_id, smiles=None)
        db_session.add(mol)
        await db_session.flush()

        result = await db_session.execute(
            text("SELECT morgan_bfp IS NULL AS no_fp FROM molecules WHERE id = :id"),
            {"id": mol.id},
        )
        assert result.scalar_one() is True

    @pytest.mark.asyncio
    async def test_trigger_recomputes_on_smiles_update(
        self, db_session: AsyncSession, workspace_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        mol = _make_molecule_model(workspace_id, org_id, smiles=None)
        db_session.add(mol)
        await db_session.flush()

        # Simulate disclosure: set SMILES
        await db_session.execute(
            text("UPDATE molecules SET smiles = :s WHERE id = :id"),
            {"s": "CCO", "id": mol.id},
        )
        await db_session.flush()

        result = await db_session.execute(
            text("SELECT morgan_bfp IS NOT NULL AS has_fp FROM molecules WHERE id = :id"),
            {"id": mol.id},
        )
        assert result.scalar_one() is True

    @pytest.mark.asyncio
    async def test_trigger_clears_on_smiles_null(
        self, db_session: AsyncSession, workspace_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        mol = _make_molecule_model(workspace_id, org_id, smiles="c1ccccc1")
        db_session.add(mol)
        await db_session.flush()

        # Simulate merge tombstone: clear SMILES
        await db_session.execute(
            text("UPDATE molecules SET smiles = NULL WHERE id = :id"),
            {"id": mol.id},
        )
        await db_session.flush()

        result = await db_session.execute(
            text("SELECT morgan_bfp IS NULL AS no_fp FROM molecules WHERE id = :id"),
            {"id": mol.id},
        )
        assert result.scalar_one() is True


class TestIndexedSimilaritySearch:
    """End-to-end tests for similarity search via SQLAlchemyMoleculeRepository."""

    @pytest.mark.asyncio
    async def test_similarity_search_returns_scored_results(
        self, db_session: AsyncSession, workspace_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        """Insert benzene, toluene, ethanol; search for benzene-like molecules.

        Uses a low threshold (0.1) because Morgan fingerprint Tanimoto
        between small molecules like benzene/toluene can be modest (~0.2-0.3)
        depending on RDKit radius/nbits defaults.
        """
        benzene = _make_molecule_model(workspace_id, org_id, smiles="c1ccccc1", name="benzene")
        toluene = _make_molecule_model(workspace_id, org_id, smiles="Cc1ccccc1", name="toluene")
        ethanol = _make_molecule_model(workspace_id, org_id, smiles="CCO", name="ethanol")
        db_session.add_all([benzene, toluene, ethanol])
        await db_session.flush()

        repo = SQLAlchemyMoleculeRepository(_FakeUoW(db_session))  # type: ignore[arg-type]
        results = await repo.search_similarity(workspace_id, "c1ccccc1", threshold=0.1)

        # Should be list[tuple[Molecule, float]]
        assert isinstance(results, list)
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
        assert all(isinstance(r[0], Molecule) and isinstance(r[1], float) for r in results)

        # At least benzene + toluene should be in results at threshold 0.1
        result_ids = {r[0].id for r in results}
        assert benzene.id in result_ids, "Benzene (exact match) should be in results"
        assert toluene.id in result_ids, "Toluene (close analog) should be in results"

        # Benzene self-similarity should be ~1.0
        benzene_score = next(r[1] for r in results if r[0].id == benzene.id)
        assert benzene_score > 0.99, f"Benzene self-similarity should be ~1.0, got {benzene_score}"

        # Toluene should have meaningful (non-trivial) similarity to benzene
        toluene_score = next(r[1] for r in results if r[0].id == toluene.id)
        assert toluene_score > 0.1, f"Toluene similarity should exceed threshold, got {toluene_score}"

        # Toluene should be more similar to benzene than ethanol (if ethanol appears)
        ethanol_hits = [r[1] for r in results if r[0].id == ethanol.id]
        if ethanol_hits:
            assert toluene_score > ethanol_hits[0], "Toluene should be more similar to benzene than ethanol"

        # Results should be sorted descending by score
        scores = [r[1] for r in results]
        assert scores == sorted(scores, reverse=True), "Results should be sorted by descending similarity"

    @pytest.mark.asyncio
    async def test_similarity_search_workspace_isolation(
        self, db_session: AsyncSession, org_id: uuid.UUID
    ) -> None:
        """Molecules in workspace B must not appear in workspace A results."""
        ws_a = uuid.uuid4()
        ws_b = uuid.uuid4()

        # Create separate orgs for each workspace (FK constraint)
        org_b_id = uuid.uuid4()
        org_b = OrganizationModel(
            id=org_b_id,
            workspace_id=ws_b,
            name=f"OrgB-{org_b_id.hex[:6]}",
            org_type="internal",
            is_active=True,
            version=1,
        )
        db_session.add(org_b)
        await db_session.flush()

        mol_a = _make_molecule_model(ws_a, org_id, smiles="c1ccccc1", name="benzene-A")
        mol_b = _make_molecule_model(ws_b, org_b_id, smiles="c1ccccc1", name="benzene-B")
        db_session.add_all([mol_a, mol_b])
        await db_session.flush()

        repo = SQLAlchemyMoleculeRepository(_FakeUoW(db_session))  # type: ignore[arg-type]
        results = await repo.search_similarity(ws_a, "c1ccccc1", threshold=0.3)

        result_ids = {r[0].id for r in results}
        assert mol_a.id in result_ids, "Workspace A molecule should be in results"
        assert mol_b.id not in result_ids, "Workspace B molecule must NOT appear in workspace A search"

    @pytest.mark.asyncio
    async def test_similarity_search_excludes_tombstones(
        self, db_session: AsyncSession, workspace_id: uuid.UUID, org_id: uuid.UUID
    ) -> None:
        """Tombstone molecules (merged_into_id set) should be excluded from results."""
        active = _make_molecule_model(workspace_id, org_id, smiles="c1ccccc1", name="active-mol")
        tombstone = _make_molecule_model(workspace_id, org_id, smiles="c1ccccc1", name="tombstone-mol")
        tombstone.merged_into_id = active.id  # Mark as merged tombstone
        db_session.add_all([active, tombstone])
        await db_session.flush()

        repo = SQLAlchemyMoleculeRepository(_FakeUoW(db_session))  # type: ignore[arg-type]
        results = await repo.search_similarity(workspace_id, "c1ccccc1", threshold=0.3)

        result_ids = {r[0].id for r in results}
        assert active.id in result_ids, "Active molecule should be in results"
        assert tombstone.id not in result_ids, "Tombstone molecule must be excluded from results"
