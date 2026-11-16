"""Protocol Activity summary over the real SQL reader: one normalization layer per readout."""

from __future__ import annotations

import json
import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from returns.result import Success

from cellar.application.screening.get_protocol_activity import (
    VALID_STATUSES,
    ActivitySummaryV2,
    GetProtocolActivityQuery,
    GetProtocolActivitySummary,
)
from cellar.application.screening.protocol_activity_reader import (
    ActivityAggregates,
    AggregateScope,
)
from cellar.application.screening.run_aggregation import combine_replicates
from cellar.domain.screening_assay.aggregation_types import ValueQualifier
from cellar.domain.screening_assay.enums import primary_normalization
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_activity_reader import (
    SQLAlchemyProtocolActivityReader,
)
from tests.fakes.fake_auth import FakeAuth
from tests.integration import _screening_seed as seed


async def _summary(
    uow,
    session_factory,
    ws: uuid.UUID,
    *,
    unit: str,
    normalizations: list[str],
    rows: list[tuple[float, str | None]],
    qualifiers: list[str | None] | None = None,
) -> ActivitySummaryV2:
    """One compound, one completed run, readout "Signal" with ``rows`` (value, layer)
    and their ``qualifiers``."""
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "m1")
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(s, p, name="Signal", unit=unit, normalizations=normalizations)
        run = await seed.run(s, ws, p, date(2026, 11, 12), status="completed")
        for (value, layer), q in zip(rows, qualifiers or [None] * len(rows), strict=True):
            await seed.readout(s, ws, run, rd, mol, value, normalization=layer, qualifier=q)
        await uow.commit()
    result = await GetProtocolActivitySummary(SQLAlchemyProtocolActivityReader(session_factory))(
        GetProtocolActivityQuery(workspace_id=ws, protocol_id=p),
        auth=FakeAuth(role="viewer", workspace_id=ws),
    )
    assert isinstance(result, Success)
    return result.unwrap()


async def test_primary_layer_is_read_alone_when_it_has_data(uow, session_factory, workspace_id):
    out = await _summary(
        uow,
        session_factory,
        workspace_id,
        unit="RFU",
        normalizations=["percent_inhibition"],
        rows=[
            (1000.0, None),
            (3000.0, None),
            (40.0, "percent_inhibition"),
            (60.0, "percent_inhibition"),
        ],
    )

    signal = out.items[0].readouts["Signal"]
    assert (signal.mean, signal.n, signal.best) == (50.0, 2, 60.0)
    assert out.readout_definitions[0].unit == "%"


async def test_raw_layer_when_the_primary_has_no_data(uow, session_factory, workspace_id):
    out = await _summary(
        uow,
        session_factory,
        workspace_id,
        unit="RFU",
        normalizations=["percent_control"],
        rows=[(10.0, None), (20.0, None)],
    )

    assert out.items[0].readouts["Signal"].mean == 15.0
    assert out.readout_definitions[0].unit == "RFU"


async def test_readout_without_normalizations_reads_raw(uow, session_factory, workspace_id):
    out = await _summary(
        uow,
        session_factory,
        workspace_id,
        unit="RFU",
        normalizations=[],
        rows=[(1.0, None), (3.0, None)],
    )

    assert out.items[0].readouts["Signal"].mean == 2.0


def test_primary_normalization_skips_none():
    assert primary_normalization(["none", "z_score"]) == "z_score"
    assert primary_normalization([]) is None
    assert primary_normalization(None) is None


# --- Regression guard: Activity keeps today's treatment of qualified values --------------
# Written against the reader before the shared aggregation (Task 2) and run there first.


async def test_activity_still_averages_qualified_values(uow, session_factory, workspace_id):
    out = await _summary(
        uow,
        session_factory,
        workspace_id,
        unit="uM",
        normalizations=[],
        rows=[(10.0, None), (20.0, None), (50.0, None)],
        qualifiers=[None, None, ">"],
    )

    signal = out.items[0].readouts["Signal"]
    assert (signal.mean, signal.n, signal.best) == (26.6667, 3, 50.0)


