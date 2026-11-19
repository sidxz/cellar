"""Integration test: intercept qualifiers round-trip through the DR curve repo.

An ``nd`` intercept's value is NaN in the domain, which Postgres JSONB rejects: it is
stored as JSON null and read back as NaN. A row stored before qualifiers existed has no
``qualifier`` key and reads as ``None`` (today's rules), never as ``=``.
"""

from __future__ import annotations

import math

import pytest
import sqlalchemy as sa

from cellar.domain.screening_assay.curve_fitting import InterceptValue
from cellar.domain.screening_assay.dose_response_config import InterceptSpec
from cellar.domain.screening_assay.enums import InterceptKind
from cellar.domain.shared.aggregation_types import ValueQualifier
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.dose_response_curve_repository import (  # noqa: E501
    SQLAlchemyDoseResponseCurveRepository,
)
from tests.fixtures.dose_response_curves import seed_curve

EC50 = InterceptSpec(kind=InterceptKind.EC, level=50.0)
EC90 = InterceptSpec(kind=InterceptKind.EC, level=90.0)


@pytest.mark.asyncio
async def test_qualifiers_round_trip_and_nd_is_stored_as_null(uow, workspace_id):
    async with uow:
        curve = await seed_curve(uow, workspace_id=workspace_id)
        curve.intercept_values = [
            InterceptValue(
                spec=EC50,
                value=0.0002,
                confidence_interval_low=None,
                confidence_interval_high=None,
                qualifier=ValueQualifier.LT,
            ),
            InterceptValue(
                spec=EC90,
                value=math.nan,
                confidence_interval_low=None,
                confidence_interval_high=None,
                qualifier=ValueQualifier.ND,
            ),
        ]
        await SQLAlchemyDoseResponseCurveRepository(uow).save(curve)
        await uow.commit()

    async with uow:
        stored = (
            await uow.session.execute(
                sa.text("SELECT intercept_values FROM dose_response_curves WHERE id = :id"),
                {"id": curve.id},
            )
        ).scalar_one()
        (fetched,) = await SQLAlchemyDoseResponseCurveRepository(uow).find_by_ids(
            workspace_id, [curve.id]
        )

    assert [(d["value"], d["qualifier"]) for d in stored] == [(0.0002, "<"), (None, "nd")]
    lt, nd = fetched.intercept_values
    assert (lt.value, lt.qualifier, lt.at_bound) == (0.0002, ValueQualifier.LT, False)
    assert math.isnan(nd.value)
    assert nd.qualifier == ValueQualifier.ND


@pytest.mark.asyncio
async def test_a_row_stored_before_qualifiers_reads_none(uow, workspace_id):
    async with uow:
        curve = await seed_curve(uow, workspace_id=workspace_id)
        await uow.commit()

    async with uow:
        legacy = (
            '[{"spec": {"kind": "ec", "level": 50.0, "basis": "relative_percent", '
            '"label": null}, "value": 3.2, "ci_low": 1.0, "ci_high": 9.0, "at_bound": true}]'
        )
        await uow.session.execute(
            sa.text(
                "UPDATE dose_response_curves SET intercept_values = CAST(:iv AS jsonb) "
                "WHERE id = :id"
            ),
            {"iv": legacy, "id": curve.id},
        )
        await uow.commit()

    async with uow:
        (fetched,) = await SQLAlchemyDoseResponseCurveRepository(uow).find_by_ids(
            workspace_id, [curve.id]
        )

    (iv,) = fetched.intercept_values
    assert (iv.value, iv.at_bound, iv.qualifier) == (3.2, True, None)
