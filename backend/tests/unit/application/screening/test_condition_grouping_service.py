"""Tests for ConditionGroupingService — condition-based readout aggregation."""

from __future__ import annotations

import uuid
from collections import namedtuple
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.screening.condition_grouping_service import (
    ConditionGroupingService,
)
from chem_vault.domain.screening_assay.enums import (
    ConditionDataType,
    ProtocolType,
    ReadoutDataType,
)
from chem_vault.domain.screening_assay.protocol import (
    ConditionDefinition,
    Protocol,
    ReadoutDefinition,
)
from chem_vault.domain.shared.errors import NotFoundError, ValidationError

# ---------------------------------------------------------------------------
# Shared fixtures + helpers
# ---------------------------------------------------------------------------

WS = uuid.uuid4()
USER = uuid.uuid4()
_PH = uuid.UUID(int=0)  # placeholder UUID

# Simulate a DB grouped-by-condition row
GroupRow = namedtuple(
    "GroupRow",
    [
        "condition_value",
        "readout_definition_id",
        "readout_name",
        "aggregation",
        "unit",
        "avg_val",
        "min_val",
        "max_val",
        "cnt",
    ],
)


def _make_protocol(
    readout_defs: list[ReadoutDefinition],
    condition_defs: list[ConditionDefinition] | None = None,
) -> Protocol:
    """Build a minimal DRAFT Protocol with optional condition definitions."""
    return Protocol.create(
        workspace_id=WS,
        name="Test Protocol",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=USER,
        readout_definitions=readout_defs,
        condition_definitions=condition_defs,
    )


