"""CreateCollection with more molecules than one statement may bind parameters for.

asyncpg refuses a statement with more than 32,767 bind parameters; a workbench
selection can hold up to 100,000 compounds.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from cellar.application.research_organization.create_collection import (
    CreateCollection,
    CreateCollectionCommand,
)
from cellar.application.shared.molecule_resolver import MoleculeResolver
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration import (
    molecule_repository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization import (
    collection_repository,
)
from tests.fakes.fake_auth import FakeAuth
from tests.integration import _screening_seed as seed

pytestmark = pytest.mark.asyncio

N = 20_000

_INSERT_MOLECULES = sa.text(
    "INSERT INTO molecules (id, workspace_id, name, molecule_type, structure_status, "
    "registration_status, synthesis_status, lifecycle_stage, registration_number, "
    "originating_org_id, version) "
    "SELECT gen_random_uuid(), :ws, 'm' || g, 'small_molecule', 'undisclosed', 'approved', "
    "'virtual', 'registered', :tag || g, :org, 1 "
    "FROM generate_series(1, :n) g RETURNING id"
)


async def test_find_molecules_by_more_ids_than_bind_parameters(uow, workspace_id):
    async with uow:
        repo = molecule_repository.SQLAlchemyMoleculeRepository(uow)
        assert await repo.find_by_ids(workspace_id, [uuid.uuid4() for _ in range(40_000)]) == []


async def test_create_collection_with_20000_molecules(uow, workspace_id):
    async with uow:
        s = uow.session
        org = await seed.org(s, workspace_id)
        tag = f"CV-{uuid.uuid4().hex[:6]}-"
        inserted = await s.execute(
            _INSERT_MOLECULES, {"ws": workspace_id, "org": org, "n": N, "tag": tag}
        )
        ids = tuple(inserted.scalars())
        await uow.commit()
    molecules = molecule_repository.SQLAlchemyMoleculeRepository(uow)
    uc = CreateCollection(
        uow,
        collection_repository.SQLAlchemyCollectionRepository(uow),
        EventDispatcher(),
        MoleculeResolver(molecules, None),  # type: ignore[arg-type]  # UUID refs only
    )

    result = await uc(
        CreateCollectionCommand(
            workspace_id=workspace_id, name="Big", created_by=seed.USER, molecule_ids=ids
        ),
        auth=FakeAuth(workspace_id=workspace_id),
    )

    collection = result.unwrap()
    assert collection.molecule_count == N
    async with uow:
        stored = await uow.session.scalar(
            sa.text("SELECT count(*) FROM collection_molecules WHERE collection_id = :c"),
            {"c": collection.id},
        )
    assert stored == N
