"""Unit tests for GetRunCurves."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock, MagicMock

import pytest

from cellar.application.screening.get_run_curves import GetRunCurves, GetRunCurvesQuery
from cellar.application.screening.plate_map_reader import (
    PlateMapData,
    PlateMapResult,
    WellMapEntry,
)
from cellar.domain.screening_assay.curve_derivative import DerivativeCurve
from cellar.domain.screening_assay.enums import HolderKind
from cellar.domain.screening_assay.holder import holder_label, position_label
from cellar.domain.screening_assay.measured_curve import (
    CurveChannel,
    MeasuredCurve,
    ReportedPoint,
)
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ValidationError
from tests.fakes.fake_auth import FakeAuth


class FakeUoW:
    async def commit(self) -> list:  # pragma: no cover
        return []

    async def rollback(self) -> None:  # pragma: no cover
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


CHANNELS = [
    CurveChannel(key="ratio", label="Ratio", x_unit="°C", y_unit=None, order=0),
    CurveChannel(key="f330", label="F330", x_unit="°C", y_unit="a.u.", order=1),
]


def _entry(column: int) -> WellMapEntry:
    return WellMapEntry(
        well_id=uuid.uuid4(),
        position=f"A{column}",
        row="A",
        column=column,
        well_type="sample",
        position_label=position_label(HolderKind.CASSETTE, "A", column),
    )


class Harness:
    def __init__(self, *, with_curves: bool = True) -> None:
        self.viewer = FakeAuth(role="viewer")
        self.ws = self.viewer.workspace_id
        self.run_id = uuid.uuid4()
        self.entries = [_entry(c) for c in (1, 2, 3)]
        # A second plate with no curves comes first, so the holder must be found by its wells.
        self.other = PlateMapData(plate_id=uuid.uuid4(), plate_number=2, format="96", wells=[])
        self.holder = PlateMapData(
            plate_id=uuid.uuid4(),
            plate_number=1,
            format="",
            wells=self.entries,
            holder_kind="cassette",
            holder_rows=1,
            holder_columns=3,
        )
        self.reader = AsyncMock()
        self.reader.get_plate_map = AsyncMock(
            return_value=PlateMapResult(
                run_id=self.run_id,
                dose_unit="uM",
                plates=[self.other, self.holder] if with_curves else [],
            )
        )
        self.curve_repo = AsyncMock()
        self.curve_repo.list_channels = AsyncMock(return_value=CHANNELS if with_curves else [])
        self.curve_repo.find_by_run = AsyncMock(
            side_effect=lambda ws, run_id, *, channel_key: [
                self._curve(e, channel_key) for e in reversed(self.entries)
            ]
        )
        self.derivative = MagicMock()
        self.derivative.derivative = MagicMock(
            side_effect=lambda x, y, *, window: DerivativeCurve(x=(0.5, 1.5), y=(9.0, 9.5))
        )
        self.uc = GetRunCurves(
            uow=FakeUoW(),
            curve_repo=self.curve_repo,
            plate_map_reader=self.reader,
            derivative=self.derivative,
        )

    def _curve(self, entry: WellMapEntry, key: str) -> MeasuredCurve:
        channel = next(c for c in CHANNELS if c.key == key)
        return MeasuredCurve(
            workspace_id=self.ws,
            run_id=self.run_id,
            well_id=entry.well_id,
            channel_key=key,
            channel_label=channel.label,
            x_unit=channel.x_unit,
            y_unit=channel.y_unit,
            channel_order=channel.order,
            x=(20.0, 21.0),
            y=(1.0, 1.1),
            reported=(ReportedPoint("transition", 1, "Transition #1", 55.0, "°C"),),
            reader="stub",
        )

    def query(
        self, channel: str | None = None, *, view: str = "measured", window: float | None = None
    ) -> GetRunCurvesQuery:
        return GetRunCurvesQuery(
            workspace_id=self.ws, run_id=self.run_id, channel=channel, view=view, window=window
        )


async def test_returns_first_channel_by_default():
    h = Harness()
    out = (await h.uc(h.query(), auth=h.viewer)).unwrap()

    assert [c.key for c in out.channels] == ["ratio", "f330"] and out.channel.key == "ratio"
    h.curve_repo.find_by_run.assert_awaited_once_with(h.ws, h.run_id, channel_key="ratio")
    h.curve_repo.list_channels.assert_awaited_once_with(h.ws, h.run_id)
    h.reader.get_plate_map.assert_awaited_once_with(h.ws, h.run_id)
    assert out.holder_label == holder_label(HolderKind.CASSETTE, 1, 3) and len(out.positions) == 3
    assert (out.holder_kind, out.holder_rows, out.holder_columns) == ("cassette", 1, 3)
    assert (out.run_id, out.dose_unit) == (h.run_id, "uM")
    # Curves follow the positions' order, whatever order the repository returned.
    assert [c.well_id for c in out.curves] == [e.well_id for e in h.entries]
    assert out.curves[0].x == (20.0, 21.0) and out.curves[0].reported[0].value == 55.0


async def test_returns_requested_channel():
    h = Harness()
    out = (await h.uc(h.query("f330"), auth=h.viewer)).unwrap()
    assert out.channel.key == "f330"
    h.curve_repo.find_by_run.assert_awaited_once_with(h.ws, h.run_id, channel_key="f330")


async def test_unknown_channel_is_validation_error():
    h = Harness()
    failure = (await h.uc(h.query("nope"), auth=h.viewer)).failure()
    assert isinstance(failure, ValidationError) and "Unknown channel 'nope'" in str(failure)
    h.curve_repo.find_by_run.assert_not_awaited()


async def test_run_without_curves_is_empty_not_an_error():
    h = Harness(with_curves=False)
    out = (await h.uc(h.query(), auth=h.viewer)).unwrap()
    assert (out.channels, out.channel, out.curves, out.positions) == ((), None, (), ())
    assert (out.holder_kind, out.holder_rows, out.holder_columns) == ("plate", None, None)
    assert out.holder_label == holder_label(HolderKind.PLATE, None, None)
    h.curve_repo.find_by_run.assert_not_awaited()


async def test_run_without_curves_uses_first_plate_as_holder():
    h = Harness()
    h.curve_repo.list_channels.return_value = []
    out = (await h.uc(h.query(), auth=h.viewer)).unwrap()
    assert out.holder_kind == "plate" and out.positions == () and out.curves == ()


async def test_run_not_found():
    h = Harness()
    h.reader.get_plate_map.return_value = None
    failure = (await h.uc(h.query(), auth=h.viewer)).failure()
    assert isinstance(failure, NotFoundError) and str(h.run_id) in str(failure)
    h.curve_repo.list_channels.assert_not_awaited()


async def test_other_workspace_raises_not_found():
    h = Harness()
    with pytest.raises(NotFoundError):
        await h.uc(h.query(), auth=FakeAuth(role="viewer"))
    h.reader.get_plate_map.assert_not_awaited()


async def test_no_role_raises_authorization_error():
    h = Harness()
    with pytest.raises(AuthorizationError):
        await h.uc(h.query(), auth=FakeAuth(role="guest", workspace_id=h.ws))
    h.reader.get_plate_map.assert_not_awaited()


async def test_derivative_view_states_the_window_used():
    h = Harness()
    out = (await h.uc(h.query(view="derivative"), auth=h.viewer)).unwrap()
    x_range = 21.0 - 20.0
    assert out.view == "derivative" and out.window == pytest.approx(0.05 * x_range)
    h.derivative.derivative.assert_called()
    assert out.curves[0].x == (0.5, 1.5) and out.curves[0].y == (9.0, 9.5)
    assert out.curves[0].reported[0].value == 55.0  # reported values unchanged
    assert {c.kwargs["window"] for c in h.derivative.derivative.call_args_list} == {out.window}


async def test_measured_view_does_not_call_the_derivative_service():
    h = Harness()
    out = (await h.uc(h.query(), auth=h.viewer)).unwrap()
    assert out.view == "measured" and out.window is None
    assert out.curves[0].x == (20.0, 21.0)
    h.derivative.derivative.assert_not_called()


async def test_explicit_window_is_passed_through():
    h = Harness()
    out = (await h.uc(h.query(view="derivative", window=0.25), auth=h.viewer)).unwrap()
    assert out.window == 0.25
    assert {c.kwargs["window"] for c in h.derivative.derivative.call_args_list} == {0.25}


async def test_window_up_to_the_widest_x_range_is_accepted():
    h = Harness()
    out = (await h.uc(h.query(view="derivative", window=1.0), auth=h.viewer)).unwrap()
    assert out.window == 1.0


async def test_window_larger_than_the_widest_x_range_is_clamped_to_it():
    h = Harness()  # every curve spans x 20 to 21
    out = (await h.uc(h.query(view="derivative", window=1e308), auth=h.viewer)).unwrap()
    assert out.window == 1.0
    assert {c.kwargs["window"] for c in h.derivative.derivative.call_args_list} == {1.0}


@pytest.mark.parametrize("window", [float("inf"), float("nan"), -1.0, 0.0])
async def test_window_not_finite_or_not_positive_is_a_validation_error(window):
    h = Harness()
    result = await h.uc(h.query(view="derivative", window=window), auth=h.viewer)
    assert isinstance(result.failure(), ValidationError)
    assert "above 0" in str(result.failure())
    h.derivative.derivative.assert_not_called()


async def test_derivative_view_leaves_out_a_curve_with_an_empty_derivative():
    h = Harness()
    empty_for = h.entries[1]
    h.derivative.derivative.side_effect = lambda x, y, *, window: (
        DerivativeCurve(x=(), y=())
        if y == (7.0, 7.0)
        else DerivativeCurve(x=(0.5, 1.5), y=(9.0, 9.5))
    )
    original = h.curve_repo.find_by_run.side_effect

    async def find(ws, run_id, *, channel_key):
        curves = original(ws, run_id, channel_key=channel_key)
        return [
            c.__class__(**{**c.__dict__, "y": (7.0, 7.0)}) if c.well_id == empty_for.well_id else c
            for c in curves
        ]

    h.curve_repo.find_by_run.side_effect = find
    out = (await h.uc(h.query(view="derivative"), auth=h.viewer)).unwrap()
    assert empty_for.well_id not in {c.well_id for c in out.curves} and len(out.curves) == 2
