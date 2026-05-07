"""Tests for ReadoutCalculationEngine pipeline orchestrator."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest

from chem_vault.application.screening.readout_calculation_engine import (
    ReadoutCalculationEngine,
)
from chem_vault.domain.screening_assay.enums import (
    PlateFormat,
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
    WellType,
)
from chem_vault.domain.screening_assay.plate_normalizer import PlateNormalizer
from chem_vault.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from chem_vault.domain.screening_assay.readout_data import ReadoutData
from chem_vault.domain.screening_assay.replicate_aggregator import ReplicateAggregator
from chem_vault.domain.screening_assay.run import Plate, Run, Well
from chem_vault.domain.shared.enums import Qualifier
from chem_vault.domain.shared.value_objects import QualifiedValue
from chem_vault.infrastructure.computation.asteval_evaluator import (
    AstevalFormulaEvaluator,
)
from returns.result import Failure, Success

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

WS = uuid.uuid4()
USER = uuid.uuid4()
_PH = uuid.UUID(int=0)  # placeholder UUID


def _make_protocol(readout_defs: list[ReadoutDefinition]) -> Protocol:
    """Build a minimal Protocol with the given readout definitions."""
    return Protocol.create(
        workspace_id=WS,
        name="Test Protocol",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=USER,
        readout_definitions=readout_defs,
    )


def _make_run(protocol_id: uuid.UUID) -> Run:
    """Build a minimal Run with one plate and one sample well."""
    run = Run.create(
        workspace_id=WS,
        protocol_id=protocol_id,
        run_date=date(2026, 4, 6),
        operator=USER,
    )
    plate = Plate(
        run_id=run.id,
        plate_number=1,
        format=PlateFormat.F96,
    )
    run.plates.append(plate)
    well = Well(
        plate_id=plate.id,
        row="A",
        column=1,
        well_type=WellType.SAMPLE,
        batch_id=uuid.uuid4(),
    )
    run.wells.append(well)
    return run


def _make_repos():
    """Create AsyncMock repos for the engine."""
    return (
        AsyncMock(),  # readout_data_repo
        AsyncMock(),  # run_repo
        AsyncMock(),  # protocol_repo
    )


def _fake_uow(is_active: bool = True):
    """Fake UoW that passes through async context manager.

    By default ``is_active`` is True so the engine takes the no-context
    fast path. Pass ``False`` to exercise the "open my own UoW + commit"
    path that runs in production.
    """
    uow = AsyncMock()
    uow.is_active = is_active
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    uow.commit = AsyncMock(return_value=[])
    return uow


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputedReadoutsPersisted:
    """Protocol with "Raw" readout + "Doubled" calculated readout (formula: Raw * 2).
    Import raw data value=50. Verify engine calls save_bulk with 1 computed
    ReadoutData where value=100.0 and is_computed=True.
    """

    @pytest.mark.asyncio
    async def test_computed_readouts_persisted(self) -> None:
        # -- Arrange --
        raw_rd = ReadoutDefinition(
            protocol_id=_PH,
            name="Raw",
            data_type=ReadoutDataType.NUMERIC,
        )
        calc_rd = ReadoutDefinition(
            protocol_id=_PH,
            name="Doubled",
            data_type=ReadoutDataType.NUMERIC,
            is_calculated=True,
            calculation_formula="Raw * 2",
        )

        protocol = _make_protocol([raw_rd, calc_rd])
        run = _make_run(protocol.id)
        well = run.wells[0]
        mol_id = uuid.uuid4()

        raw_readout = ReadoutData(
            workspace_id=WS,
            run_id=run.id,
            well_id=well.id,
            molecule_id=mol_id,
            batch_id=well.batch_id,
            readout_definition_id=raw_rd.id,
            value=QualifiedValue(value=50.0),
        )

        readout_data_repo, run_repo, protocol_repo = _make_repos()
        run_repo.find_by_id.return_value = run
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
        protocol_repo.find_by_id.return_value = protocol
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
        readout_data_repo.find_by_run.return_value = [raw_readout]
        readout_data_repo.delete_computed_for_run.return_value = 0

        engine = ReadoutCalculationEngine(
            uow=_fake_uow(),
            formula_evaluator=AstevalFormulaEvaluator(),
            plate_normalizer=PlateNormalizer(),
            replicate_aggregator=ReplicateAggregator(),
            readout_data_repo=readout_data_repo,
            run_repo=run_repo,
            protocol_repo=protocol_repo,
        )

        # -- Act --
        result = await engine.compute_for_run(run.id, workspace_id=WS)

        # -- Assert --
        assert isinstance(result, Success)
        computed = result.unwrap().computed_readouts

        assert len(computed) == 1
        assert computed[0].is_computed is True
        assert computed[0].value is not None
        assert computed[0].value.value == 100.0
        assert computed[0].readout_definition_id == calc_rd.id
        assert computed[0].molecule_id == mol_id

        readout_data_repo.save_bulk.assert_awaited_once()
        saved = readout_data_repo.save_bulk.call_args[0][0]
        assert len(saved) == 1
        assert saved[0].value.value == 100.0


class TestCommitsWhenOpeningOwnUoW:
    """When the engine opens its own UoW (caller doesn't), it MUST commit
    or the computed readouts and qc_metrics are silently rolled back on
    context exit. Real production bug — calc engine was never persisting
    anything despite returning Success.
    """

    @pytest.mark.asyncio
    async def test_commits_own_uow_after_successful_compute(self) -> None:
        raw_rd = ReadoutDefinition(
            protocol_id=_PH,
            name="Raw",
            data_type=ReadoutDataType.NUMERIC,
        )
        calc_rd = ReadoutDefinition(
            protocol_id=_PH,
            name="Doubled",
            data_type=ReadoutDataType.NUMERIC,
            is_calculated=True,
            calculation_formula="Raw * 2",
        )
        protocol = _make_protocol([raw_rd, calc_rd])
        run = _make_run(protocol.id)
        raw_readout = ReadoutData(
            workspace_id=WS,
            run_id=run.id,
            well_id=run.wells[0].id,
            molecule_id=uuid.uuid4(),
            batch_id=run.wells[0].batch_id,
            readout_definition_id=raw_rd.id,
            value=QualifiedValue(value=50.0),
        )
        readout_data_repo, run_repo, protocol_repo = _make_repos()
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
        readout_data_repo.find_by_run.return_value = [raw_readout]
        readout_data_repo.delete_computed_for_run.return_value = 0

        # is_active=False -> engine opens its own context -> must commit.
        uow = _fake_uow(is_active=False)
        engine = ReadoutCalculationEngine(
            uow=uow,
            formula_evaluator=AstevalFormulaEvaluator(),
            plate_normalizer=PlateNormalizer(),
            replicate_aggregator=ReplicateAggregator(),
            readout_data_repo=readout_data_repo,
            run_repo=run_repo,
            protocol_repo=protocol_repo,
        )

        result = await engine.compute_for_run(run.id, workspace_id=WS)
        assert isinstance(result, Success)
        # The fix: commit() MUST be awaited or the session changes are lost.
        uow.commit.assert_awaited_once()


class TestNoCalculatedReadoutsIsNoop:
    """Protocol with only raw readout. Verify save_bulk NOT called."""

    @pytest.mark.asyncio
    async def test_no_calculated_readouts_is_noop(self) -> None:
        # -- Arrange --
        raw_rd = ReadoutDefinition(
            protocol_id=_PH,
            name="Raw",
            data_type=ReadoutDataType.NUMERIC,
        )

        protocol = _make_protocol([raw_rd])
        run = _make_run(protocol.id)
        well = run.wells[0]

        raw_readout = ReadoutData(
            workspace_id=WS,
            run_id=run.id,
            well_id=well.id,
            molecule_id=uuid.uuid4(),
            batch_id=well.batch_id,
            readout_definition_id=raw_rd.id,
            value=QualifiedValue(value=42.0),
        )

        readout_data_repo, run_repo, protocol_repo = _make_repos()
        run_repo.find_by_id.return_value = run
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
        protocol_repo.find_by_id.return_value = protocol
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
        readout_data_repo.find_by_run.return_value = [raw_readout]
        readout_data_repo.delete_computed_for_run.return_value = 0

        engine = ReadoutCalculationEngine(
            uow=_fake_uow(),
            formula_evaluator=AstevalFormulaEvaluator(),
            plate_normalizer=PlateNormalizer(),
            replicate_aggregator=ReplicateAggregator(),
            readout_data_repo=readout_data_repo,
            run_repo=run_repo,
            protocol_repo=protocol_repo,
        )

        # -- Act --
        result = await engine.compute_for_run(run.id, workspace_id=WS)

        # -- Assert --
        assert isinstance(result, Success)
        assert result.unwrap().computed_readouts == []
        readout_data_repo.save_bulk.assert_not_awaited()


class TestIdempotentDeletesPreviousComputed:
    """Verify delete_computed_for_run is called before computation."""

    @pytest.mark.asyncio
    async def test_idempotent_deletes_previous_computed(self) -> None:
        # -- Arrange --
        raw_rd = ReadoutDefinition(
            protocol_id=_PH,
            name="Raw",
            data_type=ReadoutDataType.NUMERIC,
        )
        calc_rd = ReadoutDefinition(
            protocol_id=_PH,
            name="Tripled",
            data_type=ReadoutDataType.NUMERIC,
            is_calculated=True,
            calculation_formula="Raw * 3",
        )

        protocol = _make_protocol([raw_rd, calc_rd])
        run = _make_run(protocol.id)
        well = run.wells[0]
        mol_id = uuid.uuid4()

        raw_readout = ReadoutData(
            workspace_id=WS,
            run_id=run.id,
            well_id=well.id,
            molecule_id=mol_id,
            batch_id=well.batch_id,
            readout_definition_id=raw_rd.id,
            value=QualifiedValue(value=10.0),
        )

        readout_data_repo, run_repo, protocol_repo = _make_repos()
        run_repo.find_by_id.return_value = run
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
        protocol_repo.find_by_id.return_value = protocol
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
        readout_data_repo.find_by_run.return_value = [raw_readout]
        readout_data_repo.delete_computed_for_run.return_value = 5  # simulate 5 old rows deleted

        engine = ReadoutCalculationEngine(
            uow=_fake_uow(),
            formula_evaluator=AstevalFormulaEvaluator(),
            plate_normalizer=PlateNormalizer(),
            replicate_aggregator=ReplicateAggregator(),
            readout_data_repo=readout_data_repo,
            run_repo=run_repo,
            protocol_repo=protocol_repo,
        )

        # -- Act --
        result = await engine.compute_for_run(run.id, workspace_id=WS)

        # -- Assert --
        assert isinstance(result, Success)
        readout_data_repo.delete_computed_for_run.assert_awaited_once_with(WS, run.id)

        # Verify new computed data is correct
        computed = result.unwrap().computed_readouts
        assert len(computed) == 1
        assert computed[0].value.value == 30.0  # 10.0 * 3


class TestRunNotFound:
    """Verify Failure(NotFoundError) when run does not exist."""

    @pytest.mark.asyncio
    async def test_run_not_found(self) -> None:
        readout_data_repo, run_repo, protocol_repo = _make_repos()
        run_repo.find_by_id.return_value = None
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=None)

        engine = ReadoutCalculationEngine(
            uow=_fake_uow(),
            formula_evaluator=AstevalFormulaEvaluator(),
            plate_normalizer=PlateNormalizer(),
            replicate_aggregator=ReplicateAggregator(),
            readout_data_repo=readout_data_repo,
            run_repo=run_repo,
            protocol_repo=protocol_repo,
        )

        result = await engine.compute_for_run(uuid.uuid4(), workspace_id=WS)

        assert isinstance(result, Failure)
        err = result.failure()
        assert "Run" in err.message
        assert "not found" in err.message


class TestProtocolNotFound:
    """Verify Failure(NotFoundError) when protocol does not exist."""

    @pytest.mark.asyncio
    async def test_protocol_not_found(self) -> None:
        raw_rd = ReadoutDefinition(
            protocol_id=_PH,
            name="Raw",
            data_type=ReadoutDataType.NUMERIC,
        )
        protocol = _make_protocol([raw_rd])
        run = _make_run(protocol.id)

        readout_data_repo, run_repo, protocol_repo = _make_repos()
        run_repo.find_by_id.return_value = run
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
        protocol_repo.find_by_id.return_value = None
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=None)

        engine = ReadoutCalculationEngine(
            uow=_fake_uow(),
            formula_evaluator=AstevalFormulaEvaluator(),
            plate_normalizer=PlateNormalizer(),
            replicate_aggregator=ReplicateAggregator(),
            readout_data_repo=readout_data_repo,
            run_repo=run_repo,
            protocol_repo=protocol_repo,
        )

        result = await engine.compute_for_run(run.id, workspace_id=WS)

        assert isinstance(result, Failure)
        err = result.failure()
        assert "Protocol" in err.message
        assert "not found" in err.message


class TestEmptyRawDataReturnsSuccess:
    """No raw data in run -> Success([]) without calling save_bulk."""

    @pytest.mark.asyncio
    async def test_empty_raw_data_returns_empty(self) -> None:
        raw_rd = ReadoutDefinition(
            protocol_id=_PH,
            name="Raw",
            data_type=ReadoutDataType.NUMERIC,
        )
        protocol = _make_protocol([raw_rd])
        run = _make_run(protocol.id)

        readout_data_repo, run_repo, protocol_repo = _make_repos()
        run_repo.find_by_id.return_value = run
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
        protocol_repo.find_by_id.return_value = protocol
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
        readout_data_repo.find_by_run.return_value = []
        readout_data_repo.delete_computed_for_run.return_value = 0

        engine = ReadoutCalculationEngine(
            uow=_fake_uow(),
            formula_evaluator=AstevalFormulaEvaluator(),
            plate_normalizer=PlateNormalizer(),
            replicate_aggregator=ReplicateAggregator(),
            readout_data_repo=readout_data_repo,
            run_repo=run_repo,
            protocol_repo=protocol_repo,
        )

        result = await engine.compute_for_run(run.id, workspace_id=WS)

        assert isinstance(result, Success)
        assert result.unwrap().computed_readouts == []
        readout_data_repo.save_bulk.assert_not_awaited()


class TestCrossProtocolFormulasSkipped:
    """Formulas with @ references are skipped (resolved by CrossProtocolResolver)."""

    @pytest.mark.asyncio
    async def test_cross_protocol_formulas_skipped(self) -> None:
        raw_rd = ReadoutDefinition(
            protocol_id=_PH,
            name="Raw",
            data_type=ReadoutDataType.NUMERIC,
        )
        cross_rd = ReadoutDefinition(
            protocol_id=_PH,
            name="CrossCalc",
            data_type=ReadoutDataType.NUMERIC,
            is_calculated=True,
            calculation_formula="@{Other Protocol}.IC50 * Raw",
        )

        protocol = _make_protocol([raw_rd, cross_rd])
        run = _make_run(protocol.id)
        well = run.wells[0]

        raw_readout = ReadoutData(
            workspace_id=WS,
            run_id=run.id,
            well_id=well.id,
            molecule_id=uuid.uuid4(),
            batch_id=well.batch_id,
            readout_definition_id=raw_rd.id,
            value=QualifiedValue(value=50.0),
        )

        readout_data_repo, run_repo, protocol_repo = _make_repos()
        run_repo.find_by_id.return_value = run
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
        protocol_repo.find_by_id.return_value = protocol
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
        readout_data_repo.find_by_run.return_value = [raw_readout]
        readout_data_repo.delete_computed_for_run.return_value = 0

        engine = ReadoutCalculationEngine(
            uow=_fake_uow(),
            formula_evaluator=AstevalFormulaEvaluator(),
            plate_normalizer=PlateNormalizer(),
            replicate_aggregator=ReplicateAggregator(),
            readout_data_repo=readout_data_repo,
            run_repo=run_repo,
            protocol_repo=protocol_repo,
        )

        result = await engine.compute_for_run(run.id, workspace_id=WS)

        assert isinstance(result, Success)
        # No computed data because the only calculated readout is cross-protocol
        assert result.unwrap().computed_readouts == []
        readout_data_repo.save_bulk.assert_not_awaited()


class TestChainedCalculatedReadouts:
    """Two calculated readouts where B depends on A. Topological sort required."""

    @pytest.mark.asyncio
    async def test_chained_calculated_readouts(self) -> None:
        raw_rd = ReadoutDefinition(
            protocol_id=_PH,
            name="Raw",
            data_type=ReadoutDataType.NUMERIC,
        )
        calc_a = ReadoutDefinition(
            protocol_id=_PH,
            name="StepA",
            data_type=ReadoutDataType.NUMERIC,
            is_calculated=True,
            calculation_formula="Raw + 10",
        )
        calc_b = ReadoutDefinition(
            protocol_id=_PH,
            name="StepB",
            data_type=ReadoutDataType.NUMERIC,
            is_calculated=True,
            calculation_formula="StepA * 2",
        )

        protocol = _make_protocol([raw_rd, calc_a, calc_b])
        run = _make_run(protocol.id)
        well = run.wells[0]
        mol_id = uuid.uuid4()

        raw_readout = ReadoutData(
            workspace_id=WS,
            run_id=run.id,
            well_id=well.id,
            molecule_id=mol_id,
            batch_id=well.batch_id,
            readout_definition_id=raw_rd.id,
            value=QualifiedValue(value=5.0),
        )

        readout_data_repo, run_repo, protocol_repo = _make_repos()
        run_repo.find_by_id.return_value = run
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
        protocol_repo.find_by_id.return_value = protocol
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
        readout_data_repo.find_by_run.return_value = [raw_readout]
        readout_data_repo.delete_computed_for_run.return_value = 0

        engine = ReadoutCalculationEngine(
            uow=_fake_uow(),
            formula_evaluator=AstevalFormulaEvaluator(),
            plate_normalizer=PlateNormalizer(),
            replicate_aggregator=ReplicateAggregator(),
            readout_data_repo=readout_data_repo,
            run_repo=run_repo,
            protocol_repo=protocol_repo,
        )

        result = await engine.compute_for_run(run.id, workspace_id=WS)

        assert isinstance(result, Success)
        computed = result.unwrap().computed_readouts
        assert len(computed) == 2

        step_a = next(c for c in computed if c.readout_definition_id == calc_a.id)
        step_b = next(c for c in computed if c.readout_definition_id == calc_b.id)

        # Raw=5, StepA=5+10=15, StepB=15*2=30
        assert step_a.value.value == 15.0
        assert step_b.value.value == 30.0


class TestCircularDependencyDetected:
    """Circular dependency in calculated readouts raises ValidationError."""

    @pytest.mark.asyncio
    async def test_circular_dependency_raises(self) -> None:
        raw_rd = ReadoutDefinition(
            protocol_id=_PH,
            name="Raw",
            data_type=ReadoutDataType.NUMERIC,
        )
        calc_a = ReadoutDefinition(
            protocol_id=_PH,
            name="CalcA",
            data_type=ReadoutDataType.NUMERIC,
            is_calculated=True,
            calculation_formula="CalcB + 1",
        )
        calc_b = ReadoutDefinition(
            protocol_id=_PH,
            name="CalcB",
            data_type=ReadoutDataType.NUMERIC,
            is_calculated=True,
            calculation_formula="CalcA + 1",
        )

        protocol = _make_protocol([raw_rd, calc_a, calc_b])
        run = _make_run(protocol.id)
        well = run.wells[0]

        raw_readout = ReadoutData(
            workspace_id=WS,
            run_id=run.id,
            well_id=well.id,
            molecule_id=uuid.uuid4(),
            batch_id=well.batch_id,
            readout_definition_id=raw_rd.id,
            value=QualifiedValue(value=1.0),
        )

        readout_data_repo, run_repo, protocol_repo = _make_repos()
        run_repo.find_by_id.return_value = run
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
        protocol_repo.find_by_id.return_value = protocol
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
        readout_data_repo.find_by_run.return_value = [raw_readout]
        readout_data_repo.delete_computed_for_run.return_value = 0

        engine = ReadoutCalculationEngine(
            uow=_fake_uow(),
            formula_evaluator=AstevalFormulaEvaluator(),
            plate_normalizer=PlateNormalizer(),
            replicate_aggregator=ReplicateAggregator(),
            readout_data_repo=readout_data_repo,
            run_repo=run_repo,
            protocol_repo=protocol_repo,
        )

        result = await engine.compute_for_run(run.id, workspace_id=WS)
        assert isinstance(result, Failure)
        assert "ircular dependency" in str(result.failure())


class TestMultiFormulaNormalization:
    """A readout def with `normalizations={%inh, z_score}` should produce
    one ReadoutData row per (well, formula). Each computed row carries
    the formula in `normalization_applied`.
    """

    @pytest.mark.asyncio
    async def test_emits_one_row_per_formula_per_well(self) -> None:
        # Single readout def with two formulas in its set.
        raw_rd = ReadoutDefinition(
            protocol_id=_PH,
            name="Raw AU",
            data_type=ReadoutDataType.NUMERIC,
            normalizations=frozenset(
                {
                    ReadoutNormalization.PERCENT_INHIBITION,
                    ReadoutNormalization.Z_SCORE,
                }
            ),
        )
        protocol = _make_protocol([raw_rd])

        # Build a run with two pos-control wells (z-score needs SD > 0),
        # one neg-control, and one sample well — all on a single plate.
        run = Run.create(
            workspace_id=WS,
            protocol_id=protocol.id,
            run_date=date(2026, 4, 6),
            operator=USER,
        )
        plate = Plate(run_id=run.id, plate_number=1, format=PlateFormat.F96)
        run.plates.append(plate)
        sample_well = Well(
            plate_id=plate.id, row="A", column=1, well_type=WellType.SAMPLE,
            batch_id=uuid.uuid4(),
        )
        pos1 = Well(plate_id=plate.id, row="A", column=2, well_type=WellType.POSITIVE_CONTROL)
        pos2 = Well(plate_id=plate.id, row="A", column=3, well_type=WellType.POSITIVE_CONTROL)
        neg = Well(plate_id=plate.id, row="A", column=4, well_type=WellType.NEGATIVE_CONTROL)
        run.wells.extend([sample_well, pos1, pos2, neg])

        mol_id = uuid.uuid4()
        raw_data = [
            ReadoutData(
                workspace_id=WS, run_id=run.id, well_id=sample_well.id,
                molecule_id=mol_id, batch_id=sample_well.batch_id,
                readout_definition_id=raw_rd.id,
                value=QualifiedValue(value=50.0),
            ),
            ReadoutData(
                workspace_id=WS, run_id=run.id, well_id=pos1.id,
                readout_definition_id=raw_rd.id,
                value=QualifiedValue(value=100.0),
            ),
            ReadoutData(
                workspace_id=WS, run_id=run.id, well_id=pos2.id,
                readout_definition_id=raw_rd.id,
                value=QualifiedValue(value=90.0),
            ),
            ReadoutData(
                workspace_id=WS, run_id=run.id, well_id=neg.id,
                readout_definition_id=raw_rd.id,
                value=QualifiedValue(value=0.0),
            ),
        ]

        readout_data_repo, run_repo, protocol_repo = _make_repos()
        run_repo.find_by_id_in_workspace = AsyncMock(return_value=run)
        protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
        readout_data_repo.find_by_run.return_value = raw_data
        readout_data_repo.delete_computed_for_run.return_value = 0

        engine = ReadoutCalculationEngine(
            uow=_fake_uow(),
            formula_evaluator=AstevalFormulaEvaluator(),
            plate_normalizer=PlateNormalizer(),
            replicate_aggregator=ReplicateAggregator(),
            readout_data_repo=readout_data_repo,
            run_repo=run_repo,
            protocol_repo=protocol_repo,
        )

        result = await engine.compute_for_run(run.id, workspace_id=WS)
        assert isinstance(result, Success)

        computed = [
            r for r in result.unwrap().computed_readouts
            if r.readout_definition_id == raw_rd.id
        ]
        # 1 sample × 2 formulas = 2 computed rows
        assert len(computed) == 2
        formulas = {c.normalization_applied for c in computed}
        assert formulas == {
            ReadoutNormalization.PERCENT_INHIBITION,
            ReadoutNormalization.Z_SCORE,
        }
        # Both rows must reference the same well + readout def
        assert all(c.well_id == sample_well.id for c in computed)
        assert all(c.is_computed for c in computed)
        assert all(c.molecule_id == mol_id for c in computed)
