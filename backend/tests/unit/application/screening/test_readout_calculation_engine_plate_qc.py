"""Plate QC per readout x layer, and control-compound potency per plate."""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest
from returns.result import Success

from cellar.application.screening.readout_calculation_engine import ReadoutCalculationEngine
from cellar.domain.screening_assay.enums import (
    PlateFormat,
    ProtocolType,
    ReadoutDataType,
    ReadoutNormalization,
    WellType,
)
from cellar.domain.screening_assay.plate_normalizer import PlateNormalizer
from cellar.domain.screening_assay.plate_quality import PlateQualityCalculator
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.replicate_aggregator import ReplicateAggregator
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.domain.shared.value_objects import QualifiedValue
from cellar.infrastructure.computation.asteval_evaluator import AstevalFormulaEvaluator

WS = uuid.uuid4()
USER = uuid.uuid4()
_PH = uuid.UUID(int=0)
PI = ReadoutNormalization.PERCENT_INHIBITION


def _uow():
    uow = AsyncMock()
    uow.is_active = True
    return uow


class _Plate:
    """A run with one plate; ``add`` places a well and its raw value."""

    def __init__(self, protocol: Protocol) -> None:
        self.run = Run.create(
            workspace_id=WS, protocol_id=protocol.id, run_date=date(2026, 11, 16), operator=USER
        )
        self.plate = Plate(run_id=self.run.id, plate_number=1, format=PlateFormat.F96)
        self.run.plates.append(self.plate)
        self.rows: list[ReadoutData] = []
        self._n = 0

    def add(self, rd, well_type, value, *, dose=None, molecule=None) -> Well:
        self._n += 1
        well = Well(
            plate_id=self.plate.id,
            row="ABCDEFGH"[(self._n - 1) // 12],
            column=(self._n - 1) % 12 + 1,
            well_type=well_type,
            dose=dose,
        )
        self.run.wells.append(well)
        self.rows.append(
            ReadoutData(
                workspace_id=WS,
                run_id=self.run.id,
                well_id=well.id,
                molecule_id=molecule,
                readout_definition_id=rd.id,
                value=QualifiedValue(value=value),
            )
        )
        return well


async def _compute(protocol: Protocol, p: _Plate) -> Run:
    readout_repo, run_repo, protocol_repo = AsyncMock(), AsyncMock(), AsyncMock()
    run_repo.find_by_id_in_workspace = AsyncMock(return_value=p.run)
    protocol_repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
    readout_repo.find_by_run.return_value = p.rows
    engine = ReadoutCalculationEngine(
        uow=_uow(),
        formula_evaluator=AstevalFormulaEvaluator(),
        plate_normalizer=PlateNormalizer(),
        replicate_aggregator=ReplicateAggregator(),
        readout_data_repo=readout_repo,
        run_repo=run_repo,
        protocol_repo=protocol_repo,
        dispatcher=AsyncMock(),
        plate_quality=PlateQualityCalculator(),
    )
    assert isinstance(await engine.compute_for_run(p.run.id, workspace_id=WS), Success)
    return p.run


@pytest.mark.asyncio
async def test_plate_qc_per_readout_and_layer_beside_the_legacy_z_prime() -> None:
    signal = ReadoutDefinition(
        protocol_id=_PH,
        name="Signal",
        data_type=ReadoutDataType.NUMERIC,
        normalizations=frozenset({PI}),
    )
    other = ReadoutDefinition(protocol_id=_PH, name="Other", data_type=ReadoutDataType.NUMERIC)
    protocol = Protocol.create(
        workspace_id=WS,
        name="QC",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=USER,
        readout_definitions=[signal, other],
    )
    p = _Plate(protocol)
    for v in (100.0, 98.0, 102.0):  # HIGH convention: POS = uninhibited
        p.add(signal, WellType.POSITIVE_CONTROL, v)
    for v in (10.0, 12.0, 8.0):
        p.add(signal, WellType.NEGATIVE_CONTROL, v)
    p.add(signal, WellType.SAMPLE, 50.0, molecule=uuid.uuid4())
    p.add(other, WellType.SAMPLE, 7.0, molecule=uuid.uuid4())  # no controls: no entry

    run = await _compute(protocol, p)

    plate_id = str(p.plate.id)
    per_layer = run.qc_metrics["plates"][plate_id]
    assert list(per_layer) == [str(signal.id)]
    raw = per_layer[str(signal.id)]["raw"]
    assert raw["z_prime"] == pytest.approx(1 - 12 / 90, abs=1e-3)
    assert raw["classification"] == "excellent"
    assert (raw["pos_mean"], raw["pos_sd"], raw["pos_n"]) == pytest.approx((100.0, 2.0, 3))
    assert (raw["neg_mean"], raw["neg_sd"], raw["neg_n"]) == pytest.approx((10.0, 2.0, 3))
    assert raw["s2b"] == pytest.approx(10.0)
    inh = per_layer[str(signal.id)]["percent_inhibition"]
    assert inh["z_prime"] == pytest.approx(raw["z_prime"], abs=1e-3)
    assert (inh["pos_mean"], inh["neg_mean"]) == pytest.approx((0.0, 100.0))
    assert inh["pos_sd"] == pytest.approx(200 / 90)
    assert inh["s2b"] is None  # a ratio of % means says nothing
    # The legacy per-plate entry stays, from the first readout's raw layer.
    assert run.qc_metrics["z_prime"][plate_id] == {
        "z_prime": 0.867,
        "classification": "excellent",
        "pos_mean": 100.0,
        "pos_sd": 2.0,
        "neg_mean": 10.0,
        "neg_sd": 2.0,
        "s2b": 10.0,
    }


@pytest.mark.asyncio
async def test_one_well_per_control_stores_means_without_a_z_prime() -> None:
    signal = ReadoutDefinition(protocol_id=_PH, name="Signal", data_type=ReadoutDataType.NUMERIC)
    protocol = Protocol.create(
        workspace_id=WS,
        name="QC",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=USER,
        readout_definitions=[signal],
    )
    p = _Plate(protocol)
    p.add(signal, WellType.POSITIVE_CONTROL, 100.0)
    p.add(signal, WellType.NEGATIVE_CONTROL, 10.0)
    p.add(signal, WellType.NEGATIVE_CONTROL, 12.0)

    run = await _compute(protocol, p)

    raw = run.qc_metrics["plates"][str(p.plate.id)][str(signal.id)]["raw"]
    assert raw["z_prime"] is None
    assert raw["classification"] == "insufficient_data"
    assert (raw["pos_mean"], raw["pos_sd"], raw["pos_n"]) == (100.0, None, 1)
    assert (raw["neg_mean"], raw["neg_n"]) == (11.0, 2)
