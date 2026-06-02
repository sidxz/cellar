"""Integration tests for entity_exists_in_workspace + the link-repo provider."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from cellar.domain.workspace_config.tagging.tag import TaggableEntityType
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    MoleculeTagLinkRepository,
    SQLAlchemyTagLinkRepositoryProvider,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def _insert_org_and_molecule(
    uow: AsyncUnitOfWork, workspace_id: uuid.UUID, reg: str
) -> uuid.UUID:
    org_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, "
            "is_active, version) VALUES (:id, :ws, :name, 'internal', true, 1)"
        ),
        {"id": org_id, "ws": workspace_id, "name": f"org-{reg}"},
    )
    mol_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, "
            "molecule_type, version, originating_org_id) VALUES "
            "(:id, :ws, :reg, :name, 'small_molecule', 1, :org)"
        ),
        {"id": mol_id, "ws": workspace_id, "reg": reg, "name": reg, "org": org_id},
    )
    return mol_id


class TestEntityExistsAndProvider:
    async def test_entity_exists_in_workspace(self, uow: AsyncUnitOfWork) -> None:
        ws_id, other_ws = uuid.uuid4(), uuid.uuid4()
        async with uow:
            mol_id = await _insert_org_and_molecule(uow, ws_id, "EX-1")
            await uow.commit()
        async with uow:
            repo = MoleculeTagLinkRepository(uow)
            assert await repo.entity_exists_in_workspace(ws_id, mol_id) is True
            assert await repo.entity_exists_in_workspace(other_ws, mol_id) is False
            assert await repo.entity_exists_in_workspace(ws_id, uuid.uuid4()) is False

    async def test_provider_returns_bound_repo(self, uow: AsyncUnitOfWork) -> None:
        provider = SQLAlchemyTagLinkRepositoryProvider(uow)
        repo = provider.for_type(TaggableEntityType.MOLECULE)
        assert isinstance(repo, MoleculeTagLinkRepository)
        assert repo._uow is uow
