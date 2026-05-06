"""Tests for MoleculeActivityService.enrich_molecules — ActivityValue enrichment."""

from __future__ import annotations

import uuid
from typing import Self
from unittest.mock import AsyncMock

import pytest

from chem_vault.application.screening.molecule_activity_service import (
    MoleculeActivityService,
)
from chem_vault.domain.screening_assay.dose_response_curve import DoseResponseCurve
from chem_vault.domain.screening_assay.enums import CurveClass, CurveType

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

WS = uuid.uuid4()
MOL_ID = uuid.uuid4()
PROTO_ID = uuid.uuid4()


class _FakeUoW:
    is_active = True

    async def commit(self) -> list:
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


def _make_curve(
    *,
    molecule_id: uuid.UUID = MOL_ID,
    protocol_id: uuid.UUID = PROTO_ID,
    curve_type: CurveType = CurveType.IC50,
    fitted_value: float = 5.2,
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
        batch_id=uuid.uuid4(),
        protocol_id=protocol_id,
        run_id=uuid.uuid4(),
        curve_type=curve_type,
        fitted_value=fitted_value,
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


def _make_service(curve_repo=None) -> MoleculeActivityService:
    protocol_repo = AsyncMock()
    # find_by_ids returns [] by default — service falls back to "uM" for
    # IC50 unit decoration. Tests that need a specific unit should override.
    protocol_repo.find_by_ids = AsyncMock(return_value=[])
    return MoleculeActivityService(
        uow=_FakeUoW(),
        readout_repo=AsyncMock(),
        curve_repo=curve_repo or AsyncMock(),
        protocol_repo=protocol_repo,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEnrichMoleculesWithCurveParams:
    """enrich_molecules populates raw_data and curve_params from DoseResponseCurve."""

    @pytest.mark.asyncio
    async def test_curve_params_and_raw_data_populated(self) -> None:
        """ActivityValue should contain condensed raw_data and full curve params."""
        raw_points = [
            {"concentration": 0.01, "response": 95.0},
            {"concentration": 0.1, "response": 80.0},
            {"concentration": 1.0, "response": 50.0},
            {"concentration": 10.0, "response": 10.0},
        ]
        curve = _make_curve(raw_data=raw_points)

        curve_repo = AsyncMock()
        # find_best_curves_for_molecules returns {mol_id -> {proto_id -> curve}}
        curve_repo.find_best_curves_for_molecules.return_value = {
            MOL_ID: {PROTO_ID: curve},
        }

        service = _make_service(curve_repo=curve_repo)
        col_spec = f"drc:{PROTO_ID}:ic50"

        result = await service.enrich_molecules(WS, [MOL_ID], [col_spec])

        assert MOL_ID in result
        av = result[MOL_ID][col_spec]

        # Basic fields
        assert av.value == 5.2
        assert av.unit == "uM"
        assert av.source == "dose_response"
        assert av.curve_type == "ic50"
        assert av.r_squared == 0.97
        assert av.data_point_count == 8

        # raw_data condensed to [{x, y}]
        assert av.raw_data is not None
        assert len(av.raw_data) == 4
        assert av.raw_data[0] == {"x": 0.01, "y": 95.0}
        assert av.raw_data[3] == {"x": 10.0, "y": 10.0}

        # curve_params
        assert av.curve_params is not None
        assert av.curve_params.hill_slope == -1.1
        assert av.curve_params.top == 100.0
        assert av.curve_params.bottom == 0.5
        assert av.curve_params.num_points == 8
        assert av.curve_params.curve_class == "full"
        assert av.curve_params.confidence_interval_low == 3.8
        assert av.curve_params.confidence_interval_high == 7.1

    @pytest.mark.asyncio
    async def test_curve_without_raw_data(self) -> None:
        """When raw_data is empty/None, raw_data on ActivityValue is None."""
        curve = _make_curve(raw_data=None)

        curve_repo = AsyncMock()
        curve_repo.find_best_curves_for_molecules.return_value = {
            MOL_ID: {PROTO_ID: curve},
        }

        service = _make_service(curve_repo=curve_repo)
        col_spec = f"drc:{PROTO_ID}:ic50"

        result = await service.enrich_molecules(WS, [MOL_ID], [col_spec])

        av = result[MOL_ID][col_spec]
        assert av.raw_data is None
        # curve_params should still be populated
        assert av.curve_params is not None
        assert av.curve_params.hill_slope == -1.1

    @pytest.mark.asyncio
    async def test_curve_without_curve_class(self) -> None:
        """When curve_class is None, CurveParams.curve_class is None."""
        curve = _make_curve(
            curve_class=None,
            confidence_interval_low=None,
            confidence_interval_high=None,
        )

        curve_repo = AsyncMock()
        curve_repo.find_best_curves_for_molecules.return_value = {
            MOL_ID: {PROTO_ID: curve},
        }

        service = _make_service(curve_repo=curve_repo)
        col_spec = f"drc:{PROTO_ID}:ic50"

        result = await service.enrich_molecules(WS, [MOL_ID], [col_spec])

        av = result[MOL_ID][col_spec]
        assert av.curve_params is not None
        assert av.curve_params.curve_class is None
        assert av.curve_params.confidence_interval_low is None
        assert av.curve_params.confidence_interval_high is None


class TestEnrichMoleculesEmptyInputs:
    """Edge cases for empty inputs."""

    @pytest.mark.asyncio
    async def test_empty_molecule_ids_returns_empty(self) -> None:
        service = _make_service()
        result = await service.enrich_molecules(WS, [], [f"drc:{PROTO_ID}:ic50"])
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_columns_returns_empty(self) -> None:
        service = _make_service()
        result = await service.enrich_molecules(WS, [MOL_ID], [])
        assert result == {}

    @pytest.mark.asyncio
    async def test_no_matching_curve_returns_empty(self) -> None:
        """When the curve repo returns no curves for the molecule."""
        curve_repo = AsyncMock()
        curve_repo.find_best_curves_for_molecules.return_value = {}

        service = _make_service(curve_repo=curve_repo)
        col_spec = f"drc:{PROTO_ID}:ic50"

        result = await service.enrich_molecules(WS, [MOL_ID], [col_spec])
        assert result == {}
