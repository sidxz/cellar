"""DeleteProtocol + GetProtocol.can_delete: who may delete a draft, and never
while something still points at it."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.get_protocol import GetProtocol, GetProtocolQuery
from cellar.application.screening.manage_protocol import (
    DeleteProtocol,
    DeleteProtocolCommand,
)
from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.errors import AuthorizationError, ConflictError, NotFoundError
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.research_organization._helpers import FakeUnitOfWork

pytestmark = pytest.mark.asyncio

WS = uuid.uuid4()
CREATOR = uuid.uuid4()


def _protocol(*, published: bool = False) -> Protocol:
    p = Protocol.create(
        workspace_id=WS,
        name="Onboarding draft",
        protocol_type=ProtocolType.CELL_BASED,
        created_by=CREATOR,
        readout_definitions=[
            ReadoutDefinition(
                protocol_id=uuid.uuid4(), name="IC50", data_type=ReadoutDataType.NUMERIC
            )
        ],
    )
    if published:
        p.publish()
    p.clear_events()
    return p


def _repo(protocol: Protocol | None, usages: list[str] | None = None) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id_in_workspace.return_value = protocol
    repo.find_usages.return_value = usages or []
    repo.find_effective_targets_for_protocols.return_value = {}
    return repo


def _auth(role: str = "editor", user_id: uuid.UUID = CREATOR) -> FakeAuth:
    return FakeAuth(role=role, user_id=user_id, workspace_id=WS)


async def _delete(repo: AsyncMock, auth: FakeAuth, protocol_id: uuid.UUID | None = None):
    uc = DeleteProtocol(FakeUnitOfWork(), repo, AsyncMock())
    return await uc(
        DeleteProtocolCommand(workspace_id=WS, protocol_id=protocol_id or uuid.uuid4()),
        auth=auth,
    )


# ---------- DeleteProtocol ----------


async def test_creator_editor_deletes_their_unused_draft():
    p = _protocol()
    repo = _repo(p)

    assert isinstance(await _delete(repo, _auth(), p.id), Success)
    repo.delete.assert_awaited_once_with(WS, p.id)


async def test_admin_deletes_someone_elses_draft():
    p = _protocol()
    repo = _repo(p)

    assert isinstance(await _delete(repo, _auth("admin", uuid.uuid4()), p.id), Success)
    repo.delete.assert_awaited_once()


async def test_another_editor_cannot_delete_the_draft():
    p = _protocol()
    repo = _repo(p)

    with pytest.raises(AuthorizationError):
        await _delete(repo, _auth("editor", uuid.uuid4()), p.id)
    repo.delete.assert_not_awaited()


async def test_viewer_cannot_delete_even_their_own_draft():
    with pytest.raises(AuthorizationError):
        await _delete(_repo(_protocol()), _auth("viewer"))


async def test_a_draft_still_in_use_is_refused_even_for_an_admin():
    p = _protocol()
    repo = _repo(p, usages=['campaign "Test-2" (2 readouts)', "1 compound flag"])

    out = await _delete(repo, _auth("admin", uuid.uuid4()), p.id)

    assert isinstance(out, Failure)
    err = out.failure()
    assert isinstance(err, ConflictError)
    assert 'campaign "Test-2" (2 readouts)' in str(err)
    assert "1 compound flag" in str(err)
    repo.delete.assert_not_awaited()


async def test_a_published_protocol_is_refused():
    p = _protocol(published=True)
    repo = _repo(p)

    out = await _delete(repo, _auth("admin"), p.id)

    assert isinstance(out, Failure)
    assert isinstance(out.failure(), ConflictError)
    repo.delete.assert_not_awaited()


async def test_missing_protocol_is_not_found():
    out = await _delete(_repo(None), _auth())
    assert isinstance(out, Failure)
    assert isinstance(out.failure(), NotFoundError)


# ---------- GetProtocol.can_delete ----------


async def _can_delete(protocol: Protocol, auth: FakeAuth, usages: list[str] | None = None):
    repo = _repo(protocol, usages)
    out = await GetProtocol(FakeUnitOfWork(), repo)(
        GetProtocolQuery(workspace_id=WS, protocol_id=protocol.id), auth=auth
    )
    return out.unwrap().can_delete, repo


async def test_can_delete_true_for_the_creator_of_an_unused_draft():
    can, _ = await _can_delete(_protocol(), _auth())
    assert can is True


async def test_can_delete_false_when_in_use():
    can, _ = await _can_delete(_protocol(), _auth(), usages=["3 runs"])
    assert can is False


async def test_can_delete_false_for_someone_else_without_checking_usages():
    can, repo = await _can_delete(_protocol(), _auth("editor", uuid.uuid4()))
    assert can is False
    repo.find_usages.assert_not_awaited()


async def test_can_delete_false_for_a_published_protocol():
    can, repo = await _can_delete(_protocol(published=True), _auth("admin"))
    assert can is False
    repo.find_usages.assert_not_awaited()
