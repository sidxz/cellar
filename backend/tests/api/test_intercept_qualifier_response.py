"""API test: every curve response carries each intercept's qualifier.

An ``nd`` intercept goes out with value null; one stored before qualifiers existed goes
out with qualifier null (the reader applies today's rules).
"""

from __future__ import annotations

import math
import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient

import cellar.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401
from cellar.domain.screening_assay.curve_fitting import InterceptValue
from cellar.domain.screening_assay.dose_response_config import InterceptSpec
from cellar.domain.screening_assay.enums import CurveClass, InterceptKind
from cellar.domain.shared.aggregation_types import ValueQualifier
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (  # noqa: E501
    SQLAlchemyDoseResponseCurveRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fixtures.dose_response_curves import seed_curve

_DOSES = [0.0002, 0.002, 0.02, 0.2, 2.0, 20.0]


def _iv(level: float, value: float, qualifier: ValueQualifier | None) -> InterceptValue:
    return InterceptValue(
        spec=InterceptSpec(kind=InterceptKind.EC, level=level),
        value=value,
        confidence_interval_low=None,
        confidence_interval_high=None,
        qualifier=qualifier,
    )


async def _seed(uow: AsyncUnitOfWork, workspace_id: uuid.UUID):
    async with uow:
        curve = await seed_curve(uow, workspace_id=workspace_id)
        curve.curve_class = CurveClass.ACTIVE_ALL_DOSES
        curve.raw_data = [{"concentration": d, "response": 92.0} for d in _DOSES]
        curve.intercept_values = [
            _iv(50.0, 0.0002, ValueQualifier.LT),
            _iv(90.0, math.nan, ValueQualifier.ND),
            _iv(10.0, 0.0002, None),  # stored before qualifiers
        ]
        await SQLAlchemyDoseResponseCurveRepository(uow).save(curve)
        await uow.commit()
    return curve


def _shape(intercepts: list[dict]) -> list[tuple]:
    return [(iv["spec"]["level"], iv["value"], iv["qualifier"]) for iv in intercepts]


_EXPECTED = [(50.0, 0.0002, "<"), (90.0, None, "nd"), (10.0, 0.0002, None)]


@pytest.mark.asyncio
async def test_run_curves_carry_each_intercepts_qualifier(
    client: AsyncClient, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
) -> None:
    curve = await _seed(uow, workspace_id)

    response = await client.get(
        "/api/v1/dose-response-curves", params={"run_id": str(curve.run_id)}
    )

    assert response.status_code == 200, response.text
    (body,) = response.json()
    assert body["curve_class"] == "active_all_doses"
    assert _shape(body["intercept_values"]) == _EXPECTED


@pytest.mark.asyncio
async def test_molecule_activity_detail_carries_each_intercepts_qualifier(
    client: AsyncClient, uow: AsyncUnitOfWork, workspace_id: uuid.UUID
) -> None:
    curve = await _seed(uow, workspace_id)
    async with uow:
        await uow.session.execute(
            sa.text("UPDATE runs SET status = 'completed' WHERE id = :id"), {"id": curve.run_id}
        )
        await uow.commit()

    response = await client.get(f"/api/v1/molecules/{curve.molecule_id}/activity-detail")

    assert response.status_code == 200, response.text
    (group,) = response.json()["protocols"]
    (detail,) = group["curves"]
    assert _shape(detail["intercept_values"]) == _EXPECTED
