"""Unit tests for normalization coalescing on AddReadoutDefinition / UpdateReadoutDefinition.

The use case accepts both the preferred ``normalizations: list[str]`` and the
legacy ``normalization: str`` and resolves them into a single domain-side
``frozenset[ReadoutNormalization]`` that the aggregate stores.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Success

from chem_vault.application.screening.manage_readout_definitions import (
    AddReadoutDefinition,
    AddReadoutDefinitionCommand,
    UpdateReadoutDefinition,
    UpdateReadoutDefinitionCommand,
)
from chem_vault.domain.screening_assay.enums import (
    ProtocolType,
    ReadoutDataType,
    ReadoutNormalization,
)
from chem_vault.domain.screening_assay.protocol import Protocol, ReadoutDefinition

WS = uuid.uuid4()
USER = uuid.uuid4()


def _make_protocol() -> Protocol:
    rd = ReadoutDefinition(
        protocol_id=uuid.UUID(int=0),
        name="seed",
        data_type=ReadoutDataType.NUMERIC,
    )
    return Protocol.create(
        workspace_id=WS,
        name="P",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=USER,
        readout_definitions=[rd],
    )


def _fake_uow():
    uow = AsyncMock()
    uow.is_active = True
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    uow.commit = AsyncMock(return_value=[])
    return uow


def _make_repo(protocol: Protocol):
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
    repo.save = AsyncMock()
    return repo


def _make_dispatcher():
    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()
    return dispatcher


@pytest.mark.asyncio
async def test_add_readout_with_normalizations_list():
    protocol = _make_protocol()
    use_case = AddReadoutDefinition(
        uow=_fake_uow(), repo=_make_repo(protocol), dispatcher=_make_dispatcher()
    )
    cmd = AddReadoutDefinitionCommand(
        workspace_id=WS,
        protocol_id=protocol.id,
        name="Raw AU",
        data_type="numeric",
        normalizations=["percent_inhibition", "z_score"],
    )
    result = await use_case(cmd)
    assert isinstance(result, Success)
    new_rd = next(rd for rd in result.unwrap().readout_definitions if rd.name == "Raw AU")
    assert new_rd.normalizations == frozenset(
        {ReadoutNormalization.PERCENT_INHIBITION, ReadoutNormalization.Z_SCORE}
    )


# Tests for the legacy single-value `normalization=` request field removed —
# the field is gone from AddReadoutDefinitionCommand; clients pass
# `normalizations=[]` directly.


@pytest.mark.asyncio
async def test_update_readout_with_normalizations_list_replaces_set():
    protocol = _make_protocol()
    seed_rd = protocol.readout_definitions[0]
    use_case = UpdateReadoutDefinition(
        uow=_fake_uow(), repo=_make_repo(protocol), dispatcher=_make_dispatcher()
    )
    cmd = UpdateReadoutDefinitionCommand(
        workspace_id=WS,
        protocol_id=protocol.id,
        definition_id=seed_rd.id,
        normalizations=["percent_inhibition", "z_score"],
    )
    result = await use_case(cmd)
    assert isinstance(result, Success)
    updated = result.unwrap().readout_definitions[0]
    assert updated.normalizations == frozenset(
        {ReadoutNormalization.PERCENT_INHIBITION, ReadoutNormalization.Z_SCORE}
    )


@pytest.mark.asyncio
async def test_update_readout_with_empty_normalizations_clears_set():
    protocol = _make_protocol()
    seed_rd = protocol.readout_definitions[0]
    # Seed it with a formula first.
    protocol.update_readout_definition(
        seed_rd.id, normalizations=frozenset({ReadoutNormalization.PERCENT_INHIBITION})
    )
    use_case = UpdateReadoutDefinition(
        uow=_fake_uow(), repo=_make_repo(protocol), dispatcher=_make_dispatcher()
    )
    cmd = UpdateReadoutDefinitionCommand(
        workspace_id=WS,
        protocol_id=protocol.id,
        definition_id=seed_rd.id,
        normalizations=[],
    )
    result = await use_case(cmd)
    assert isinstance(result, Success)
    assert result.unwrap().readout_definitions[0].normalizations == frozenset()
