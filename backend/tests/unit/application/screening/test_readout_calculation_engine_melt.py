"""ReadoutCalculationEngine: Tm and ΔTm rows per temperature window."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from returns.result import Success

from cellar.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from cellar.domain.screening_assay.enums import (
    PlateFormat,
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
    WellType,
)
from cellar.domain.screening_assay.melt_window import (
    PER_POSITION_MEASURES,
    MeltMeasure,
    MeltReadoutConfig,
)
from cellar.domain.screening_assay.melting_step import (
    MeltingStep,
    MeltingStepSource,
    MeltingStepStatus,
)
from cellar.domain.screening_assay.plate_normalizer import PlateNormalizer
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.replicate_aggregator import ReplicateAggregator
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.domain.shared.enums import Qualifier
from cellar.domain.shared.value_objects import QualifiedValue
from cellar.infrastructure.computation.asteval_evaluator import AstevalFormulaEvaluator

WS = uuid.uuid4()
USER = uuid.uuid4()
_PH = uuid.UUID(int=0)
CH = "350nm"
WINDOWS = {"Low": (25.0, 50.0), "Main": (50.0, 85.0)}


def _melt_rd(window: str, measure: MeltMeasure) -> ReadoutDefinition:
    low, high = WINDOWS[window]
    prefix = "Tm" if measure is MeltMeasure.TM else "ΔTm"
    return ReadoutDefinition(
        protocol_id=_PH,
        name=f"{prefix} ({window})",
        data_type=ReadoutDataType.NUMERIC,
        unit="°C",
        aggregation=ReadoutAggregation.MEAN,
        melt_config=MeltReadoutConfig(
            window=window, measure=measure, channel_key=CH, low=low, high=high
        ),
    )


def _window_defs() -> list[ReadoutDefinition]:
    return [_melt_rd(w, m) for w in WINDOWS for m in MeltMeasure if m in PER_POSITION_MEASURES]


def _protocol(defs: list[ReadoutDefinition]) -> Protocol:
    return Protocol.create(
        workspace_id=WS,
        name="Thermal shift",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=USER,
        readout_definitions=defs,
    )


def _run(protocol: Protocol) -> tuple[Run, Well, Well]:
    run = Run.create(
        workspace_id=WS, protocol_id=protocol.id, run_date=date(2026, 11, 13), operator=USER
    )
    plate = Plate(run_id=run.id, plate_number=1, format=PlateFormat.F96)
    run.plates.append(plate)
    ref = Well(plate_id=plate.id, row="A", column=1, well_type=WellType.REFERENCE)
    sample = Well(
        plate_id=plate.id, row="A", column=2, well_type=WellType.SAMPLE, batch_id=uuid.uuid4()
    )
    run.wells.extend([ref, sample])
    return run, ref, sample


def _step(
    run: Run, well: Well, value: float, status: MeltingStepStatus = MeltingStepStatus.UNREVIEWED
) -> MeltingStep:
    return MeltingStep(
        workspace_id=WS,
        run_id=run.id,
        well_id=well.id,
        channel_key=CH,
        source=MeltingStepSource.MANUAL,
        value=value,
        status=status,
    )


def _engine(
    protocol: Protocol,
    run: Run,
    steps: list[MeltingStep],
    *,
    raw: list[ReadoutData] | None = None,
    molecule_by_batch: dict[uuid.UUID, uuid.UUID] | None = None,
    traced: set[tuple[uuid.UUID, str]] | None = None,
) -> tuple[ReadoutCalculationEngine, AsyncMock, AsyncMock, AsyncMock]:
    readout_data_repo = AsyncMock()
    readout_data_repo.find_by_run.return_value = raw or []
    run_repo = AsyncMock()
    run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
    protocol_repo = AsyncMock()
    protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
    step_repo = AsyncMock()
    step_repo.find_by_run.return_value = steps
    curve_repo = AsyncMock()
    curve_repo.list_traced.return_value = (
        {(w.id, CH) for w in run.wells} if traced is None else traced
    )
    batch_repo = AsyncMock()
    batch_repo.find_by_ids.return_value = [
        SimpleNamespace(id=b, molecule_id=m) for b, m in (molecule_by_batch or {}).items()
    ]
    uow = AsyncMock()
    uow.is_active = True
    engine = ReadoutCalculationEngine(
        uow=uow,
        formula_evaluator=AstevalFormulaEvaluator(),
        plate_normalizer=PlateNormalizer(),
        replicate_aggregator=ReplicateAggregator(),
        readout_data_repo=readout_data_repo,
        run_repo=run_repo,
        protocol_repo=protocol_repo,
        dispatcher=AsyncMock(),
        melting_step_repo=step_repo,
        measured_curve_repo=curve_repo,
        batch_repo=batch_repo,
    )
    return engine, readout_data_repo, step_repo, batch_repo


async def _rows(engine: ReadoutCalculationEngine, run: Run, protocol: Protocol):
    result = await engine.compute_for_run(run.id, workspace_id=WS)
    assert isinstance(result, Success)
    names = {rd.id: rd.name for rd in protocol.readout_definitions}
    return {
        (names[r.readout_definition_id], r.well_id): r.value.value
        for r in result.unwrap().computed_readouts
    }, result.unwrap().computed_readouts


@pytest.mark.asyncio
async def test_merged_step_writes_negative_delta_row_and_no_low_window_row() -> None:
    protocol = _protocol(_window_defs())
    run, ref, sample = _run(protocol)
    steps = [_step(run, ref, 36.6), _step(run, ref, 71.3), _step(run, sample, 64.0)]
    engine, *_ = _engine(protocol, run, steps)

    rows, _ = await _rows(engine, run, protocol)

    assert rows == {
        ("Tm (Low)", ref.id): 36.6,
        ("Tm (Main)", ref.id): 71.3,
        ("Tm (Main)", sample.id): 64.0,
        ("ΔTm (Main)", sample.id): pytest.approx(-7.3),
    }


@pytest.mark.asyncio
async def test_position_without_a_trace_on_the_channel_gets_no_window_rows() -> None:
    protocol = _protocol(_window_defs())
    run, ref, sample = _run(protocol)
    steps = [_step(run, ref, 71.3), _step(run, sample, 64.0)]
    engine, *_ = _engine(protocol, run, steps, traced={(ref.id, CH), (sample.id, "other")})

    rows, _ = await _rows(engine, run, protocol)

    assert rows == {("Tm (Main)", ref.id): 71.3}


@pytest.mark.asyncio
async def test_no_reference_writes_tm_rows_but_no_delta_rows() -> None:
    protocol = _protocol(_window_defs())
    run, ref, sample = _run(protocol)
    steps = [_step(run, ref, 71.3, MeltingStepStatus.REJECTED), _step(run, sample, 64.0)]
    engine, *_ = _engine(protocol, run, steps)

    rows, _ = await _rows(engine, run, protocol)

    assert rows == {("Tm (Main)", sample.id): 64.0}


@pytest.mark.asyncio
async def test_rejected_steps_do_not_count() -> None:
    protocol = _protocol(_window_defs())
    run, ref, sample = _run(protocol)
    steps = [
        _step(run, ref, 71.0, MeltingStepStatus.ACCEPTED),
        _step(run, sample, 60.0, MeltingStepStatus.REJECTED),
        _step(run, sample, 64.0),
    ]
    engine, *_ = _engine(protocol, run, steps)

    rows, _ = await _rows(engine, run, protocol)

    assert rows[("Tm (Main)", sample.id)] == 64.0
    assert rows[("ΔTm (Main)", sample.id)] == pytest.approx(-7.0)


@pytest.mark.asyncio
async def test_run_with_traces_but_no_mapped_readouts_still_gets_window_rows() -> None:
    protocol = _protocol(_window_defs())
    run, ref, sample = _run(protocol)
    steps = [_step(run, ref, 71.3), _step(run, sample, 64.0)]
    engine, readout_data_repo, *_ = _engine(protocol, run, steps, raw=[])

    rows, computed = await _rows(engine, run, protocol)

    assert ("ΔTm (Main)", sample.id) in rows
    readout_data_repo.save_bulk.assert_awaited_once_with(computed)


@pytest.mark.asyncio
async def test_window_rows_carry_well_batch_and_molecule() -> None:
    protocol = _protocol(_window_defs())
    run, ref, sample = _run(protocol)
    mol = uuid.uuid4()
    steps = [_step(run, ref, 71.3), _step(run, sample, 64.0)]
    engine, _, step_repo, batch_repo = _engine(
        protocol, run, steps, molecule_by_batch={sample.batch_id: mol}
    )

    _, computed = await _rows(engine, run, protocol)

    step_repo.find_by_run.assert_awaited_once_with(WS, run.id)
    batch_repo.find_by_ids.assert_awaited_once_with(WS, [sample.batch_id])
    sample_rows = [r for r in computed if r.well_id == sample.id]
    assert len(sample_rows) == 2
    for r in sample_rows:
        assert r.batch_id == sample.batch_id
        assert r.molecule_id == mol
        assert r.run_id == run.id
        assert r.workspace_id == WS
        assert r.is_computed is True
        assert r.normalization_applied is None
    ref_row = next(r for r in computed if r.well_id == ref.id)
    assert ref_row.batch_id is None and ref_row.molecule_id is None


@pytest.mark.asyncio
async def test_formula_can_use_a_window_readout() -> None:
    doubled = ReadoutDefinition(
        protocol_id=_PH,
        name="Doubled shift",
        data_type=ReadoutDataType.NUMERIC,
        is_calculated=True,
        calculation_formula="[ΔTm (Main)] * 2",
    )
    protocol = _protocol([*_window_defs(), doubled])
    run, ref, sample = _run(protocol)
    mol = uuid.uuid4()
    steps = [_step(run, ref, 71.3), _step(run, sample, 64.0)]
    engine, *_ = _engine(protocol, run, steps, molecule_by_batch={sample.batch_id: mol})

    _, computed = await _rows(engine, run, protocol)

    formula_rows = [r for r in computed if r.readout_definition_id == doubled.id]
    assert len(formula_rows) == 1
    assert formula_rows[0].molecule_id == mol
    assert formula_rows[0].batch_id == sample.batch_id
    assert formula_rows[0].value.value == pytest.approx(-14.6)


@pytest.mark.asyncio
async def test_protocol_without_windows_is_unchanged() -> None:
    raw_rd = ReadoutDefinition(protocol_id=_PH, name="Raw", data_type=ReadoutDataType.NUMERIC)
    calc_rd = ReadoutDefinition(
        protocol_id=_PH,
        name="Doubled",
        data_type=ReadoutDataType.NUMERIC,
        is_calculated=True,
        calculation_formula="Raw * 2",
    )
    protocol = _protocol([raw_rd, calc_rd])
    run, _, sample = _run(protocol)
    mol = uuid.uuid4()
    raw = ReadoutData(
        workspace_id=WS,
        run_id=run.id,
        well_id=sample.id,
        molecule_id=mol,
        batch_id=sample.batch_id,
        readout_definition_id=raw_rd.id,
        value=QualifiedValue(value=50.0),
    )
    engine, _, step_repo, batch_repo = _engine(
        protocol, run, [_step(run, sample, 64.0)], raw=[raw]
    )

    _, computed = await _rows(engine, run, protocol)

    assert [(r.readout_definition_id, r.value.value) for r in computed] == [(calc_rd.id, 100.0)]
    step_repo.find_by_run.assert_not_awaited()
    batch_repo.find_by_ids.assert_not_awaited()


# ---- Series values (one computed row per batch, no position) ----


def _series_rd(name: str, measure: MeltMeasure, unit: str = "°C", **param) -> ReadoutDefinition:
    low, high = WINDOWS["Main"]
    return ReadoutDefinition(
        protocol_id=_PH,
        name=name,
        data_type=ReadoutDataType.NUMERIC,
        unit=unit,
        aggregation=ReadoutAggregation.MEAN,
        melt_config=MeltReadoutConfig(
            window="Main", measure=measure, channel_key=CH, low=low, high=high, **param
        ),
    )


MAX_RD = "Max ΔTm (Main)"


def _series_run(protocol: Protocol, doses_by_batch: dict[uuid.UUID, list[float]]):
    run, ref, _ = _run(protocol)
    run.wells[:] = [ref]
    plate_id = ref.plate_id
    col = 2
    wells = []
    for batch, doses in doses_by_batch.items():
        for d in doses:
            w = Well(
                plate_id=plate_id,
                row="A",
                column=col,
                well_type=WellType.SAMPLE,
                batch_id=batch,
                dose=d,
            )
            col += 1
            run.wells.append(w)
            wells.append(w)
    return run, ref, wells


@pytest.mark.asyncio
async def test_series_rows_written_per_batch() -> None:
    rd = _series_rd(MAX_RD, MeltMeasure.MAX_DELTA_TM)
    protocol = _protocol([rd])
    batch, mol = uuid.uuid4(), uuid.uuid4()
    run, ref, (w1, w2, w3) = _series_run(protocol, {batch: [6.25, 25.0, 50.0]})
    steps = [
        _step(run, ref, 71.3),
        _step(run, w1, 70.0),
        _step(run, w2, 62.7),
        _step(run, w3, 63.3),
    ]
    engine, *_ = _engine(protocol, run, steps, molecule_by_batch={batch: mol})

    _, computed = await _rows(engine, run, protocol)

    [row] = computed
    assert row.readout_definition_id == rd.id and row.well_id is None
    assert row.batch_id == batch and row.molecule_id == mol and row.is_computed
    assert row.value.value == pytest.approx(-8.6) and row.value.qualifier is Qualifier.EQUAL


@pytest.mark.asyncio
async def test_series_rows_for_two_lots_are_separate() -> None:
    protocol = _protocol([_series_rd(MAX_RD, MeltMeasure.MAX_DELTA_TM)])
    lot1, lot2, mol = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    run, ref, (a, b) = _series_run(protocol, {lot1: [10.0], lot2: [10.0]})
    steps = [_step(run, ref, 71.3), _step(run, a, 70.0), _step(run, b, 64.3)]
    engine, *_ = _engine(protocol, run, steps, molecule_by_batch={lot1: mol, lot2: mol})

    _, computed = await _rows(engine, run, protocol)

    assert {(r.batch_id, round(r.value.value, 6)) for r in computed} == {
        (lot1, -1.3),
        (lot2, -7.0),
    }
    assert {r.molecule_id for r in computed} == {mol}
    assert all(r.well_id is None for r in computed)


@pytest.mark.asyncio
async def test_series_rows_not_fed_to_formulas() -> None:
    calc = ReadoutDefinition(
        protocol_id=_PH,
        name="Copy",
        data_type=ReadoutDataType.NUMERIC,
        is_calculated=True,
        calculation_formula=f"[{MAX_RD}] * 1",
    )
    protocol = _protocol([_series_rd(MAX_RD, MeltMeasure.MAX_DELTA_TM), calc])
    batch = uuid.uuid4()
    run, ref, (w,) = _series_run(protocol, {batch: [10.0]})
    steps = [_step(run, ref, 71.3), _step(run, w, 64.0)]
    engine, *_ = _engine(protocol, run, steps, molecule_by_batch={batch: uuid.uuid4()})

    _, computed = await _rows(engine, run, protocol)

    assert [r.readout_definition_id for r in computed if r.readout_definition_id == calc.id] == []


@pytest.mark.asyncio
async def test_censored_lowest_shift_row_has_gt_qualifier() -> None:
    rd = _series_rd(
        "Lowest shifting conc. (Main, ±2 °C)",
        MeltMeasure.LOWEST_SHIFT_CONCENTRATION,
        unit="uM",
        threshold=2.0,
    )
    protocol = _protocol([rd])
    batch = uuid.uuid4()
    run, ref, (a, b) = _series_run(protocol, {batch: [10.0, 50.0]})
    steps = [_step(run, ref, 71.3), _step(run, a, 71.0), _step(run, b, 70.0)]
    engine, *_ = _engine(protocol, run, steps, molecule_by_batch={batch: uuid.uuid4()})

    _, computed = await _rows(engine, run, protocol)

    [row] = computed
    assert row.value.value == 50.0 and row.value.qualifier is Qualifier.GREATER_THAN
