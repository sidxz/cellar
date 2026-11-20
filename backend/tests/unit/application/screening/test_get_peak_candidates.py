"""GetPeakCandidates: the candidate peaks of one position of a run, on each of its signals.

Every trace is synthetic: a sigmoid step or a straight line, plus seeded Gaussian noise.
"""

from __future__ import annotations

import math
import random
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from cellar.application.screening.get_peak_candidates import (
    GetPeakCandidates,
    GetPeakCandidatesQuery,
)
from cellar.application.screening.get_run_curves import GetRunCurves, GetRunCurvesQuery
from cellar.application.screening.plate_map_reader import PlateMapResult
from cellar.domain.screening_assay.enums import PlateFormat, WellType
from cellar.domain.screening_assay.measured_curve import CurveChannel, MeasuredCurve
from cellar.domain.screening_assay.peak_detection import PeakDirection
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ValidationError
from cellar.infrastructure.computation.derivative_peak_detection import DerivativePeakDetection
from cellar.infrastructure.computation.savgol_derivative import SavgolCurveDerivative
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.screening.test_import_instrument_file import FakeUoW

WS = uuid.uuid4()
USER = uuid.uuid4()
# The run's signal order is Ratio, then 350 nm, whatever order the traces are read in.
RATIO, F350 = ("ratio", 0), ("350nm", 1)


def _x(points: int) -> tuple[float, ...]:
    return tuple(25 + 0.057 * i for i in range(points))


def _y(x: tuple[float, ...], steps: dict[float, float], seed: int) -> tuple[float, ...]:
    """A sloped baseline with the steps given as midpoint -> height."""
    rng = random.Random(seed)
    return tuple(
        0.002 * t
        + sum(height / (1 + math.exp(-(t - mid) / 1.2)) for mid, height in steps.items())
        + rng.gauss(0, 0.01)
        for t in x
    )


class Harness:
    """A sample whose 350 nm trace has a step at 60 °C and whose ratio trace has none, and a
    reference scanned further: its traces are the widest of the run on both signals."""

    def __init__(self) -> None:
        self.run = Run.create(
            workspace_id=WS, protocol_id=uuid.uuid4(), run_date=date(2026, 11, 17), operator=USER
        )
        plate = Plate(run_id=self.run.id, plate_number=1, format=PlateFormat.F96)
        self.run.plates.append(plate)
        self.ref = Well(plate_id=plate.id, row="A", column=1, well_type=WellType.REFERENCE)
        self.sample = Well(plate_id=plate.id, row="A", column=2, well_type=WellType.SAMPLE)
        self.untraced = Well(plate_id=plate.id, row="A", column=3, well_type=WellType.SAMPLE)
        self.run.wells.extend([self.ref, self.sample, self.untraced])

        short, long = _x(1000), _x(1223)  # 25 to 81.94 °C, and 25 to 94.65 °C
        # Read back with the later signal first: the answer must not follow this order.
        self.curves = [
            self.curve(self.sample, F350, short, {60.0: 1.0}, seed=1),
            self.curve(self.ref, F350, long[:1100], {55.0: 1.0}, seed=2),
            self.curve(self.ref, RATIO, long, {55.0: 1.0}, seed=3),
            self.curve(self.sample, RATIO, short, {}, seed=4),
        ]
        self.auth = FakeAuth(role="viewer", workspace_id=WS)
        self.run_repo = AsyncMock()
        self.run_repo.find_by_id_in_workspace = AsyncMock(return_value=self.run)
        self.curve_repo = AsyncMock()
        self.curve_repo.find_by_run = AsyncMock(
            side_effect=lambda ws, run_id, *, channel_key=None: [
                c for c in self.curves if channel_key in (None, c.channel_key)
            ]
        )
        self.curve_repo.list_channels = AsyncMock(
            return_value=[
                CurveChannel(key=key, label=key, x_unit="°C", y_unit=None, order=order)
                for key, order in (RATIO, F350)
            ]
        )
        detector = DerivativePeakDetection(SavgolCurveDerivative())
        self.detection = MagicMock()
        self.detection.candidates = MagicMock(side_effect=detector.candidates)
        self.uc = GetPeakCandidates(
            uow=FakeUoW([]),
            run_repo=self.run_repo,
            curve_repo=self.curve_repo,
            detection=self.detection,
        )

    def curve(
        self,
        well: Well,
        signal: tuple[str, int],
        x: tuple[float, ...],
        steps: dict[float, float],
        *,
        seed: int,
    ) -> MeasuredCurve:
        key, order = signal
        return MeasuredCurve(
            workspace_id=WS,
            run_id=self.run.id,
            well_id=well.id,
            channel_key=key,
            channel_label=key,
            x_unit="°C",
            y_unit=None,
            channel_order=order,
            x=x,
            y=_y(x, steps, seed),
            reader="stub",
        )

    def query(self, well: Well | None = None, smoothing: float | None = None):
        return GetPeakCandidatesQuery(
            workspace_id=WS,
            run_id=self.run.id,
            well_id=(well or self.sample).id,
            smoothing_window=smoothing,
        )

    async def traces_view_window(self, key: str) -> float:
        """The smoothing the Traces view uses for the derivative of this signal."""
        reader = AsyncMock()
        reader.get_plate_map = AsyncMock(
            return_value=PlateMapResult(run_id=self.run.id, dose_unit="uM", plates=[])
        )
        curves = GetRunCurves(
            uow=FakeUoW([]),
            curve_repo=self.curve_repo,
            plate_map_reader=reader,
            derivative=SavgolCurveDerivative(),
        )
        query = GetRunCurvesQuery(
            workspace_id=WS, run_id=self.run.id, channel=key, view="derivative"
        )
        window = (await curves(query, auth=self.auth)).unwrap().window
        assert window is not None
        return window