async def test_activity_omits_an_all_inactive_dose_response_readout(
    uow, session_factory, workspace_id
):
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, workspace_id, await seed.org(s, workspace_id), "m1")
        p = await seed.protocol(s, workspace_id)
        rd = await seed.readout_def(s, p, name="IC50", data_type="dose_response", unit="uM")
        run = await seed.run(s, workspace_id, p, date(2026, 11, 12), status="completed")
        await seed.curve(
            s, workspace_id, p, run, mol, rd, fitted_value=5.0, curve_class="inactive"
        )
        await uow.commit()
    result = await GetProtocolActivitySummary(SQLAlchemyProtocolActivityReader(session_factory))(
        GetProtocolActivityQuery(workspace_id=workspace_id, protocol_id=p),
        auth=FakeAuth(role="viewer", workspace_id=workspace_id),
    )

    items = result.unwrap().items
    assert len(items) == 1
    assert "IC50" not in items[0].readouts


# --- Shared aggregation (get_aggregates) -----------------------------------------------


async def _numeric_world(
    uow, ws: uuid.UUID, values: list[tuple[float, str | None]]
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """One compound, one completed run of readout "Signal" (uM) with (value, qualifier) rows.
    Returns (protocol, molecule, run)."""
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "m1")
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(s, p, name="Signal", unit="uM")
        run = await seed.run(s, ws, p, date(2026, 11, 12), status="completed")
        for value, q in values:
            await seed.readout(s, ws, run, rd, mol, value, qualifier=q)
        await uow.commit()
    return p, mol, run


async def _aggregates(session_factory, ws: uuid.UUID, p: uuid.UUID, **scope) -> ActivityAggregates:
    reader = SQLAlchemyProtocolActivityReader(session_factory)
    return await reader.get_aggregates(ws, p, AggregateScope(**scope))


async def test_censored_values_are_counted_not_averaged(uow, session_factory, workspace_id):
    p, mol, _ = await _numeric_world(
        uow, workspace_id, [(10.0, None), (20.0, "="), (50.0, ">"), (1.0, "<")]
    )

    agg = await _aggregates(session_factory, workspace_id, p, statuses=VALID_STATUSES)

    [row] = agg.numeric_rows
    assert row.molecule_id == mol
    assert row.readout_definition_id is not None
    assert (row.mean, row.n, row.best, row.low) == (15.0, 2, 20.0, 10.0)
    assert (row.gt_count, row.gt_bound, row.lt_count, row.lt_bound) == (1, 50.0, 1, 1.0)
    # The workbench's value rule reads these through ReplicateStats.
    assert combine_replicates(row.stats(), "mean", unit="uM") == (15.0, ValueQualifier.EQ)


async def test_activity_scope_keeps_qualified_values_in_the_mean(
    uow, session_factory, workspace_id
):
    p, _, _ = await _numeric_world(uow, workspace_id, [(10.0, None), (20.0, None), (50.0, ">")])

    activity = await _aggregates(
        session_factory, workspace_id, p, statuses=VALID_STATUSES, exclude_censored=False
    )
    workbench = await _aggregates(session_factory, workspace_id, p, statuses=VALID_STATUSES)

    assert (round(activity.numeric_rows[0].mean, 4), activity.numeric_rows[0].n) == (26.6667, 3)
    [row] = workbench.numeric_rows
    assert (row.mean, row.n, row.gt_count) == (15.0, 2, 1)


async def test_missing_empty_and_null_conditions_are_one_condition_set(
    uow, session_factory, workspace_id
):
    ws = workspace_id
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "m1")
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(s, p, name="Signal")
        conditions = [{"NADP": "+"}, {"NADP": "-"}, None, None, {}, {"NADP": None}]
        runs = []
        for i, c in enumerate(conditions):
            run = await seed.run(s, ws, p, date(2026, 11, i + 1), status="completed", conditions=c)
            await seed.readout(s, ws, run, rd, mol, float(i))
            runs.append(run)
        await s.execute(
            sa.text("UPDATE runs SET conditions = 'null'::jsonb WHERE id = :id"), {"id": runs[3]}
        )
        await uow.commit()

    agg = await _aggregates(session_factory, ws, p, statuses=VALID_STATUSES, by_conditions=True)

    by_set = {json.dumps(r.conditions, sort_keys=True): r.n for r in agg.numeric_rows}
    assert by_set == {'{"NADP": "+"}': 1, '{"NADP": "-"}': 1, "{}": 4}


