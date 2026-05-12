"""Tests for ListBulkRegistrationItems use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from returns.result import Failure, Success

from cellar.application.chemical_registration.bulk_registration_item_reader import (
    BulkRegistrationItemPage,
    BulkRegistrationItemRow,
)
from cellar.application.chemical_registration.list_bulk_registration_items import (
    ListBulkRegistrationItems,
    ListBulkRegistrationItemsQuery,
)
from cellar.domain.chemical_registration.bulk_registration import BulkRegistration
from cellar.domain.chemical_registration.enums import BulkRegistrationFileFormat
from cellar.domain.shared.errors import NotFoundError, ValidationError


@dataclass
class StubAuth:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_role: str = "viewer"
    is_admin: bool = False

    def has_role(self, minimum_role: str) -> bool:
        return True


class StubRepo:
    def __init__(self, *, by_workflow: dict[str, BulkRegistration] | None = None) -> None:
        self._by_workflow = by_workflow or {}

    async def find_by_workflow_id_in_workspace(
        self, workspace_id: uuid.UUID, workflow_id: str
    ) -> BulkRegistration | None:
        return self._by_workflow.get(workflow_id)

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> BulkRegistration | None:
        for v in self._by_workflow.values():
            if v.id == id:
                return v
        return None


class StubReader:
    def __init__(self, page: BulkRegistrationItemPage) -> None:
        self.page = page
        self.calls: list[dict] = []

    async def list_items(
        self,
        *,
        workspace_id: uuid.UUID,
        bulk_registration_id: uuid.UUID,
        action: str | None,
        limit: int,
        offset: int,
    ) -> BulkRegistrationItemPage:
        self.calls.append(
            {
                "workspace_id": workspace_id,
                "bulk_registration_id": bulk_registration_id,
                "action": action,
                "limit": limit,
                "offset": offset,
            }
        )
        return self.page


def _make_bulk_reg(workspace_id: uuid.UUID, workflow_id: str) -> BulkRegistration:
    return BulkRegistration.create(
        workspace_id=workspace_id,
        source_file="f.csv",
        file_format=BulkRegistrationFileFormat.CSV,
        submitted_by=uuid.uuid4(),
        total_count=1,
        workflow_id=workflow_id,
    )


class StubUoW:
    async def __aenter__(self) -> "StubUoW":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def commit(self) -> list:
        return []


@pytest.mark.asyncio
async def test_list_resolves_workflow_id_to_bulk_reg_id() -> None:
    ws = uuid.uuid4()
    auth = StubAuth(user_id=uuid.uuid4(), workspace_id=ws)
    bulk = _make_bulk_reg(ws, "bulk-reg-w-x")
    repo = StubRepo(by_workflow={"bulk-reg-w-x": bulk})
    reader = StubReader(BulkRegistrationItemPage(rows=[], total=0))

    uc = ListBulkRegistrationItems(uow=StubUoW(), repo=repo, reader=reader)
    result = await uc(
        ListBulkRegistrationItemsQuery(
            workspace_id=ws,
            workflow_id="bulk-reg-w-x",
            action="error",
            limit=10,
            offset=0,
        ),
        auth=auth,
    )
    assert isinstance(result, Success)
    assert reader.calls[0]["bulk_registration_id"] == bulk.id
    assert reader.calls[0]["action"] == "error"
    assert reader.calls[0]["limit"] == 10


@pytest.mark.asyncio
async def test_list_returns_not_found_when_workflow_missing() -> None:
    ws = uuid.uuid4()
    auth = StubAuth(user_id=uuid.uuid4(), workspace_id=ws)
    repo = StubRepo(by_workflow={})
    reader = StubReader(BulkRegistrationItemPage(rows=[], total=0))

    uc = ListBulkRegistrationItems(uow=StubUoW(), repo=repo, reader=reader)
    result = await uc(
        ListBulkRegistrationItemsQuery(
            workspace_id=ws,
            workflow_id="missing",
        ),
        auth=auth,
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_list_validates_action_enum() -> None:
    ws = uuid.uuid4()
    auth = StubAuth(user_id=uuid.uuid4(), workspace_id=ws)
    bulk = _make_bulk_reg(ws, "wf")
    repo = StubRepo(by_workflow={"wf": bulk})
    reader = StubReader(BulkRegistrationItemPage(rows=[], total=0))

    uc = ListBulkRegistrationItems(uow=StubUoW(), repo=repo, reader=reader)
    result = await uc(
        ListBulkRegistrationItemsQuery(
            workspace_id=ws,
            workflow_id="wf",
            action="not-an-action",
        ),
        auth=auth,
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ValidationError)
