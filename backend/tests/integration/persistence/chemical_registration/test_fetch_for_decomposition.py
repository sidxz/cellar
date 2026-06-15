"""Integration test for SQLAlchemyMoleculeRepository.fetch_for_decomposition."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (  # noqa: E501
    SQLAlchemyMoleculeRepository,
)


async def _seed_org(uow, ws: uuid.UUID) -> uuid.UUID:
    org_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, :n, 'internal', true, 1)"
        ),
        {"id": org_id, "ws": ws, "n": f"org-{org_id.hex[:6]}"},
    )
    return org_id


async def _seed_molecule(
    uow,
    ws: uuid.UUID,
    org_id: uuid.UUID,
    *,
    reg: str,
    smiles: str | None,
    version: int = 1,
    merged_into_id: uuid.UUID | None = None,
) -> uuid.UUID:
    mol_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, "
            "molecule_type, smiles, version, originating_org_id, merged_into_id) VALUES "
            "(:id, :ws, :r, :r, 'small_molecule', :smi, :v, :org, :merged)"
        ),
        {
            "id": mol_id,
            "ws": ws,
            "r": reg,
            "smi": smiles,
            "v": version,
            "org": org_id,
            "merged": merged_into_id,
        },
    )
    return mol_id


@pytest.mark.asyncio
async def test_fetch_for_decomposition_returns_id_smiles_version(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        a = await _seed_molecule(uow, ws, org, reg="CV-A", smiles="Fc1ccccc1", version=3)
        b = await _seed_molecule(uow, ws, org, reg="CV-B", smiles="Clc1ccccc1", version=1)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyMoleculeRepository(uow)
        rows = await repo.fetch_for_decomposition(molecule_ids=[a, b], workspace_id=ws)

    by_id = {mid: (smi, ver) for (mid, smi, ver) in rows}
    assert by_id[a] == ("Fc1ccccc1", 3)
    assert by_id[b] == ("Clc1ccccc1", 1)


@pytest.mark.asyncio
async def test_fetch_for_decomposition_keeps_null_smiles_members(uow):
    ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        structureless = await _seed_molecule(uow, ws, org, reg="CV-N", smiles=None)
        await uow.commit()

    async with uow:
        repo = SQLAlchemyMoleculeRepository(uow)
        rows = await repo.fetch_for_decomposition(molecule_ids=[structureless], workspace_id=ws)

    assert len(rows) == 1
    assert rows[0][0] == structureless
    assert rows[0][1] is None  # surfaced (will become an unmatched member), not dropped


@pytest.mark.asyncio
async def test_fetch_for_decomposition_excludes_merged_and_other_workspace(uow):
    ws = uuid.uuid4()
    other_ws = uuid.uuid4()
    async with uow:
        org = await _seed_org(uow, ws)
        target = uuid.uuid4()
        merged = await _seed_molecule(
            uow, ws, org, reg="CV-M", smiles="CCO", merged_into_id=target
        )
        other_org = await _seed_org(uow, other_ws)
        foreign = await _seed_molecule(uow, other_ws, other_org, reg="CV-F", smiles="CCN")
        await uow.commit()

    async with uow:
        repo = SQLAlchemyMoleculeRepository(uow)
        rows = await repo.fetch_for_decomposition(
            molecule_ids=[merged, foreign], workspace_id=ws
        )

    assert rows == []  # merged excluded; foreign workspace excluded


@pytest.mark.asyncio
async def test_fetch_for_decomposition_empty_input_returns_empty(uow):
    async with uow:
        repo = SQLAlchemyMoleculeRepository(uow)
        assert await repo.fetch_for_decomposition(molecule_ids=[], workspace_id=uuid.uuid4()) == []
