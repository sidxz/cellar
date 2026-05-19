"""API test: POST /api/v1/dose-response-curves/{curve_id}/refit.

Task 2.9 — extends the existing /refit endpoint to accept the Sprint 2 rich
exclusion payload (``exclusions[]`` + ``save_reason`` + ``save_note``) while
preserving Sprint 1 back-compat (bare ``excluded_indices`` / legacy
``excluded_point_indices`` + ``disable_auto_outliers``).

The two shapes are mutually exclusive — if ``exclusions`` is present, the use
case runs the Sprint 2 path (creates an AuditOperation, persists rich
ExcludedPointDetail entries). Otherwise it runs the Sprint 1 path (bare index
list, no audit). Branching lives in the use case; the route is a pass-through.
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
    """Seed a curve with ≥6 raw_data points (Sprint 2 test exercises idx=5)."""
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    readout_def_id = uuid.uuid4()

    await _insert_org(uow, org_id, workspace_id)
    await _insert_protocol(uow, protocol_id, workspace_id)
    await _insert_readout_def(uow, readout_def_id, protocol_id)
    await _insert_run(uow, run_id, protocol_id, workspace_id)

    # 6 log-spaced doses, synthetic sigmoid response.
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
class TestRefitEndpoint:
    async def test_accepts_rich_exclusions_payload(
        self, client: AsyncClient, seeded_curve: DoseResponseCurve
    ) -> None:
        """Sprint 2 callers send full ExcludedPointDetail shape + audit context."""
        response = await client.post(
            f"/api/v1/dose-response-curves/{seeded_curve.id}/refit",
            json={
                "exclusions": [
                    {
                        "idx": 2,
                        "source": "manual",
                        "excluded": True,
                        "reason": "outlier",
                        "note": "dispense spike",
                    },
                    {
                        "idx": 5,
                        "source": "auto_3sigma",
                        "excluded": False,
                        "reason": "auto_3sigma",
                        "note": None,
                    },
                ],
                "save_reason": "outlier",
                "save_note": "lid dropped on plate",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        excluded = body["excluded_points"]
        # The manual exclusion was applied.
        manual = next(e for e in excluded if e["idx"] == 2)
        assert manual["excluded"] is True
        assert manual["reason"] == "outlier"
        assert manual["source"] == "manual"
        # The suggestion was preserved (excluded=False).
        suggestion = next(e for e in excluded if e["idx"] == 5)
        assert suggestion["excluded"] is False
        assert suggestion["source"] == "auto_3sigma"

    async def test_sprint1_back_compat_excluded_indices(
        self, client: AsyncClient, seeded_curve: DoseResponseCurve
    ) -> None:
        """Sprint 1 callers (bare excluded_point_indices) keep working unchanged."""
        response = await client.post(
            f"/api/v1/dose-response-curves/{seeded_curve.id}/refit",
            json={
                "excluded_point_indices": [2],
                "disable_auto_outliers": True,
            },
        )
        assert response.status_code == 200, response.text
