"""Unit tests for the AddRunCollection / RemoveRunCollection use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.manage_run_collections import (
    AddRunCollection,
    AddRunCollectionCommand,
    RemoveRunCollection,
    RemoveRunCollectionCommand,
)
from cellar.domain.screening_assay.events import (
    RunCollectionAdded,
    RunCollectionRemoved,
)
from cellar.domain.screening_assay.repository import CollectionLinkResult
from cellar.domain.shared.errors import ConflictError, NotFoundError
from cellar.domain.shared.events import DomainEvent

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeUoW:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> list[DomainEvent]:
        self.committed = True
        return []

    async def rollback(self) -> None:  # pragma: no cover
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


@dataclass
class FakeAuth:
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_role: str = "editor"
    is_admin: bool = False

    def has_role(self, minimum_role: str) -> bool:
        roles = ["viewer", "editor", "admin"]
        return roles.index(self.workspace_role) >= roles.index(minimum_role)


def _build_add_uc(
    *,
    is_locked: bool | None,
    link: CollectionLinkResult | None = None,
) -> tuple[AddRunCollection, AsyncMock, AsyncMock]:
    repo = AsyncMock()
    repo.find_lock_state = AsyncMock(return_value=is_locked)
    repo.add_collection = AsyncMock(return_value=link)
    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()
    uc = AddRunCollection(uow=FakeUoW(), repo=repo, dispatcher=dispatcher)
    return uc, repo, dispatcher


def _build_remove_uc(
    *,
    is_locked: bool | None,
    removed: bool = True,
) -> tuple[RemoveRunCollection, AsyncMock, AsyncMock]:
    repo = AsyncMock()
    repo.find_lock_state = AsyncMock(return_value=is_locked)
    repo.remove_collection = AsyncMock(return_value=removed)
    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()
    uc = RemoveRunCollection(uow=FakeUoW(), repo=repo, dispatcher=dispatcher)
    return uc, repo, dispatcher


def _dispatched_events(dispatcher: AsyncMock) -> list[DomainEvent]:
    dispatcher.dispatch_all.assert_awaited_once()
    return list(dispatcher.dispatch_all.await_args.args[0])


# ---------------------------------------------------------------------------
# AddRunCollection
# ---------------------------------------------------------------------------


class TestAddRunCollection:
    @pytest.mark.asyncio
    async def test_locked_run_blocked(self) -> None:
        auth = FakeAuth()
        uc, repo, _ = _build_add_uc(is_locked=True)

        result = await uc(
            AddRunCollectionCommand(
                workspace_id=auth.workspace_id,
                run_id=uuid.uuid4(),
                collection_id=uuid.uuid4(),
            ),
            auth=auth,
        )

        assert isinstance(result, Failure), result
        assert isinstance(result.failure(), ConflictError)
        repo.add_collection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_run_not_found(self) -> None:
        auth = FakeAuth()
        uc, repo, _ = _build_add_uc(is_locked=None)

        result = await uc(
            AddRunCollectionCommand(
                workspace_id=auth.workspace_id,
                run_id=uuid.uuid4(),
                collection_id=uuid.uuid4(),
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        repo.add_collection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_add_succeeds_and_emits_event(self) -> None:
        auth = FakeAuth()
        run_id = uuid.uuid4()
        collection_id = uuid.uuid4()
        uc, _, dispatcher = _build_add_uc(is_locked=False, link=CollectionLinkResult.ADDED)

        result = await uc(
            AddRunCollectionCommand(
                workspace_id=auth.workspace_id,
                run_id=run_id,
                collection_id=collection_id,
            ),
            auth=auth,
        )

        assert isinstance(result, Success), result
        events = _dispatched_events(dispatcher)
        added = [e for e in events if isinstance(e, RunCollectionAdded)]
        assert len(added) == 1
        assert added[0].collection_id == collection_id
        assert added[0].aggregate_id == run_id
        assert added[0].user_id == auth.user_id

    @pytest.mark.asyncio
    async def test_add_idempotent_emits_no_event(self) -> None:
        auth = FakeAuth()
        uc, _, dispatcher = _build_add_uc(
            is_locked=False, link=CollectionLinkResult.ALREADY_LINKED
        )

        result = await uc(
            AddRunCollectionCommand(
                workspace_id=auth.workspace_id,
                run_id=uuid.uuid4(),
                collection_id=uuid.uuid4(),
            ),
            auth=auth,
        )

        assert isinstance(result, Success), result
        events = _dispatched_events(dispatcher)
        assert not any(isinstance(e, RunCollectionAdded) for e in events)

    @pytest.mark.asyncio
    async def test_add_collection_not_found(self) -> None:
        auth = FakeAuth()
        uc, _, dispatcher = _build_add_uc(
            is_locked=False, link=CollectionLinkResult.COLLECTION_NOT_FOUND
        )

        result = await uc(
            AddRunCollectionCommand(
                workspace_id=auth.workspace_id,
                run_id=uuid.uuid4(),
                collection_id=uuid.uuid4(),
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        dispatcher.dispatch_all.assert_not_awaited()


# ---------------------------------------------------------------------------
# RemoveRunCollection
# ---------------------------------------------------------------------------


class TestRemoveRunCollection:
    @pytest.mark.asyncio
    async def test_remove_succeeds_and_emits_event(self) -> None:
        auth = FakeAuth()
        run_id = uuid.uuid4()
        collection_id = uuid.uuid4()
        uc, _, dispatcher = _build_remove_uc(is_locked=False, removed=True)

        result = await uc(
            RemoveRunCollectionCommand(
                workspace_id=auth.workspace_id,
                run_id=run_id,
                collection_id=collection_id,
            ),
            auth=auth,
        )

        assert isinstance(result, Success), result
        events = _dispatched_events(dispatcher)
        removed = [e for e in events if isinstance(e, RunCollectionRemoved)]
        assert len(removed) == 1
        assert removed[0].collection_id == collection_id
        assert removed[0].aggregate_id == run_id
        assert removed[0].user_id == auth.user_id

    @pytest.mark.asyncio
    async def test_remove_noop_emits_no_event(self) -> None:
        auth = FakeAuth()
        uc, _, dispatcher = _build_remove_uc(is_locked=False, removed=False)

        result = await uc(
            RemoveRunCollectionCommand(
                workspace_id=auth.workspace_id,
                run_id=uuid.uuid4(),
                collection_id=uuid.uuid4(),
            ),
            auth=auth,
        )

        assert isinstance(result, Success), result
        events = _dispatched_events(dispatcher)
        assert not any(isinstance(e, RunCollectionRemoved) for e in events)

    @pytest.mark.asyncio
    async def test_remove_locked_run_blocked(self) -> None:
        auth = FakeAuth()
        uc, repo, _ = _build_remove_uc(is_locked=True)

        result = await uc(
            RemoveRunCollectionCommand(
                workspace_id=auth.workspace_id,
                run_id=uuid.uuid4(),
                collection_id=uuid.uuid4(),
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ConflictError)
        repo.remove_collection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_remove_run_not_found(self) -> None:
        auth = FakeAuth()
        uc, repo, _ = _build_remove_uc(is_locked=None)

        result = await uc(
            RemoveRunCollectionCommand(
                workspace_id=auth.workspace_id,
                run_id=uuid.uuid4(),
                collection_id=uuid.uuid4(),
            ),
            auth=auth,
        )

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        repo.remove_collection.assert_not_awaited()
