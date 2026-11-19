"""API test: PATCH /api/v1/dose-response-curves/{curve_id}/classify.

A scientist may set any class by hand, "active at all doses" included; the change shows
in the curve's edit history. An unknown class is refused.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fixtures.dose_response_curves import seed_curve

pytestmark = pytest.mark.asyncio


async def _curve_id(uow: AsyncUnitOfWork, workspace_id: uuid.UUID) -> uuid.UUID:
    async with uow:
        curve = await seed_curve(uow, workspace_id=workspace_id)
        await uow.commit()
    return curve.id


async def test_active_at_all_doses_is_set_by_hand_and_recorded(
    client: AsyncClient, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
) -> None:
    curve_id = await _curve_id(uow, workspace_id)

    response = await client.patch(
        f"/api/v1/dose-response-curves/{curve_id}/classify",
        json={"curve_class": "active_all_doses"},
    )
    history = await client.get(f"/api/v1/dose-response-curves/{curve_id}/edit-history")

    assert response.status_code == 200, response.text
    assert response.json()["curve_class"] == "active_all_doses"
    assert history.status_code == 200, history.text
    (event,) = history.json()["events"]
    assert event["operation_type"] == "property_edit"
    assert [(e["field_name"], e["old_value"], e["new_value"]) for e in event["entries"]] == [
        ("curve_class", None, "active_all_doses")  # the seed curve had no class
    ]


async def test_an_unknown_class_is_refused(
    client: AsyncClient, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
) -> None:
    curve_id = await _curve_id(uow, workspace_id)

    response = await client.patch(
        f"/api/v1/dose-response-curves/{curve_id}/classify", json={"curve_class": "potent"}
    )

    assert response.status_code == 422, response.text
