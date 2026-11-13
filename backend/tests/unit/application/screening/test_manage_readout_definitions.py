"""AddTemperatureWindow and melt_config on UpdateReadoutDefinition."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.screening.manage_readout_definitions import (
    AddTemperatureWindow,
    AddTemperatureWindowCommand,
    UpdateReadoutDefinition,
    UpdateReadoutDefinitionCommand,
)
from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.melt_window import MeltMeasure
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.errors import AuthorizationError, ConflictError, ValidationError
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.research_organization._helpers import FakeUnitOfWork

pytestmark = pytest.mark.asyncio

WS = uuid.uuid4()


def _protocol(*extra: ReadoutDefinition) -> Protocol:
    return Protocol.create(
        workspace_id=WS,
        name="Thermal",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=[
            ReadoutDefinition(
                protocol_id=uuid.uuid4(), name="Raw", data_type=ReadoutDataType.NUMERIC
            ),
            *extra,
        ],
    )


def _repo(protocol: Protocol) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
    repo.save = AsyncMock()
    return repo


def _cmd(protocol: Protocol, measures=(MeltMeasure.TM, MeltMeasure.DELTA_TM), **kw):
    return AddTemperatureWindowCommand(
        workspace_id=WS,
        protocol_id=protocol.id,
        window="Main",
        channel_key="ch1",
        low=25.0,
        high=50.0,
        measures=measures,
        **kw,
    )


async def _add(protocol: Protocol, cmd, role: str = "editor"):
    repo = _repo(protocol)
    uc = AddTemperatureWindow(FakeUnitOfWork(), repo, AsyncMock())
    return await uc(cmd, auth=FakeAuth(role=role, workspace_id=WS)), repo


async def test_add_window_adds_tm_and_delta_tm_in_one_change():
    p = _protocol()
    result, repo = await _add(p, _cmd(p))
    assert isinstance(result, Success)
    tm, dtm = p.readout_definitions[1:]
    assert (tm.name, dtm.name) == ("Tm (Main)", "ΔTm (Main)")
    for rd, m in ((tm, MeltMeasure.TM), (dtm, MeltMeasure.DELTA_TM)):
        assert rd.melt_config.measure == m
        assert rd.unit == "°C"
        assert rd.data_type == ReadoutDataType.NUMERIC
        assert rd.aggregation.value == "mean"
    assert dtm.display_order > tm.display_order > p.readout_definitions[0].display_order - 1
    repo.save.assert_awaited_once()


async def test_add_window_with_only_delta():
    p = _protocol()
    result, _ = await _add(p, _cmd(p, measures=(MeltMeasure.DELTA_TM,)))
    assert isinstance(result, Success)
    assert [rd.name for rd in p.readout_definitions] == ["Raw", "ΔTm (Main)"]


async def test_add_window_with_no_measures_is_validation_error():
    p = _protocol()
    result, repo = await _add(p, _cmd(p, measures=()))
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ValidationError)
    repo.save.assert_not_awaited()


async def test_add_window_name_collision_adds_nothing():
    clash = ReadoutDefinition(
        protocol_id=uuid.uuid4(), name="ΔTm (Main)", data_type=ReadoutDataType.NUMERIC
    )
    p = _protocol(clash)
    result, repo = await _add(p, _cmd(p))
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ConflictError)
    assert [rd.name for rd in p.readout_definitions] == ["Raw", "ΔTm (Main)"]
    repo.save.assert_not_awaited()


async def test_update_melt_config_on_draft_changes_both_bounds_only_together():
    p = _protocol()
    await _add(p, _cmd(p))
    tm = p.readout_definitions[1]
    repo = _repo(p)
    uc = UpdateReadoutDefinition(FakeUnitOfWork(), repo, AsyncMock())
    cfg = tm.melt_config.to_dict() | {"low": 20.0}
    result = await uc(
        UpdateReadoutDefinitionCommand(
            workspace_id=WS, protocol_id=p.id, definition_id=tm.id, melt_config=cfg
        ),
        auth=FakeAuth(workspace_id=WS),
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ValidationError)
    repo.save.assert_not_awaited()


async def test_update_melt_config_dict_is_applied():
    p = _protocol()
    await _add(p, _cmd(p, measures=(MeltMeasure.TM,)))
    tm = p.readout_definitions[1]
    uc = UpdateReadoutDefinition(FakeUnitOfWork(), _repo(p), AsyncMock())
    cfg = tm.melt_config.to_dict() | {"low": 20.0}
    result = await uc(
        UpdateReadoutDefinitionCommand(
            workspace_id=WS, protocol_id=p.id, definition_id=tm.id, melt_config=cfg
        ),
        auth=FakeAuth(workspace_id=WS),
    )
    assert isinstance(result, Success)
    assert p.readout_definitions[1].melt_config.low == 20.0


async def test_add_window_viewer_raises_authorization_error():
    p = _protocol()
    with pytest.raises(AuthorizationError):
        await _add(p, _cmd(p), role="viewer")
