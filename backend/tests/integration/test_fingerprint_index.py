"""Integration tests for morgan_bfp trigger and indexed similarity search."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    OrganizationModel,
)


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


def _make_molecule_model(
    workspace_id: uuid.UUID,
    org_id: uuid.UUID,
    *,
    smiles: str | None = "c1ccccc1",
    name: str = "benzene",
    reg_num: str | None = None,
) -> MoleculeModel:
    """Create a minimal MoleculeModel for testing."""
    return MoleculeModel(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        registration_number=reg_num or f"CV-{uuid.uuid4().hex[:5]}",
        name=name,
        molecule_type="small_molecule",
        smiles=smiles,
        structure_status="disclosed",
        registration_status="registered",
        synthesis_status="not_started",
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
