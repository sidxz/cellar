"""Integration tests: melting steps persist, update under a version check, and go with the run."""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from cellar.application.screening.delete_run import DeleteRun, DeleteRunCommand
from cellar.application.screening.reset_run_data import ResetRunData, ResetRunDataCommand
from cellar.domain.screening_assay.enums import (
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
)
from cellar.domain.screening_assay.measured_curve import ReportedPoint
from cellar.domain.screening_assay.melt_window import MeltMeasure, MeltReadoutConfig
from cellar.domain.screening_assay.melting_step import MeltingStep, MeltingStepStatus
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.errors import ConflictError
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.measured_curve_repository import (  # noqa: E501
    SQLAlchemyMeasuredCurveRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.melting_step_repository import (
    SQLAlchemyMeltingStepRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.fakes.fake_auth import FakeAuth
from tests.integration.persistence.screening.test_measured_curve_lifecycle import (
    _repos,
    _run_with_curves,
)

_M097 = Path(__file__).parents[4] / "alembic" / "versions" / "097_melting_steps.py"
RANGE = (20.0, 22.0)


def _point(value: float, label: str = "Tm 1") -> ReportedPoint:
    return ReportedPoint(kind="transition", ordinal=1, label=label, value=value, unit="°C")


async def _seed_steps(session_factory, workspace_id):  # type: ignore[no-untyped-def]
    run_id, well_ids = await _run_with_curves(session_factory, workspace_id)
    steps = [
        MeltingStep.from_reported(
            workspace_id=workspace_id,
            run_id=run_id,
            well_id=w,
            channel_key="ratio",
            point=_point(21.0 + i / 10),
        )
        for i, w in enumerate(well_ids)
    ]
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyMeltingStepRepository(uow).save_bulk(steps)
        await uow.commit()
    return run_id, steps


async def test_save_bulk_find_by_run_and_by_id_scoped_to_workspace(session_factory, workspace_id):
    run_id, steps = await _seed_steps(session_factory, workspace_id)
    other_ws = uuid.uuid4()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyMeltingStepRepository(uow)
        found = await repo.find_by_run(workspace_id, run_id)
        assert {s.id for s in found} == {s.id for s in steps}
        one = await repo.find_by_id(workspace_id, steps[1].id)
        assert one is not None
        assert one.value == pytest.approx(21.1) and one.instrument_value == pytest.approx(21.1)
        assert one.instrument_label == "Tm 1" and one.status is MeltingStepStatus.UNREVIEWED
        assert one.channel_key == "ratio" and one.version == 1
        assert await repo.find_by_run(other_ws, run_id) == []
        assert await repo.find_by_id(other_ws, steps[1].id) is None

        manual = MeltingStep.manual(
            workspace_id=workspace_id,
            run_id=run_id,
            well_id=steps[0].well_id,
            channel_key="ratio",
            value=20.5,
            x_range=RANGE,
            reason="second step",
            by=uuid.uuid4(),
        )
        await repo.add(manual)
        await uow.commit()

    async with uow:
        again = await SQLAlchemyMeltingStepRepository(uow).find_by_id(workspace_id, manual.id)
        assert again is not None and again.instrument_value is None
        assert again.reason == "second step" and again.changed_by == manual.changed_by


async def test_update_with_stale_version_raises_conflict_and_changes_nothing(
    session_factory, workspace_id
):
    _, steps = await _seed_steps(session_factory, workspace_id)
    step_id = steps[0].id
    alice, bob = uuid.uuid4(), uuid.uuid4()

    # Both open version 1.
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyMeltingStepRepository(uow)
        mine = await repo.find_by_id(workspace_id, step_id)
        theirs = await repo.find_by_id(workspace_id, step_id)
    assert mine is not None and theirs is not None

    # Alice saves first.
    loaded = mine.version
    mine.review(
        status=MeltingStepStatus.REJECTED,
        value=mine.value,
        reason="noisy",
        x_range=RANGE,
        by=alice,
    )
    async with uow:
        await SQLAlchemyMeltingStepRepository(uow).update(mine, expected_version=loaded)
        await uow.commit()

    # Bob's save is refused.
    loaded = theirs.version
    theirs.review(
        status=MeltingStepStatus.ACCEPTED, value=theirs.value, reason=None, x_range=RANGE, by=bob
    )
    async with uow:
        with pytest.raises(ConflictError, match="changed by someone else"):
            await SQLAlchemyMeltingStepRepository(uow).update(theirs, expected_version=loaded)

    async with uow:
        stored = await SQLAlchemyMeltingStepRepository(uow).find_by_id(workspace_id, step_id)
    assert stored is not None
    assert stored.status is MeltingStepStatus.REJECTED and stored.reason == "noisy"
    assert stored.version == 2 and stored.changed_by == alice and stored.changed_at is not None


async def test_update_is_scoped_to_workspace(session_factory, workspace_id):
    _, steps = await _seed_steps(session_factory, workspace_id)
    step = steps[0]
    step.workspace_id = uuid.uuid4()
    step.review(
        status=MeltingStepStatus.ACCEPTED,
        value=step.value,
        reason=None,
        x_range=RANGE,
        by=uuid.uuid4(),
    )
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        with pytest.raises(ConflictError):
            await SQLAlchemyMeltingStepRepository(uow).update(step, expected_version=1)


async def test_delete_by_run_and_cascade_on_run_delete(session_factory, workspace_id):
    run_id, _ = await _seed_steps(session_factory, workspace_id)

    uow = AsyncUnitOfWork(session_factory)
    uc = ResetRunData(
        **_repos(uow),
        measured_curve_repo=SQLAlchemyMeasuredCurveRepository(uow),
        melting_step_repo=SQLAlchemyMeltingStepRepository(uow),
    )
    result = await uc(
        ResetRunDataCommand(workspace_id=workspace_id, run_id=run_id),
        auth=FakeAuth(workspace_id=workspace_id),
    )
    assert result.unwrap().melting_steps_deleted == 3
    async with uow:
        assert await SQLAlchemyMeltingStepRepository(uow).find_by_run(workspace_id, run_id) == []

    run_id, _ = await _seed_steps(session_factory, workspace_id)
    deleted = await DeleteRun(**_repos(AsyncUnitOfWork(session_factory)))(
        DeleteRunCommand(workspace_id=workspace_id, run_id=run_id),
        auth=FakeAuth(workspace_id=workspace_id),
    )
    assert deleted.unwrap() is None
    async with session_factory() as session:
        count = await session.execute(
            sa.text("SELECT count(*) FROM melting_steps WHERE run_id = :r"), {"r": run_id}
        )
        assert count.scalar() == 0


async def test_protocol_repository_round_trips_melt_config(session_factory, workspace_id, user_id):
    pid = uuid.uuid4()
    config = MeltReadoutConfig(
        window="Main", measure=MeltMeasure.DELTA_TM, channel_key="ratio", low=50.0, high=85.0
    )
    readouts = [
        ReadoutDefinition(protocol_id=pid, name="Signal", data_type=ReadoutDataType.NUMERIC),
        ReadoutDefinition(
            protocol_id=pid,
            name="ΔTm (Main)",
            data_type=ReadoutDataType.NUMERIC,
            unit="°C",
            aggregation=ReadoutAggregation.MEAN,
            melt_config=config,
        ),
    ]
    p = Protocol.create(
        workspace_id=workspace_id,
        name="Thermal shift round trip",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=user_id,
        code="PRT-09701",
        readout_definitions=readouts,
    )
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyProtocolRepository(uow).save(p)
        await uow.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        loaded = await SQLAlchemyProtocolRepository(uow).find_by_id_in_workspace(
            workspace_id, p.id
        )
    assert loaded is not None
    by_name = {r.name: r for r in loaded.readout_definitions}
    assert by_name["ΔTm (Main)"].melt_config == config
    assert by_name["Signal"].melt_config is None


def _load_m097():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m097", _M097)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_migration_097_seeds_transition_steps_from_traces(session_factory, workspace_id):
    run_id, well_ids = await _run_with_curves(session_factory, workspace_id)
    reported = [
        {"kind": "transition", "ordinal": 1, "label": "Tm 1", "value": 36.6, "unit": "°C"},
        {"kind": "onset", "ordinal": 1, "label": "Onset 1", "value": 33.0, "unit": "°C"},
        {"kind": "transition", "ordinal": 2, "label": "Tm 2", "value": 71.3, "unit": "°C"},
    ]
    m097 = _load_m097()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        session = uow.session
        await session.execute(
            sa.text(
                "UPDATE measured_curves SET reported = CAST(:r AS jsonb) "
                "WHERE well_id = :w AND channel_key = 'ratio'"
            ),
            {"r": json.dumps(reported), "w": well_ids[0]},
        )

        def downgrade_then_upgrade(sync_session) -> None:  # type: ignore[no-untyped-def]
            # The test database is at head: step back to 096, then apply 097 for real.
            with Operations.context(MigrationContext.configure(sync_session.connection())):
                m097.downgrade()
                m097.upgrade()

        await session.run_sync(downgrade_then_upgrade)
        rows = (
            await session.execute(
                sa.text(
                    "SELECT well_id, channel_key, source, value, instrument_value, "
                    "instrument_label, status, version FROM melting_steps "
                    "WHERE run_id = :r ORDER BY value"
                ),
                {"r": run_id},
            )
        ).all()
        await session.rollback()  # leave the shared test database as it was

    assert [tuple(r) for r in rows] == [
        (well_ids[0], "ratio", "instrument", 36.6, 36.6, "Tm 1", "unreviewed", 1),
        (well_ids[0], "ratio", "instrument", 71.3, 71.3, "Tm 2", "unreviewed", 1),
    ]
