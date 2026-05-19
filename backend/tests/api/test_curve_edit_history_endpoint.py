"""API test: GET /api/v1/dose-response-curves/{curve_id}/edit-history.

The endpoint surfaces ``CURVE_POINT_EXCLUSION`` (and any other) audit
operations written against a ``DoseResponseCurve``, newest-first. Used by
the FE edit-history popover on the DR chart.

These tests are intentionally narrow — route exists, returns 200, response
shape matches the contract. Sorting/projection correctness is owned by the
use case's unit tests in
``tests/unit/application/screening/test_get_curve_edit_history.py``.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

# Force ORM model registration so FK resolution works in the test DB.
import cellar.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401

from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.domain.audit_compliance.enums import AuditAction, OperationType
from cellar.domain.audit_compliance.models import AuditEntry
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import CurveType
from cellar.infrastructure.persistence.sqlalchemy.audit.audit_repository import (
    SQLAlchemyAuditRepository,
)
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


async def _seed_curve(
    uow: AsyncUnitOfWork, *, workspace_id: uuid.UUID
) -> DoseResponseCurve:
    """Seed a minimal curve so the endpoint has a valid {curve_id} to query."""
    org_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    run_id = uuid.uuid4()
    readout_def_id = uuid.uuid4()

    await _insert_org(uow, org_id, workspace_id)
    await _insert_protocol(uow, protocol_id, workspace_id)
    await _insert_readout_def(uow, readout_def_id, protocol_id)
    await _insert_run(uow, run_id, protocol_id, workspace_id)

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
        num_points=3,
    )

    repo = SQLAlchemyDoseResponseCurveRepository(uow)
    await repo.save(curve)
    return curve


@pytest.fixture
async def seeded_curve(
    uow: AsyncUnitOfWork, workspace_id: uuid.UUID
) -> DoseResponseCurve:
    async with uow:
        curve = await _seed_curve(uow, workspace_id=workspace_id)
        await uow.commit()
    return curve


@pytest.fixture
async def seeded_curve_with_history(
    api_app,
    seeded_curve: DoseResponseCurve,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> DoseResponseCurve:
    """Seed an audit op against ``seeded_curve``.

    Uses the production ``AuditRecordingService`` bound by the test app's
    DI container so we audit through the exact code path the use case does.
    """
    from cellar.infrastructure.di.container import (  # noqa: WPS433 — DI per-test
        create_container,
    )

    container = create_container()
    audit_repo = container[SQLAlchemyAuditRepository]
    recorder = AuditRecordingService(audit_repo)

    await recorder.record(
        workspace_id=workspace_id,
        operation_type=OperationType.CURVE_POINT_EXCLUSION,
        entity_type="DoseResponseCurve",
        entity_id=seeded_curve.id,
        user_id=user_id,
        entries=[
            AuditEntry(
                entity_type="DoseResponseCurve",
                entity_id=seeded_curve.id,
                field_name="excluded_points",
                action=AuditAction.UPDATE,
                old_value="[]",
                new_value='[{"idx": 0, "reason": "outlier"}]',
            )
        ],
        reason="outlier: contaminated well",
    )
    return seeded_curve


@pytest.mark.asyncio
class TestGetCurveEditHistoryEndpoint:
    async def test_returns_200_and_empty_events_for_curve_without_history(
        self, client: AsyncClient, seeded_curve: DoseResponseCurve
    ) -> None:
        response = await client.get(
            f"/api/v1/dose-response-curves/{seeded_curve.id}/edit-history",
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert "events" in body
        assert body["events"] == []

    async def test_returns_seeded_audit_event(
        self,
        client: AsyncClient,
        seeded_curve_with_history: DoseResponseCurve,
    ) -> None:
        response = await client.get(
            f"/api/v1/dose-response-curves/{seeded_curve_with_history.id}/edit-history",
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert isinstance(body["events"], list)
        assert len(body["events"]) >= 1
        event = body["events"][0]
        assert event["operation_type"] == "curve_point_exclusion"
        assert event["reason"] == "outlier: contaminated well"
        assert event["user_id"] is not None
        assert "timestamp" in event
        assert isinstance(event["entries"], list)
        assert any(e["field_name"] == "excluded_points" for e in event["entries"])

    async def test_returns_200_with_empty_events_for_unknown_curve(
        self, client: AsyncClient
    ) -> None:
        """Unknown curve_id is not an error — it simply has no audit history.

        The endpoint queries the audit log by entity_id; it does NOT verify
        the curve exists. Returning 200 with ``events: []`` is the consistent
        shape and avoids a second DB lookup just to validate.
        """
        unknown = uuid.uuid4()
        response = await client.get(
            f"/api/v1/dose-response-curves/{unknown}/edit-history",
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"events": []}
