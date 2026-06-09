"""Integration tests: RunRepository.add_collection / remove_collection.

Mirrors the run↔target link tests. Proves idempotency, the distinct
not-found outcomes, removal semantics, and defense-in-depth workspace
scoping via the shared ``_owns`` check.
"""

from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa

from cellar.domain.research_organization.collection import Collection
from cellar.domain.research_organization.enums import CollectionType
from cellar.domain.screening_assay.repository import CollectionLinkResult
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (  # noqa: E501
    SQLAlchemyCollectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.run_repository import (
    SQLAlchemyRunRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_USER_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000002")


async def _insert_protocol(uow: AsyncUnitOfWork, protocol_id: uuid.UUID, ws_id: uuid.UUID) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO protocols "
            "(id, workspace_id, name, protocol_type, status, "
            "is_locked, dose_unit, pos_control_signal, version, protocol_version, created_by) "
            "VALUES (:id, :ws, :name, 'biochemical', 'active', "
            "false, 'uM', 'high', 1, 1, :user)"
        ),
        {
            "id": protocol_id,
            "ws": ws_id,
            "name": f"Protocol-{str(protocol_id)[:8]}",
            "user": _USER_ID,
        },
    )


async def _insert_run(
    uow: AsyncUnitOfWork, run_id: uuid.UUID, protocol_id: uuid.UUID, ws_id: uuid.UUID
) -> None:
    await uow.session.execute(
        sa.text(
            "INSERT INTO runs "
            "(id, workspace_id, protocol_id, run_date, operator, "
            "status, is_locked, version, notes) "
            "VALUES (:id, :ws, :proto, :run_date, :user, "
            "'draft', false, 1, NULL)"
        ),
        {
            "id": run_id,
            "ws": ws_id,
            "proto": protocol_id,
            "run_date": date.today(),
            "user": _USER_ID,
        },
    )


async def _insert_collection(
    uow: AsyncUnitOfWork, collection_id: uuid.UUID, ws_id: uuid.UUID, *, name: str
) -> None:
    """Seed a Collection via its aggregate factory + repository.

    Mirrors test_collection_type_persistence.py — keeps the collection's
    required columns (created_by, visibility, type, version) in one place.
    """
    repo = SQLAlchemyCollectionRepository(uow)
    coll = Collection(
        id=collection_id,
        workspace_id=ws_id,
        name=name,
        created_by=_USER_ID,
        type=CollectionType.LIBRARY,
    )
    await repo.save(coll)


async def _seed_run_and_collection(
    uow: AsyncUnitOfWork, ws_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed one protocol+run and one collection in ``ws_id``. Returns (run_id, coll_id)."""
    proto_id = uuid.uuid4()
    run_id = uuid.uuid4()
    coll_id = uuid.uuid4()
    async with uow:
        await _insert_protocol(uow, proto_id, ws_id)
        await _insert_run(uow, run_id, proto_id, ws_id)
        await _insert_collection(uow, coll_id, ws_id, name=f"Set-{str(coll_id)[:8]}")
        await uow.commit()
    return run_id, coll_id


class TestAddCollection:
    async def test_first_link_added_then_idempotent(self, uow, workspace_id):
        run_id, coll_id = await _seed_run_and_collection(uow, workspace_id)

        repo = SQLAlchemyRunRepository(uow)
        async with uow:
            first = await repo.add_collection(workspace_id, run_id, coll_id)
            await uow.commit()
        async with uow:
            second = await repo.add_collection(workspace_id, run_id, coll_id)
            await uow.commit()

        assert first is CollectionLinkResult.ADDED
        assert second is CollectionLinkResult.ALREADY_LINKED

    async def test_unknown_collection_not_found(self, uow, workspace_id):
        run_id, _ = await _seed_run_and_collection(uow, workspace_id)

        repo = SQLAlchemyRunRepository(uow)
        async with uow:
            result = await repo.add_collection(workspace_id, run_id, uuid.uuid4())

        assert result is CollectionLinkResult.COLLECTION_NOT_FOUND

    async def test_unknown_run_owner_not_found(self, uow, workspace_id):
        _, coll_id = await _seed_run_and_collection(uow, workspace_id)

        repo = SQLAlchemyRunRepository(uow)
        async with uow:
            result = await repo.add_collection(workspace_id, uuid.uuid4(), coll_id)

        assert result is CollectionLinkResult.OWNER_NOT_FOUND

    async def test_collection_in_other_workspace_not_found(self, uow, workspace_id):
        """Defense-in-depth: a cross-workspace collection is invisible via _owns."""
        run_id, _ = await _seed_run_and_collection(uow, workspace_id)
        other_ws = uuid.uuid4()
        foreign_coll = uuid.uuid4()
        async with uow:
            await _insert_collection(uow, foreign_coll, other_ws, name="Foreign Set")
            await uow.commit()

        repo = SQLAlchemyRunRepository(uow)
        async with uow:
            result = await repo.add_collection(workspace_id, run_id, foreign_coll)

        assert result is CollectionLinkResult.COLLECTION_NOT_FOUND


class TestRemoveCollection:
    async def test_remove_existing_then_absent(self, uow, workspace_id):
        run_id, coll_id = await _seed_run_and_collection(uow, workspace_id)

        repo = SQLAlchemyRunRepository(uow)
        async with uow:
            await repo.add_collection(workspace_id, run_id, coll_id)
            await uow.commit()
        async with uow:
            removed = await repo.remove_collection(workspace_id, run_id, coll_id)
            await uow.commit()
        async with uow:
            removed_again = await repo.remove_collection(workspace_id, run_id, coll_id)
            await uow.commit()

        assert removed is True
        assert removed_again is False