def _make_service(protocol_repo=None, readout_data_repo=None) -> ConditionGroupingService:
    return ConditionGroupingService(
        readout_data_repo=readout_data_repo or AsyncMock(),
        protocol_repo=protocol_repo or AsyncMock(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGroupsByConditionValue:
    """Protocol with 'Cell Line' condition and 'IC50' readout.
    Two rows returned (HEK293, CHO) → two ConditionGroups with correct values.
    """

    @pytest.mark.asyncio
    async def test_groups_by_condition_value(self) -> None:
        # -- Arrange --
        rd_ic50 = ReadoutDefinition(
            protocol_id=_PH,
            name="IC50",
            data_type=ReadoutDataType.NUMERIC,
            unit="nM",
        )
        cd_cell_line = ConditionDefinition(
            protocol_id=_PH,
            name="Cell Line",
            data_type=ConditionDataType.TEXT,
        )
        protocol = _make_protocol([rd_ic50], [cd_cell_line])
        rd = protocol.readout_definitions[0]

        hek_row = GroupRow(
            condition_value="HEK293",
            readout_definition_id=rd.id,
            readout_name="IC50",
            aggregation="mean",
            unit="nM",
            avg_val=5.2,
            min_val=4.0,
            max_val=7.0,
            cnt=3,
        )
        cho_row = GroupRow(
            condition_value="CHO",
            readout_definition_id=rd.id,
            readout_name="IC50",
            aggregation="mean",
            unit="nM",
            avg_val=12.8,
            min_val=10.0,
            max_val=16.0,
            cnt=2,
        )

        protocol_repo = AsyncMock()
        protocol_repo.find_by_id.return_value = protocol

        readout_data_repo = AsyncMock()
        readout_data_repo.find_grouped_by_condition.return_value = [hek_row, cho_row]

        service = _make_service(protocol_repo, readout_data_repo)

        # -- Act --
        result = await service.group_by_condition(WS, protocol.id, "Cell Line")

        # -- Assert --
        assert isinstance(result, Success)
        groups = result.unwrap()
        assert len(groups) == 2

        # Sorted alphabetically: CHO first, then HEK293
        cho_group = groups[0]
        hek_group = groups[1]

        assert cho_group.condition_value == "CHO"
        assert cho_group.run_count == 2
        assert len(cho_group.aggregated_readouts) == 1
        cho_readout = cho_group.aggregated_readouts[0]
        assert cho_readout.name == "IC50"
        assert cho_readout.value == 12.8  # avg used for "mean" aggregation
        assert cho_readout.unit == "nM"
        assert cho_readout.count == 2

        assert hek_group.condition_value == "HEK293"
        assert hek_group.run_count == 3
        hek_readout = hek_group.aggregated_readouts[0]
        assert hek_readout.value == 5.2
        assert hek_readout.readout_definition_id == rd.id

        readout_data_repo.find_grouped_by_condition.assert_awaited_once_with(
            protocol.id, "Cell Line"
        )


class TestUnknownConditionFails:
    """Condition name not in protocol.condition_definitions → Failure(ValidationError)."""

    @pytest.mark.asyncio
    async def test_unknown_condition_fails(self) -> None:
        # -- Arrange --
        rd = ReadoutDefinition(
            protocol_id=_PH,
            name="IC50",
            data_type=ReadoutDataType.NUMERIC,
        )
        cd = ConditionDefinition(
            protocol_id=_PH,
            name="Cell Line",
            data_type=ConditionDataType.TEXT,
        )
        protocol = _make_protocol([rd], [cd])

        protocol_repo = AsyncMock()
        protocol_repo.find_by_id.return_value = protocol

        readout_data_repo = AsyncMock()
        service = _make_service(protocol_repo, readout_data_repo)

        # -- Act --
        result = await service.group_by_condition(WS, protocol.id, "NonExistent")

        # -- Assert --
        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ValidationError)
        assert "NonExistent" in err.message
        # Should mention available conditions
        assert "Cell Line" in err.message

        # Should NOT call the DB query
        readout_data_repo.find_grouped_by_condition.assert_not_awaited()


class TestEmptyResults:
    """DB returns no rows → Success([])."""

    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        # -- Arrange --
        rd = ReadoutDefinition(
            protocol_id=_PH,
            name="IC50",
            data_type=ReadoutDataType.NUMERIC,
        )
        cd = ConditionDefinition(
            protocol_id=_PH,
            name="Cell Line",
            data_type=ConditionDataType.TEXT,
        )
        protocol = _make_protocol([rd], [cd])

        protocol_repo = AsyncMock()
        protocol_repo.find_by_id.return_value = protocol

        readout_data_repo = AsyncMock()
        readout_data_repo.find_grouped_by_condition.return_value = []

        service = _make_service(protocol_repo, readout_data_repo)

        # -- Act --
        result = await service.group_by_condition(WS, protocol.id, "Cell Line")

        # -- Assert --
        assert isinstance(result, Success)
        assert result.unwrap() == []


class TestProtocolNotFound:
    """Protocol not found → Failure(NotFoundError)."""

    @pytest.mark.asyncio
    async def test_protocol_not_found(self) -> None:
        # -- Arrange --
        protocol_repo = AsyncMock()
        protocol_repo.find_by_id.return_value = None  # does not exist

        readout_data_repo = AsyncMock()
        service = _make_service(protocol_repo, readout_data_repo)

        # -- Act --
        result = await service.group_by_condition(WS, uuid.uuid4(), "Cell Line")

        # -- Assert --
        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, NotFoundError)
        assert "Protocol" in err.message

        # DB query should never be reached
        readout_data_repo.find_grouped_by_condition.assert_not_awaited()