async def test_one_entry_per_signal_of_the_position_in_the_runs_signal_order():
    h = Harness()
    ratio, f350 = (await h.uc(h.query(), auth=h.auth)).unwrap()

    assert (ratio.channel_key, ratio.candidates) == ("ratio", ())  # no step: no candidate
    assert f350.channel_key == "350nm"
    (found,) = f350.candidates
    assert abs(found.value - 60.0) < 0.3 and found.direction is PeakDirection.RISING
    assert found.strength >= 10
    h.run_repo.find_by_id_in_workspace.assert_awaited_once_with(WS, h.run.id)
    h.curve_repo.find_by_run.assert_awaited_once_with(WS, h.run.id)


async def test_candidates_are_the_detectors_strongest_first():
    h = Harness()
    # The higher step is at the higher temperature: the order is by strength, not by value.
    h.curves = [h.curve(h.sample, RATIO, _x(1223), {50.0: 0.4, 72.0: 1.0}, seed=5)]
    (ratio,) = (await h.uc(h.query(), auth=h.auth)).unwrap()
    assert [round(c.value) for c in ratio.candidates] == [72, 50]
    assert ratio.candidates[0].strength > ratio.candidates[1].strength


async def test_default_smoothing_is_what_the_traces_view_uses_for_each_signal():
    h = Harness()
    ratio, f350 = (await h.uc(h.query(), auth=h.auth)).unwrap()

    # 5% of the widest trace of the run on that signal, not of the position's own trace.
    assert ratio.smoothing_window == pytest.approx(0.05 * 0.057 * 1222)
    assert f350.smoothing_window == pytest.approx(0.05 * 0.057 * 1099)
    assert ratio.smoothing_window == await h.traces_view_window("ratio")
    assert f350.smoothing_window == await h.traces_view_window("350nm")
    assert [c.kwargs["window"] for c in h.detection.candidates.call_args_list] == [
        ratio.smoothing_window,
        f350.smoothing_window,
    ]


async def test_given_smoothing_is_used():
    h = Harness()
    signals = (await h.uc(h.query(smoothing=2.0), auth=h.auth)).unwrap()
    assert [s.smoothing_window for s in signals] == [2.0, 2.0]
    assert {c.kwargs["window"] for c in h.detection.candidates.call_args_list} == {2.0}
    assert [round(c.value) for c in signals[1].candidates] == [60]


async def test_given_smoothing_is_capped_at_the_widest_trace_of_the_signal():
    h = Harness()
    ratio, f350 = (await h.uc(h.query(smoothing=1e308), auth=h.auth)).unwrap()
    assert ratio.smoothing_window == pytest.approx(0.057 * 1222)
    assert f350.smoothing_window == pytest.approx(0.057 * 1099)
    assert (ratio.candidates, f350.candidates) == ((), ())  # nothing is left to search


@pytest.mark.parametrize("smoothing", [0.0, -1.0, float("inf"), float("nan")])
async def test_smoothing_not_greater_than_zero_is_refused(smoothing: float):
    h = Harness()
    failure = (await h.uc(h.query(smoothing=smoothing), auth=h.auth)).failure()
    assert isinstance(failure, ValidationError)
    h.detection.candidates.assert_not_called()


async def test_only_the_signals_the_position_has_a_trace_on():
    h = Harness()
    h.curves = [c for c in h.curves if (c.well_id, c.channel_key) != (h.sample.id, "ratio")]
    signals = (await h.uc(h.query(), auth=h.auth)).unwrap()
    assert [s.channel_key for s in signals] == ["350nm"]


async def test_position_without_traces_has_no_signals():
    h = Harness()
    assert (await h.uc(h.query(h.untraced), auth=h.auth)).unwrap() == ()
    h.detection.candidates.assert_not_called()


async def test_position_of_another_run_is_not_found():
    h = Harness()
    stranger = Well(plate_id=uuid.uuid4(), row="A", column=1, well_type=WellType.SAMPLE)
    failure = (await h.uc(h.query(stranger), auth=h.auth)).failure()
    assert isinstance(failure, NotFoundError) and str(stranger.id) in str(failure)
    h.curve_repo.find_by_run.assert_not_awaited()


async def test_run_not_found():
    h = Harness()
    h.run_repo.find_by_id_in_workspace.return_value = None
    failure = (await h.uc(h.query(), auth=h.auth)).failure()
    assert isinstance(failure, NotFoundError) and str(h.run.id) in str(failure)
    h.curve_repo.find_by_run.assert_not_awaited()


async def test_other_workspace_raises_not_found():
    h = Harness()
    with pytest.raises(NotFoundError):
        await h.uc(h.query(), auth=FakeAuth(role="viewer"))
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()


async def test_no_role_raises_authorization_error():
    h = Harness()
    with pytest.raises(AuthorizationError):
        await h.uc(h.query(), auth=FakeAuth(role="guest", workspace_id=WS))
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()
