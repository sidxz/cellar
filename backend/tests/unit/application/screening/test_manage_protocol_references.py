"""Reference use cases return expected domain failures on the railway instead of raising."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure

from cellar.application.screening.manage_protocol_references import (
    AddProtocolReference,
    AddProtocolReferenceCommand,
    RemoveProtocolReference,
    RemoveProtocolReferenceCommand,
)
from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ProtocolReference, ReadoutDefinition
from cellar.domain.shared.errors import ConflictError, NotFoundError, ValidationError
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.research_organization._helpers import FakeUnitOfWork

pytestmark = pytest.mark.asyncio

WS = uuid.uuid4()
AUTH = FakeAuth(role="editor", user_id=uuid.uuid4(), workspace_id=WS)
DOI = ProtocolReference(kind="doi", value="10.1021/jm901137j")  # type: ignore[arg-type]


def _setup() -> tuple[Protocol, AsyncMock]:
    protocol = Protocol.create(
        workspace_id=WS,
        name="p",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            ReadoutDefinition(
                protocol_id=uuid.uuid4(), name="IC50", data_type=ReadoutDataType.NUMERIC
            )
        ],
        references=[DOI],
    )
    repo = AsyncMock()
    repo.find_by_id_in_workspace.return_value = protocol
    return protocol, repo


def _add(repo: AsyncMock, protocol: Protocol, kind: str, value: str):
    uc = AddProtocolReference(FakeUnitOfWork(), repo, AsyncMock())
    cmd = AddProtocolReferenceCommand(
        workspace_id=WS, protocol_id=protocol.id, kind=kind, value=value
    )
    return uc(cmd, auth=AUTH)


@pytest.mark.parametrize(
    ("kind", "value", "error"),
    [("doi", "doi:10.1021/jm901137j", ConflictError), ("url", "javascript:x", ValidationError)],
)
async def test_add_failure_is_returned_and_nothing_saved(kind, value, error):
    protocol, repo = _setup()
    result = await _add(repo, protocol, kind, value)
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), error)
    repo.save.assert_not_awaited()


async def test_removing_an_unknown_key_is_a_not_found_failure():
    protocol, repo = _setup()
    uc = RemoveProtocolReference(FakeUnitOfWork(), repo, AsyncMock())
    cmd = RemoveProtocolReferenceCommand(workspace_id=WS, protocol_id=protocol.id, key="pmid:1")
    result = await uc(cmd, auth=AUTH)
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)
    repo.save.assert_not_awaited()