class TestMinMaxAggregation:
    """Rows with min/max aggregation use the appropriate column (min_val / max_val)."""

    @pytest.mark.asyncio
    async def test_min_aggregation_uses_min_val(self) -> None:
        rd = ReadoutDefinition(
            protocol_id=_PH,
            name="IC50",
            data_type=ReadoutDataType.NUMERIC,
        )
        cd = ConditionDefinition(
            protocol_id=_PH,
            name="Concentration",
            data_type=ConditionDataType.NUMERIC,
        )
        protocol = _make_protocol([rd], [cd])

        row = GroupRow(
            condition_value="10 uM",
            readout_definition_id=rd.id,
            readout_name="IC50",
            aggregation="min",
            unit=None,
            avg_val=8.0,
            min_val=3.0,
            max_val=15.0,
            cnt=4,
        )

        protocol_repo = AsyncMock()
        protocol_repo.find_by_id.return_value = protocol

        readout_data_repo = AsyncMock()
        readout_data_repo.find_grouped_by_condition.return_value = [row]

        service = _make_service(protocol_repo, readout_data_repo)

        result = await service.group_by_condition(WS, protocol.id, "Concentration")

        assert isinstance(result, Success)
        groups = result.unwrap()
        assert len(groups) == 1
        assert groups[0].aggregated_readouts[0].value == 3.0  # min_val used

    @pytest.mark.asyncio
    async def test_max_aggregation_uses_max_val(self) -> None:
        rd = ReadoutDefinition(
            protocol_id=_PH,
            name="Emax",
            data_type=ReadoutDataType.NUMERIC,
        )
        cd = ConditionDefinition(
            protocol_id=_PH,
            name="Concentration",
            data_type=ConditionDataType.NUMERIC,
        )
        protocol = _make_protocol([rd], [cd])

        row = GroupRow(
            condition_value="1 uM",
            readout_definition_id=rd.id,
            readout_name="Emax",
            aggregation="max",
            unit="%",
            avg_val=50.0,
            min_val=30.0,
            max_val=80.0,
            cnt=5,
        )

        protocol_repo = AsyncMock()
        protocol_repo.find_by_id.return_value = protocol

        readout_data_repo = AsyncMock()
        readout_data_repo.find_grouped_by_condition.return_value = [row]

        service = _make_service(protocol_repo, readout_data_repo)

        result = await service.group_by_condition(WS, protocol.id, "Concentration")

        assert isinstance(result, Success)
        groups = result.unwrap()
        assert groups[0].aggregated_readouts[0].value == 80.0  # max_val used


class TestRunCountIsMaxAcrossReadouts:
    """run_count is the maximum cnt across all readouts in a condition group."""

    @pytest.mark.asyncio
    async def test_run_count_is_max_count(self) -> None:
        rd_ic50 = ReadoutDefinition(
            protocol_id=_PH,
            name="IC50",
            data_type=ReadoutDataType.NUMERIC,
        )
        rd_emax = ReadoutDefinition(
            protocol_id=_PH,
            name="Emax",
            data_type=ReadoutDataType.NUMERIC,
        )
        cd = ConditionDefinition(
            protocol_id=_PH,
            name="Cell Line",
            data_type=ConditionDataType.TEXT,
        )
        protocol = _make_protocol([rd_ic50, rd_emax], [cd])
        rd_a = protocol.readout_definitions[0]
        rd_b = protocol.readout_definitions[1]

        row_a = GroupRow(
            condition_value="HEK293",
            readout_definition_id=rd_a.id,
            readout_name="IC50",
            aggregation="mean",
            unit="nM",
            avg_val=5.0,
            min_val=3.0,
            max_val=7.0,
            cnt=6,
        )
        row_b = GroupRow(
            condition_value="HEK293",
            readout_definition_id=rd_b.id,
            readout_name="Emax",
            aggregation="mean",
            unit="%",
            avg_val=90.0,
            min_val=80.0,
            max_val=100.0,
            cnt=4,
        )

        protocol_repo = AsyncMock()
        protocol_repo.find_by_id.return_value = protocol

        readout_data_repo = AsyncMock()
        readout_data_repo.find_grouped_by_condition.return_value = [row_a, row_b]

        service = _make_service(protocol_repo, readout_data_repo)

        result = await service.group_by_condition(WS, protocol.id, "Cell Line")

        assert isinstance(result, Success)
        groups = result.unwrap()
        assert len(groups) == 1
        # run_count = max(6, 4) = 6
        assert groups[0].run_count == 6
        assert len(groups[0].aggregated_readouts) == 2
