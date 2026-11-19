"""The SQL mirror of ``report_intercept`` reads every case of the precedence table alike.

Search filters, selectivity ratios and the protocol aggregates censor a curve's potency in
SQL; this runs the domain function's case table against that expression on real rows.
"""

from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration._activity_query import (
    _curve_intercept,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay._compound_rows_sql import (
    reported_curve_value,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
)
from tests.fixtures.dose_response_curves import seed_curve
from tests.fixtures.intercept_report_cases import CASES, Case

_SPEC = {"kind": "ec", "level": 50.0, "basis": "relative_percent", "label": None}
_MIDPOINT = 3.0  # a censored or n.d. primary's fitted_value: the fitted 4PL midpoint


def _intercept(case: Case) -> dict:
    iv = {"spec": _SPEC, "value": case.value, "at_bound": case.at_bound}
    return iv if case.qualifier is None else {**iv, "qualifier": case.qualifier}


async def _store(uow, workspace_id, case: Case, fitted_value: float) -> uuid.UUID:
    curve = await seed_curve(uow, workspace_id=workspace_id)
    await uow.session.flush()  # the row exists before it is updated
    raw = [{"concentration": d, "response": 50.0} for d in case.doses or ()]
    raw.append({"concentration": 0.0, "response": 1.0})  # dose 0 is never a bound
    await uow.session.execute(
        sa.text(
            "UPDATE dose_response_curves SET curve_class = :cls, fitted_value = :fv, "
            "raw_data = CAST(:raw AS jsonb), intercept_values = CAST(:iv AS jsonb) "
            "WHERE id = :id"
        ),
        {
            "id": curve.id,
            "cls": case.curve_class,
            "fv": fitted_value,
            "raw": json.dumps(raw),
            "iv": json.dumps([_intercept(case)]),
        },
    )
    return curve.id


async def _reported(uow, ids: dict[str, uuid.UUID], intercept_key) -> dict[str, tuple]:
    value, qualifier = reported_curve_value(
        DoseResponseCurveModel, *_curve_intercept(intercept_key)
    )
    rows = (
        await uow.session.execute(
            sa.select(DoseResponseCurveModel.id, value, qualifier).where(
                DoseResponseCurveModel.id.in_(ids.values())
            )
        )
    ).all()
    by_id = {r[0]: (r[1], r[2]) for r in rows}
    # SQL reports an exact value with no qualifier, and n.d. as no value.
    return {
        key: (None, "nd") if v is None else (v, q or "=")
        for key, (v, q) in ((k, by_id[i]) for k, i in ids.items())
    }


@pytest.mark.asyncio
async def test_the_sql_reported_value_follows_the_precedence_table(uow, workspace_id):
    keyed: dict[str, uuid.UUID] = {}
    primary: dict[str, uuid.UUID] = {}
    async with uow:
        for case in CASES:
            keyed[case.id] = await _store(uow, workspace_id, case, _MIDPOINT)
            # The primary is read off fitted_value (NOT NULL), which is the primary
            # intercept's value when it has one.
            if case.value is not None:
                primary[case.id] = await _store(uow, workspace_id, case, case.value)
        await uow.commit()

    async with uow:
        by_key = await _reported(uow, keyed, {"kind": "ec", "level": 50.0})
        by_primary = await _reported(uow, primary, None)

    expected = {c.id: c.expected for c in CASES}
    assert by_key == expected
    assert by_primary == {k: expected[k] for k in primary}