async def test_dose_response_counts_tested_inactive_and_used(uow, session_factory, workspace_id):
    ws = workspace_id
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "m1")
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(s, p, name="IC50", data_type="dose_response", unit="uM")
        run = await seed.run(s, ws, p, date(2026, 11, 12), status="completed")
        await seed.curve(s, ws, p, run, mol, rd, fitted_value=0.1)
        await seed.curve(s, ws, p, run, mol, rd, fitted_value=1.0)
        await seed.curve(s, ws, p, run, mol, rd, fitted_value=5.0, curve_class="inactive")
        await uow.commit()

    agg = await _aggregates(session_factory, ws, p, statuses=VALID_STATUSES)

    [row] = agg.dr_agg_rows
    assert (row.molecule_id, row.readout_definition_id) == (mol, rd)
    assert (row.n_tested, row.n_inactive, row.n_used) == (3, 1, 2)
    assert row.best == 0.1
    assert row.geo_mean == pytest.approx(0.316228, abs=1e-6)


async def test_scope_filters_runs_statuses_and_workspace(uow, session_factory, workspace_id):
    ws = workspace_id
    other_ws = uuid.uuid4()
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "m1")
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(s, p, name="Signal")
        done = await seed.run(s, ws, p, date(2026, 11, 1), status="completed")
        draft = await seed.run(s, ws, p, date(2026, 11, 2), status="draft")
        await seed.readout(s, ws, done, rd, mol, 10.0)
        await seed.readout(s, ws, draft, rd, mol, 30.0)
        # A row stamped with another workspace never counts, even in this run.
        await seed.readout(s, other_ws, done, rd, mol, 999.0)
        await uow.commit()

    def means(agg: ActivityAggregates) -> list[float]:
        return [r.mean for r in agg.numeric_rows]

    assert means(await _aggregates(session_factory, ws, p, statuses=VALID_STATUSES)) == [10.0]
    assert means(await _aggregates(session_factory, ws, p, statuses=None)) == [20.0]
    assert means(await _aggregates(session_factory, ws, p, statuses=None, run_ids=(draft,))) == [
        30.0
    ]
    nothing = await _aggregates(session_factory, other_ws, p, statuses=None)
    assert nothing == ActivityAggregates(numeric_rows=[], dr_agg_rows=[])


async def test_run_grain_gives_a_row_per_run_with_the_wells_batch(
    uow, session_factory, workspace_id
):
    ws = workspace_id
    well_batch, row_batch = uuid.uuid4(), uuid.uuid4()
    async with uow:
        s = uow.session
        mol = await seed.molecule(s, ws, await seed.org(s, ws), "m1")
        p = await seed.protocol(s, ws)
        rd = await seed.readout_def(s, p, name="Signal")
        ic50 = await seed.readout_def(s, p, name="IC50", data_type="dose_response", unit="uM")
        r1 = await seed.run(s, ws, p, date(2026, 11, 1), status="completed")
        r2 = await seed.run(s, ws, p, date(2026, 11, 2), status="completed")
        w1 = await seed.well(s, await seed.plate(s, r1, 1), "A", 1, batch_id=well_batch)
        await seed.readout(s, ws, r1, rd, mol, 10.0, well_id=w1)  # batch only on the well
        await seed.readout(s, ws, r2, rd, mol, 30.0, batch_id=row_batch)
        await seed.curve(s, ws, p, r1, mol, ic50, with_well=False)
        await uow.commit()

    agg = await _aggregates(session_factory, ws, p, statuses=VALID_STATUSES, grain="run")

    rows = {(r.run_id, r.batch_id): r.mean for r in agg.numeric_rows}
    assert rows == {(r1, well_batch): 10.0, (r2, row_batch): 30.0}
    [dr] = agg.dr_agg_rows
    assert dr.run_id == r1 and dr.batch_id is not None
