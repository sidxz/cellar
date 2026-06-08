"""Unit tests for the CreateRun use case — collection-link writes.

Focused on the parallel target/collection write loops added in Task 9: a
created run links each requested collection via ``repo.add_collection`` (same
idempotent, workspace-checked path as targets), and an unknown/cross-workspace
collection aborts the create with a NotFoundError.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.create_run import CreateRun, CreateRunCommand
from cellar.domain.screening_assay.enums import ProtocolStatus
from cellar.domain.screening_assay.repository import (
    CollectionLinkResult,
    TargetLinkResult,
)
from cellar.domain.shared.errors import NotFoundError
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


@dataclass
class FakeProtocol:
    status: ProtocolStatus = ProtocolStatus.ACTIVE


def _build_uc(
    *,
    collection_link: CollectionLinkResult = CollectionLinkResult.ADDED,
) -> tuple[CreateRun, AsyncMock, AsyncMock]:
    repo = AsyncMock()
    repo.save = AsyncMock()
    repo.add_target = AsyncMock(return_value=TargetLinkResult.ADDED)
    repo.add_collection = AsyncMock(return_value=collection_link)
    protocol_repo = AsyncMock()
    protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=FakeProtocol())
    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()
    uc = CreateRun(
        uow=FakeUoW(),
        repo=repo,
        protocol_repo=protocol_repo,
        dispatcher=dispatcher,
    )
    return uc, repo, dispatcher


def _cmd(auth: FakeAuth, collection_ids: list[uuid.UUID]) -> CreateRunCommand:
    return CreateRunCommand(
        workspace_id=auth.workspace_id,
        protocol_id=uuid.uuid4(),
        run_date=date(2026, 6, 7),
        collection_ids=collection_ids,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateRunCollections:
    @pytest.mark.asyncio
    async def test_add_collection_called_once_per_id(self) -> None:
        auth = FakeAuth()
        cids = [uuid.uuid4(), uuid.uuid4()]
        uc, repo, _ = _build_uc()

        result = await uc(_cmd(auth, cids), auth=auth)

        assert isinstance(result, Success), result
        assert repo.add_collection.await_count == len(cids)
        linked = {call.args[2] for call in repo.add_collection.await_args_list}
        assert linked == set(cids)
        for call in repo.add_collection.await_args_list:
            assert call.args[0] == auth.workspace_id

    @pytest.mark.asyncio
    async def test_duplicate_collection_ids_deduplicated(self) -> None:
        auth = FakeAuth()
        cid = uuid.uuid4()
        uc, repo, _ = _build_uc()

        result = await uc(_cmd(auth, [cid, cid]), auth=auth)

        assert isinstance(result, Success), result
        assert repo.add_collection.await_count == 1

    @pytest.mark.asyncio
    async def test_no_collection_ids_no_links(self) -> None:
        auth = FakeAuth()
        uc, repo, _ = _build_uc()

        result = await uc(_cmd(auth, []), auth=auth)

        assert isinstance(result, Success), result
        repo.add_collection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_collection_aborts_create(self) -> None:
        auth = FakeAuth()
        uc, _, dispatcher = _build_uc(collection_link=CollectionLinkResult.COLLECTION_NOT_FOUND)

        result = await uc(_cmd(auth, [uuid.uuid4()]), auth=auth)

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        dispatcher.dispatch_all.assert_not_awaited()
