"""RefitCurvesKeepingEdits: a change to a run's rows refits only the curves it touches,
in place, with the chemist's exclusions carried to the same wells."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from cellar.application.screening.refit_curves_keeping_edits import RefitCurvesKeepingEdits
from cellar.domain.screening_assay.curve_fitting import ResponseScale
from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.enums import (
    CurveType,
    PlateFormat,
    ProtocolType,
    ReadoutDataType,
    ReadoutNormalization,
    WellType,
)
from cellar.domain.screening_assay.excluded_point_detail import (
    ExcludedPointDetail,
    ExclusionReason,
    ExclusionSource,
)
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.domain.shared.value_objects import QualifiedValue
from cellar.infrastructure.lmfit.curve_fitter import LmfitCurveFitter

WS, USER, CHEMIST = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
DOSES = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)
RESPONSES = (2.0, 8.0, 30.0, 70.0, 92.0, 98.0)


class _Curves:
    def __init__(self) -> None:
        self.by_id: dict = {}
        self.saved: list = []

    async def find_by_run(self, ws, run_id):
        return [c for c in self.by_id.values() if c.run_id == run_id]

    async def save(self, curve) -> None:
        self.by_id[curve.id] = curve
        self.saved.append(curve.id)

    async def delete(self, ws, curve_id) -> None:
        del self.by_id[curve_id]


class _Run:
    def __init__(self, layer: ReadoutNormalization | None = None) -> None:
        self.signal = ReadoutDefinition(
            protocol_id=uuid.UUID(int=0),
            name="Signal",
            data_type=ReadoutDataType.NUMERIC,
            normalizations=frozenset({layer}) if layer else None,
        )
        potency = ReadoutDefinition(
            protocol_id=uuid.UUID(int=0),
            name="Potency",
            data_type=ReadoutDataType.DOSE_RESPONSE,
            dose_response_config=DoseResponseConfig(
                curve_type=CurveType.IC50, y_readout_name="Signal", outlier_sigma=None
            ),
        )
        self.protocol = Protocol.create(
            workspace_id=WS,
            name="DR",
            protocol_type=ProtocolType.BIOCHEMICAL,
            created_by=USER,
            readout_definitions=[self.signal, potency],
        )
        self.run = Run.create(
            workspace_id=WS,
            protocol_id=self.protocol.id,
            run_date=date(2026, 11, 16),
            operator=USER,
        )
        plate = Plate(run_id=self.run.id, plate_number=1, format=PlateFormat.F96)
        self.run.plates.append(plate)
        self.rows: list[ReadoutData] = []
        self.wells: dict[tuple[str, int], Well] = {}
        for row in "AB":
            mol, batch = uuid.uuid4(), uuid.uuid4()
            for col, (dose, value) in enumerate(zip(DOSES, RESPONSES, strict=True), start=1):
                well = Well(
                    plate_id=plate.id, row=row, column=col, well_type=WellType.SAMPLE, dose=dose
                )
                self.run.wells.append(well)
                self.wells[(row, col)] = well
                self.rows.append(
                    ReadoutData(
                        workspace_id=WS,
                        run_id=self.run.id,
                        well_id=well.id,
                        molecule_id=mol,
                        batch_id=batch,
                        readout_definition_id=self.signal.id,
                        value=QualifiedValue(value=value),
                        is_computed=layer is not None,
                        normalization_applied=layer,
                    )
                )

    def flagged(self, *positions: tuple[str, int]) -> list[ReadoutData]:
        ids = {self.wells[p].id for p in positions}
        return [
            ReadoutData(
                id=r.id,
                workspace_id=WS,
                run_id=r.run_id,
                well_id=r.well_id,
                molecule_id=r.molecule_id,
                batch_id=r.batch_id,
                readout_definition_id=r.readout_definition_id,
                value=r.value,
                is_outlier=r.well_id in ids,
            )
            for r in self.rows
        ]


async def _fitted(r: _Run) -> tuple[RefitCurvesKeepingEdits, _Curves]:
    curves = _Curves()
    uc = RefitCurvesKeepingEdits(curve_repo=curves, curve_fitter=LmfitCurveFitter())
    out = await uc.refit(run=r.run, protocol=r.protocol, before=[], after=r.rows)
    assert out.created == 2
    curves.saved.clear()
    return uc, curves


def _manual(dose: float, response: float) -> ExcludedPointDetail:
    return ExcludedPointDetail(
        idx=1,
        source=ExclusionSource.MANUAL,
        excluded=True,
        reason=ExclusionReason.CONTAMINATION,
        author_id=CHEMIST,
        ts=datetime(2026, 11, 1, tzinfo=UTC),
        note="precipitate",
        concentration=dose,
        response=response,
    )


@pytest.mark.asyncio
async def test_a_flag_refits_only_its_series_in_place_keeping_the_chemists_exclusion() -> None:
    r = _Run()
    uc, curves = await _fitted(r)
    a = next(c for c in curves.by_id.values() if c.molecule_id == r.rows[0].molecule_id)
    b = next(c for c in curves.by_id.values() if c is not a)
    a.excluded_points = [_manual(DOSES[1], RESPONSES[1])]
    a.dose_response_config_snapshot = {**a.dose_response_config_snapshot, "top_constraint": 100.0}
    b_fit = (b.fitted_value, b.raw_data)

    out = await uc.refit(run=r.run, protocol=r.protocol, before=r.rows, after=r.flagged(("A", 5)))

    assert (out.refitted, out.created, out.removed, out.warning()) == (1, 0, 0, None)
    assert curves.saved == [a.id]  # same curve, B untouched
    assert (b.fitted_value, b.raw_data) == b_fit
    entries = {e.concentration: e for e in a.excluded_points}
    hand = entries[DOSES[1]]
    assert (hand.source, hand.reason, hand.author_id, hand.note) == (
        ExclusionSource.MANUAL,
        ExclusionReason.CONTAMINATION,
        CHEMIST,
        "precipitate",
    )
    assert entries[DOSES[4]].source == ExclusionSource.WELL_FLAG
    assert a.num_points == 4
    assert a.dose_response_config_snapshot["top_constraint"] == 100.0  # its own setting
    assert a.top == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_a_series_left_with_fewer_than_four_doses_loses_its_curve_and_says_so() -> None:
    r = _Run()
    uc, curves = await _fitted(r)

    out = await uc.refit(
        run=r.run,
        protocol=r.protocol,
        before=r.rows,
        after=r.flagged(("A", 1), ("A", 2), ("A", 3)),
    )

    assert (out.removed, len(curves.by_id)) == (1, 1)
    assert "1 curve removed" in (out.warning() or "")

    back = await uc.refit(
        run=r.run,
        protocol=r.protocol,
        before=r.flagged(("A", 1), ("A", 2), ("A", 3)),
        after=r.rows,
    )
    assert (back.created, len(curves.by_id)) == (1, 2)  # unflagged: the curve comes back


class _ScaleSpy(LmfitCurveFitter):
    def __init__(self) -> None:
        self.scales: list[ResponseScale | None] = []

    def fit(self, points, config, scale=None):
        self.scales.append(scale)
        return super().fit(points, config, scale)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("layer", "scale"),
    [(ReadoutNormalization.PERCENT_INHIBITION, ResponseScale()), (None, None)],
)
async def test_a_refit_reads_the_layer_on_its_response_scale(layer, scale) -> None:
    """A series on a % inhibition layer is refitted on 0-100 %; a raw one on no scale."""
    r = _Run(layer)
    fitter = _ScaleSpy()
    uc = RefitCurvesKeepingEdits(curve_repo=_Curves(), curve_fitter=fitter)

    out = await uc.refit(run=r.run, protocol=r.protocol, before=[], after=r.rows)

    assert out.created == 2
    assert fitter.scales == [scale, scale]
