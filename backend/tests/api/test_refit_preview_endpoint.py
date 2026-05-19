"""API test: POST /api/v1/dose-response-curves/{curve_id}/refit-preview.

Compute-only preview refit endpoint. Fired by the FE on every draft toggle
during point editing; must never persist, never audit, never auto-exclude.
The existing /refit endpoint handles commit on Save (covered separately).

These tests are intentionally narrow — route exists, returns 200 for a known
curve_id, 404 for an unknown one. Compute correctness is owned by the use
case's unit tests in tests/unit/application/screening/test_refit_dose_response_preview.py.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

# Force ORM model registration so FK resolution works in the test DB.
import cellar.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401

from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import CurveType
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (
    SQLAlchemyDoseResponseCurveRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fixtures.dose_response_curves import (
    _insert_org,
    _insert_protocol,
    _insert_readout_def,
    _insert_run,
)


async def _seed_curve_with_points(
    uow: AsyncUnitOfWork, *, workspace_id: uuid.UUID
) -> DoseResponseCurve:
    """Seed a curve with enough raw_data points to be refittable.

    The shared ``seed_curve`` helper creates a curve with ``raw_data=[]``,
    which the fitter rejects. Refit-preview needs ≥3 points to attempt a
    4PL fit, so we seed five log-spaced doses with a sigmoid response.
    """
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    readout_def_id = uuid.uuid4()

    await _insert_org(uow, org_id, workspace_id)
    await _insert_protocol(uow, protocol_id, workspace_id)
    await _insert_readout_def(uow, readout_def_id, protocol_id)
    await _insert_run(uow, run_id, protocol_id, workspace_id)

    # Synthetic sigmoid: 6 points spanning ~3 logs of concentration.
    raw_data = [
        {"concentration": 0.01, "response": 95.0},
        {"concentration": 0.1, "response": 80.0},
        {"concentration": 1.0, "response": 50.0},
        {"concentration": 10.0, "response": 20.0},
        {"concentration": 100.0, "response": 5.0},
        {"concentration": 1000.0, "response": 2.0},
    ]

    curve = DoseResponseCurve(
        workspace_id=workspace_id,
        molecule_id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        protocol_id=protocol_id,
        run_id=run_id,
        readout_definition_id=readout_def_id,
        curve_type=CurveType.IC50,
        fitted_value=1.0,
        hill_slope=1.0,
        top=100.0,
        bottom=0.0,
        r_squared=0.95,
        num_points=len(raw_data),
        raw_data=raw_data,
    )

    repo = SQLAlchemyDoseResponseCurveRepository(uow)
    await repo.save(curve)
    return curve


@pytest.fixture
async def seeded_curve(
    uow: AsyncUnitOfWork, workspace_id: uuid.UUID
) -> DoseResponseCurve:
    async with uow:
        curve = await _seed_curve_with_points(uow, workspace_id=workspace_id)
        await uow.commit()
    return curve


@pytest.mark.asyncio
class TestRefitPreviewEndpoint:
    async def test_returns_200_with_fit_shape(
        self, client: AsyncClient, seeded_curve: DoseResponseCurve
    ) -> None:
        response = await client.post(
            f"/api/v1/dose-response-curves/{seeded_curve.id}/refit-preview",
            json={"excluded_indices": []},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        # Required response fields per PreviewRefitResult
        assert "fitted_value" in body
        assert "hill_slope" in body
        assert "top" in body
        assert "bottom" in body
        assert "r_squared" in body
        assert "confidence_interval_low" in body
        assert "confidence_interval_high" in body
        assert "curve_class" in body
        assert "points_in_fit" in body
        assert "points_total" in body
        assert body["points_total"] == 6
        assert body["points_in_fit"] == 6

    async def test_excluded_indices_reduce_points_in_fit(
        self, client: AsyncClient, seeded_curve: DoseResponseCurve
    ) -> None:
        response = await client.post(
            f"/api/v1/dose-response-curves/{seeded_curve.id}/refit-preview",
            json={"excluded_indices": [0, 5]},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["points_total"] == 6
        assert body["points_in_fit"] == 4

    async def test_returns_404_for_unknown_curve(
        self, client: AsyncClient
    ) -> None:
        unknown = uuid.uuid4()
        response = await client.post(
            f"/api/v1/dose-response-curves/{unknown}/refit-preview",
            json={"excluded_indices": []},
        )
        assert response.status_code == 404

    async def test_empty_body_defaults_to_no_exclusions(
        self, client: AsyncClient, seeded_curve: DoseResponseCurve
    ) -> None:
        response = await client.post(
            f"/api/v1/dose-response-curves/{seeded_curve.id}/refit-preview",
            json={},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["points_in_fit"] == 6
