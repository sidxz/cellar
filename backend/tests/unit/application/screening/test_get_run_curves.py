"""Unit tests for GetRunCurves."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest

from cellar.application.screening.get_run_curves import GetRunCurves, GetRunCurvesQuery
from cellar.application.screening.plate_map_reader import (
    PlateMapData,
    PlateMapResult,
    WellMapEntry,
)
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
        self.uc = GetRunCurves(
            uow=FakeUoW(), curve_repo=self.curve_repo, plate_map_reader=self.reader
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

    def query(self, channel: str | None = None) -> GetRunCurvesQuery:
        return GetRunCurvesQuery(workspace_id=self.ws, run_id=self.run_id, channel=channel)


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
