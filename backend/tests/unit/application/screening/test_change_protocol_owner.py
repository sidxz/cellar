"""A protocol's creator can hand it to another org, even while it is locked."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from returns.result import Success

from cellar.application.shared.change_owner import ChangeOwnerCommand
from cellar.application.screening.change_protocol_owner import ChangeProtocolOwner
from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.research_organization._helpers import FakeUnitOfWork

NEW_ORG = uuid.uuid4()


@dataclass(frozen=True)
class _Org:
    id: uuid.UUID
    enabled: bool = True


class _Directory:
    async def list_orgs(self) -> list[_Org]:
        return [_Org(NEW_ORG)]


@pytest.mark.asyncio
async def test_creator_changes_locked_protocol_owner() -> None:
    auth = FakeAuth(role="editor")
    protocol = Protocol.create(
        workspace_id=auth.workspace_id,
        name="MIC",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=auth.user_id,
        readout_definitions=[
            ReadoutDefinition(
                protocol_id=uuid.uuid4(), name="MIC", data_type=ReadoutDataType.NUMERIC, unit="uM"
            )
        ],
    )
    protocol.lock(locked_by=auth.user_id, reason="QA")
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
    uc = ChangeProtocolOwner(FakeUnitOfWork(), repo, AsyncMock(), _Directory())
    result = await uc(
        ChangeOwnerCommand(
            workspace_id=auth.workspace_id, entity_id=protocol.id, owner_org_id=NEW_ORG
        ),
        auth=auth,
    )
    assert isinstance(result, Success)
    assert result.unwrap().owner_org_id == NEW_ORG
