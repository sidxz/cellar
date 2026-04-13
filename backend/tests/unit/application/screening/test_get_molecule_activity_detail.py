"""Tests for GetMoleculeActivityDetail use case."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Success

from chem_vault.application.screening.get_molecule_activity_detail import (
    GetMoleculeActivityDetail,
    MoleculeActivityDetail,
    MoleculeActivityDetailQuery,
)
from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
from chem_vault.domain.screening_assay.enums import CurveClass, CurveType, ProtocolType
from chem_vault.domain.shared.events import DomainEvent
from tests.fakes.fake_auth import FakeAuth

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

WS = uuid.uuid4()
MOL_ID = uuid.uuid4()
PROTO_A = uuid.uuid4()
PROTO_B = uuid.uuid4()


class _FakeUoW:
    """Minimal UoW stand-in for unit tests."""

    async def commit(self) -> list[DomainEvent]:
        return []

    async def rollback(self) -> None:
        pass

    @property
    def is_active(self) -> bool:
        return True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class _FakeProtocol:
    """Minimal stand-in for AssayProtocol."""

    def __init__(
        self,
        *,
        id: uuid.UUID,
        name: str,
        protocol_type: ProtocolType = ProtocolType.BIOCHEMICAL,
        target_id: uuid.UUID | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.protocol_type = protocol_type
        self.target_id = target_id


def _make_curve(
    *,
    molecule_id: uuid.UUID = MOL_ID,
    protocol_id: uuid.UUID = PROTO_A,
    run_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
    curve_type: CurveType = CurveType.IC50,
    fitted_value: float = 5.2,
    fitted_unit: str = "uM",
    hill_slope: float = -1.1,
    top: float = 100.0,
    bottom: float = 0.5,
    r_squared: float = 0.97,
    num_points: int = 8,
    curve_class: CurveClass | None = CurveClass.FULL,
    raw_data: list[dict] | None = None,
    confidence_interval_low: float | None = 3.8,
    confidence_interval_high: float | None = 7.1,
) -> DoseResponseCurve:
    return DoseResponseCurve(
        workspace_id=WS,
        molecule_id=molecule_id,
        batch_id=batch_id or uuid.uuid4(),
        protocol_id=protocol_id,
        run_id=run_id or uuid.uuid4(),
        curve_type=curve_type,
        fitted_value=fitted_value,
        fitted_unit=fitted_unit,
        hill_slope=hill_slope,
        top=top,
        bottom=bottom,
        r_squared=r_squared,
        num_points=num_points,
        curve_class=curve_class,
        raw_data=raw_data,
        confidence_interval_low=confidence_interval_low,
        confidence_interval_high=confidence_interval_high,
    )


def _make_uc(
    curve_repo: AsyncMock | None = None,
    protocol_repo: AsyncMock | None = None,
) -> GetMoleculeActivityDetail:
    return GetMoleculeActivityDetail(
        uow=_FakeUoW(),
        curve_repo=curve_repo or AsyncMock(),
        protocol_repo=protocol_repo or AsyncMock(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGroupedByProtocol:
    """Curves from multiple protocols are correctly grouped."""

    @pytest.mark.asyncio
    async def test_returns_curves_grouped_by_protocol(self) -> None:
        """Two protocols, multiple curves each, should produce two groups."""
        target_id = uuid.uuid4()
        curves = [
            _make_curve(protocol_id=PROTO_A, r_squared=0.95),
            _make_curve(protocol_id=PROTO_A, r_squared=0.99),
            _make_curve(protocol_id=PROTO_B, r_squared=0.80, curve_type=CurveType.EC50),
        ]

        curve_repo = AsyncMock()
        curve_repo.find_by_molecule.return_value = curves

        protocol_repo = AsyncMock()
        protocol_repo.find_by_ids.return_value = [
            _FakeProtocol(id=PROTO_A, name="Kinase IC50", target_id=target_id),
            _FakeProtocol(
                id=PROTO_B, name="Cell Viability", protocol_type=ProtocolType.CELL_BASED
            ),
        ]

        auth = FakeAuth(workspace_id=WS)
        query = MoleculeActivityDetailQuery(workspace_id=WS, molecule_id=MOL_ID)

        uc = _make_uc(curve_repo=curve_repo, protocol_repo=protocol_repo)
        result = await uc(query, auth=auth)

        assert isinstance(result, Success)
        detail: MoleculeActivityDetail = result.unwrap()

        assert detail.molecule_id == MOL_ID
        assert len(detail.protocols) == 2

        # Find protocol groups
        proto_a_group = next(g for g in detail.protocols if g.protocol_id == PROTO_A)
        proto_b_group = next(g for g in detail.protocols if g.protocol_id == PROTO_B)

        # Protocol A: 2 curves, sorted by r_squared DESC
        assert proto_a_group.protocol_name == "Kinase IC50"
        assert proto_a_group.protocol_type == "biochemical"
        assert proto_a_group.target_id == target_id
        assert len(proto_a_group.curves) == 2
        assert proto_a_group.curves[0].r_squared == 0.99
        assert proto_a_group.curves[1].r_squared == 0.95

        # Protocol B: 1 curve
        assert proto_b_group.protocol_name == "Cell Viability"
        assert proto_b_group.protocol_type == "cell_based"
        assert proto_b_group.target_id is None
        assert len(proto_b_group.curves) == 1
        assert proto_b_group.curves[0].curve_type == "ec50"

    @pytest.mark.asyncio
    async def test_curve_detail_fields(self) -> None:
        """CurveDetail should faithfully map all fields from the domain entity."""
        raw_points = [
            {"concentration": 0.01, "response": 95.0},
            {"concentration": 1.0, "response": 50.0},
        ]
        curve = _make_curve(
            raw_data=raw_points,
            curve_class=CurveClass.PARTIAL,
            confidence_interval_low=2.0,
            confidence_interval_high=8.0,
        )

        curve_repo = AsyncMock()
        curve_repo.find_by_molecule.return_value = [curve]

        protocol_repo = AsyncMock()
        protocol_repo.find_by_ids.return_value = [
            _FakeProtocol(id=PROTO_A, name="Test"),
        ]

        auth = FakeAuth(workspace_id=WS)
        query = MoleculeActivityDetailQuery(workspace_id=WS, molecule_id=MOL_ID)

        uc = _make_uc(curve_repo=curve_repo, protocol_repo=protocol_repo)
        result = await uc(query, auth=auth)

        detail = result.unwrap()
        cd = detail.protocols[0].curves[0]

        assert cd.curve_id == curve.id
        assert cd.run_id == curve.run_id
        assert cd.batch_id == curve.batch_id
        assert cd.curve_type == "ic50"
        assert cd.fitted_value == 5.2
        assert cd.fitted_unit == "uM"
        assert cd.hill_slope == -1.1
        assert cd.r_squared == 0.97
        assert cd.curve_class == "partial"
        assert cd.top == 100.0
        assert cd.bottom == 0.5
        assert cd.num_points == 8
        assert cd.confidence_interval_low == 2.0
        assert cd.confidence_interval_high == 8.0
        assert cd.raw_data == raw_points


class TestEmptyResults:
    """Edge cases when no curves exist."""

    @pytest.mark.asyncio
    async def test_returns_empty_protocols_when_no_curves(self) -> None:
        """An empty protocols list when there are no curves for the molecule."""
        curve_repo = AsyncMock()
        curve_repo.find_by_molecule.return_value = []

        protocol_repo = AsyncMock()

        auth = FakeAuth(workspace_id=WS)
        query = MoleculeActivityDetailQuery(workspace_id=WS, molecule_id=MOL_ID)

        uc = _make_uc(curve_repo=curve_repo, protocol_repo=protocol_repo)
        result = await uc(query, auth=auth)

        assert isinstance(result, Success)
        detail = result.unwrap()
        assert detail.molecule_id == MOL_ID
        assert detail.protocols == []

        # Protocol repo should NOT be called when no curves
        protocol_repo.find_by_ids.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_protocol_gets_fallback_name(self) -> None:
        """When protocol_repo doesn't return a protocol, use 'Unknown' fallback."""
        curve = _make_curve(protocol_id=PROTO_A)

        curve_repo = AsyncMock()
        curve_repo.find_by_molecule.return_value = [curve]

        protocol_repo = AsyncMock()
        protocol_repo.find_by_ids.return_value = []  # No protocol found

        auth = FakeAuth(workspace_id=WS)
        query = MoleculeActivityDetailQuery(workspace_id=WS, molecule_id=MOL_ID)

        uc = _make_uc(curve_repo=curve_repo, protocol_repo=protocol_repo)
        result = await uc(query, auth=auth)

        detail = result.unwrap()
        assert len(detail.protocols) == 1
        assert detail.protocols[0].protocol_name == "Unknown"
        assert detail.protocols[0].protocol_type == "unknown"
        assert detail.protocols[0].target_id is None
