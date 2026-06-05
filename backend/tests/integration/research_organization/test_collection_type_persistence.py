"""Round-trip the Collection.type attribute through the repository."""

from __future__ import annotations

import uuid

from cellar.domain.research_organization.collection import Collection
from cellar.domain.research_organization.enums import CollectionType
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (
    SQLAlchemyCollectionRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class TestCollectionTypePersistence:
    async def test_type_round_trips(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            coll = Collection.create(
                workspace_id=ws_id,
                name="Kinase Library",
                created_by=uuid.uuid4(),
                type=CollectionType.LIBRARY,
            )
            await repo.save(coll)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            loaded = await repo.find_by_id_in_workspace(ws_id, coll.id)

        assert loaded is not None
        assert loaded.type is CollectionType.LIBRARY

    async def test_default_type_is_generic(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            coll = Collection.create(
                workspace_id=ws_id, name="Ad-hoc", created_by=uuid.uuid4()
            )
            await repo.save(coll)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            loaded = await repo.find_by_id_in_workspace(ws_id, coll.id)

        assert loaded is not None
        assert loaded.type is CollectionType.GENERIC
