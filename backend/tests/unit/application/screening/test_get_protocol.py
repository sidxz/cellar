"""Unit tests for GetProtocol and ListProtocols (the measured-curves flag)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from cellar.application.screening.get_protocol import (
    GetProtocol,
    GetProtocolQuery,
    ListProtocols,
    ListProtocolsQuery,
)
from cellar.application.screening.manage_protocol import (
    ListProtocolsByProject,
    ListProtocolsByProjectQuery,
)
from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.errors import AuthorizationError, NotFoundError
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.research_organization._helpers import FakeUnitOfWork

viewer = FakeAuth(role="viewer")
ws = viewer.workspace_id


def _protocol(name: str = "Assay") -> Protocol:
    p = Protocol.create(
        workspace_id=ws,
        name=name,
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            ReadoutDefinition(
                protocol_id=uuid.uuid4(), name="IC50", data_type=ReadoutDataType.NUMERIC
            )
        ],
    )
    p.clear_events()
    return p


def _repo(*protocols: Protocol, with_curves: set[uuid.UUID] | None = None) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id_in_workspace.return_value = protocols[0] if protocols else None
    repo.find_by_workspace.return_value = list(protocols)
    repo.find_by_project.return_value = list(protocols)
    repo.find_effective_targets_for_protocols.return_value = {}
    repo.find_ids_with_measured_curves.return_value = with_curves or set()
    return repo


async def _get(repo: AsyncMock, protocol_id: uuid.UUID, auth: FakeAuth = viewer):
    uc = GetProtocol(FakeUnitOfWork(), repo)
    return await uc(GetProtocolQuery(workspace_id=ws, protocol_id=protocol_id), auth=auth)


async def test_get_protocol_reports_has_measured_curves():
    p = _protocol()
    repo = _repo(p, with_curves={p.id})
    assert (await _get(repo, p.id)).unwrap().has_measured_curves is True
    repo.find_ids_with_measured_curves.assert_awaited_once_with(ws, [p.id])

    repo = _repo(p)
    assert (await _get(repo, p.id)).unwrap().has_measured_curves is False


async def test_list_protocols_reports_has_measured_curves_per_item_with_one_query():
    p1, p2 = _protocol("One"), _protocol("Two")
    repo = _repo(p1, p2, with_curves={p1.id})
    uc = ListProtocols(FakeUnitOfWork(), repo)
    page = (await uc(ListProtocolsQuery(workspace_id=ws), auth=viewer)).unwrap()
    repo.find_ids_with_measured_curves.assert_awaited_once_with(ws, [p1.id, p2.id])
    assert [i.has_measured_curves for i in page.items] == [True, False]


async def test_list_by_project_reports_has_measured_curves():
    p1, p2 = _protocol("One"), _protocol("Two")
    repo = _repo(p1, p2, with_curves={p2.id})
    uc = ListProtocolsByProject(FakeUnitOfWork(), repo)
    query = ListProtocolsByProjectQuery(workspace_id=ws, project_id=uuid.uuid4())
    page = (await uc(query, auth=viewer)).unwrap()
    repo.find_ids_with_measured_curves.assert_awaited_once_with(ws, [p1.id, p2.id])
    assert [i.has_measured_curves for i in page.items] == [False, True]


async def test_get_protocol_not_found():
    repo = _repo()
    missing = uuid.uuid4()
    failure = (await _get(repo, missing)).failure()
    assert isinstance(failure, NotFoundError) and str(missing) in str(failure)
    repo.find_ids_with_measured_curves.assert_not_awaited()


async def test_get_protocol_other_workspace_raises_not_found():
    repo = _repo(_protocol())
    with pytest.raises(NotFoundError):
        await _get(repo, uuid.uuid4(), auth=FakeAuth(role="viewer"))
    repo.find_by_id_in_workspace.assert_not_awaited()


async def test_get_protocol_no_role_raises_authorization_error():
    repo = _repo(_protocol())
    with pytest.raises(AuthorizationError):
        await _get(repo, uuid.uuid4(), auth=FakeAuth(role="guest", workspace_id=ws))
    repo.find_by_id_in_workspace.assert_not_awaited()
