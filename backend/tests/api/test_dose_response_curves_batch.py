"""API test: POST /api/v1/dose-response/curves:batch."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

# Force ORM model registration so FK resolution works in test DB.
import chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401

from tests.fixtures.dose_response_curves import seed_curve
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.fixture
async def seeded_curve_ids(
    uow: AsyncUnitOfWork, workspace_id: uuid.UUID
) -> list[uuid.UUID]:
    """Seed 3 curves in the test workspace and return their IDs."""
    async with uow:
        c1 = await seed_curve(uow, workspace_id=workspace_id)
        c2 = await seed_curve(uow, workspace_id=workspace_id)
        c3 = await seed_curve(uow, workspace_id=workspace_id)
        await uow.commit()
    return [c1.id, c2.id, c3.id]


@pytest.fixture
async def foreign_curve_id(
    uow: AsyncUnitOfWork,
) -> uuid.UUID:
    """Seed a curve in a *different* workspace and return its ID."""
    foreign_ws = uuid.uuid4()
    async with uow:
        c = await seed_curve(uow, workspace_id=foreign_ws)
        await uow.commit()
    return c.id


@pytest.mark.asyncio
class TestBatchCurvesEndpoint:
    async def test_returns_curves_for_ids(
        self, client: AsyncClient, seeded_curve_ids: list[uuid.UUID]
    ) -> None:
        body = {"curve_ids": [str(i) for i in seeded_curve_ids[:2]]}
        resp = await client.post("/api/v1/dose-response/curves:batch", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert {c["id"] for c in data["curves"]} == {str(i) for i in seeded_curve_ids[:2]}
        # Sanity-check the response shape matches DoseResponseCurveResponse.
        first = data["curves"][0]
        assert "raw_data" in first
        assert "fitted_value" in first
        # raw_data is condensed to {x, y} shape
        if first.get("raw_data"):
            pt = first["raw_data"][0]
            assert "x" in pt and "y" in pt
            assert "concentration" not in pt

    async def test_empty_input_returns_empty(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/dose-response/curves:batch", json={"curve_ids": []}
        )
        assert resp.status_code == 200
        assert resp.json() == {"curves": []}

    async def test_max_500_ids(self, client: AsyncClient) -> None:
        body = {"curve_ids": [str(uuid.uuid4()) for _ in range(501)]}
        resp = await client.post("/api/v1/dose-response/curves:batch", json=body)
        assert resp.status_code == 422

    async def test_workspace_isolation(
        self, client: AsyncClient, foreign_curve_id: uuid.UUID
    ) -> None:
        body = {"curve_ids": [str(foreign_curve_id)]}
        resp = await client.post("/api/v1/dose-response/curves:batch", json=body)
        assert resp.status_code == 200
        assert resp.json()["curves"] == []
