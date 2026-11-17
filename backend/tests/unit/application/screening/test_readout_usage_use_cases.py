"""Removing, changing and reading the usage of a published protocol's readouts."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.manage_readout_definitions import (
    GetReadoutUsage,
    GetReadoutUsageQuery,
    RemoveReadoutDefinition,
    RemoveReadoutDefinitionCommand,
    UpdateReadoutDefinition,
    UpdateReadoutDefinitionCommand,
)
from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition, ReadoutUsage
from cellar.domain.shared.errors import AuthorizationError, ConflictError, NotFoundError
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.research_organization._helpers import FakeUnitOfWork

pytestmark = pytest.mark.asyncio

WS = uuid.uuid4()
UNUSED = ReadoutUsage()
USED = ReadoutUsage(reasons=("has values in 3 runs",))


def _protocol(*, published: bool = True) -> Protocol:
    protocol = Protocol.create(
        workspace_id=WS,
        name="Kinase",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            ReadoutDefinition(
                protocol_id=uuid.uuid4(), name=name, data_type=ReadoutDataType.NUMERIC
            )
            for name in ("Raw", "Rwa")
        ],
    )
    if published:
        protocol.publish()
    return protocol


def _repo(protocol: Protocol | None) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
    return repo


def _reader(usage: ReadoutUsage = UNUSED) -> AsyncMock:
    reader = AsyncMock()
    reader.for_readout = AsyncMock(return_value=usage)
    return reader


async def _remove(protocol: Protocol, reader: AsyncMock | None, role: str = "editor"):
    repo = _repo(protocol)
    uc = RemoveReadoutDefinition(FakeUnitOfWork(), repo, AsyncMock(), usage_reader=reader)
    result = await uc(
        RemoveReadoutDefinitionCommand(
            workspace_id=WS,
            protocol_id=protocol.id,
            definition_id=protocol.readout_definitions[1].id,
        ),
        auth=FakeAuth(role=role, workspace_id=WS),
    )
    return result, repo


async def _rename(protocol: Protocol, reader: AsyncMock | None, **fields):
    repo = _repo(protocol)
    uc = UpdateReadoutDefinition(FakeUnitOfWork(), repo, AsyncMock(), usage_reader=reader)
    result = await uc(
        UpdateReadoutDefinitionCommand(
            workspace_id=WS,
            protocol_id=protocol.id,
            definition_id=protocol.readout_definitions[1].id,
            **(fields or {"name": "Ratio"}),
        ),
        auth=FakeAuth(workspace_id=WS),
    )
    return result, repo


async def test_remove_unused_readout_of_a_published_protocol():
    p = _protocol()
    rd_id = p.readout_definitions[1].id
    reader = _reader()
    result, repo = await _remove(p, reader)
    assert isinstance(result, Success)
    assert [rd.name for rd in p.readout_definitions] == ["Raw"]
    reader.for_readout.assert_awaited_once_with(WS, p.id, rd_id)
    repo.save.assert_awaited_once()


async def test_remove_used_readout_is_a_conflict_with_the_reasons():
    p = _protocol()
    result, repo = await _remove(p, _reader(USED))
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ConflictError)
    assert "has values in 3 runs" in str(result.failure())
    assert len(p.readout_definitions) == 2
    repo.save.assert_not_awaited()


async def test_remove_on_a_draft_does_not_look_usage_up():
    p = _protocol(published=False)
    reader = _reader(USED)
    result, _ = await _remove(p, reader)
    assert isinstance(result, Success)
    reader.for_readout.assert_not_awaited()


async def test_remove_viewer_raises_authorization_error():
    with pytest.raises(AuthorizationError):
        await _remove(_protocol(), _reader(), role="viewer")


async def test_rename_unused_readout_of_a_published_protocol():
    p = _protocol()
    result, repo = await _rename(p, _reader())
    assert isinstance(result, Success)
    assert p.readout_definitions[1].name == "Ratio"
    repo.save.assert_awaited_once()


async def test_rename_used_readout_is_a_conflict_with_the_reasons():
    p = _protocol()
    result, repo = await _rename(p, _reader(USED))
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ConflictError)
    assert "has values in 3 runs" in str(result.failure())
    repo.save.assert_not_awaited()


async def test_cosmetic_edit_of_a_used_readout_still_succeeds():
    p = _protocol()
    result, _ = await _rename(p, _reader(USED), precision=2)
    assert isinstance(result, Success)
    assert p.readout_definitions[1].precision == 2


async def test_usage_of_every_readout_merges_the_protocols_own_and_the_stored():
    p = _protocol()
    raw, rwa = p.readout_definitions
    p.update_readout_definition(
        rwa.id,
        is_calculated=True,
        calculation_formula="Raw / 2",
        usage=UNUSED,
    )
    reader = AsyncMock()
    reader.for_protocol = AsyncMock(return_value={raw.id: USED})
    uc = GetReadoutUsage(FakeUnitOfWork(), _repo(p), reader)
    result = await uc(
        GetReadoutUsageQuery(workspace_id=WS, protocol_id=p.id),
        auth=FakeAuth(role="viewer", workspace_id=WS),
    )
    assert isinstance(result, Success)
    usage = result.unwrap()
    assert list(usage) == [raw.id, rwa.id]
    assert usage[raw.id].reasons == ("named by the formula of 'Rwa'", "has values in 3 runs")
    assert not usage[rwa.id].in_use


async def test_usage_of_a_missing_protocol_is_not_found():
    uc = GetReadoutUsage(FakeUnitOfWork(), _repo(None), AsyncMock())
    result = await uc(
        GetReadoutUsageQuery(workspace_id=WS, protocol_id=uuid.uuid4()),
        auth=FakeAuth(role="viewer", workspace_id=WS),
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), NotFoundError)
