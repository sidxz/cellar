"""Unit tests for GetMeasuredCurvesBatch."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock, MagicMock

import pytest

from cellar.application.screening.get_measured_curves_batch import (
    GetMeasuredCurvesBatch,
    GetMeasuredCurvesBatchQuery,
)
from cellar.domain.screening_assay.curve_derivative import DerivativeCurve
from cellar.domain.screening_assay.measured_curve import MeasuredCurve
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


viewer = FakeAuth(role="viewer")
ws = viewer.workspace_id
w1, w2, w3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def curve(well_id: uuid.UUID, x: tuple[float, ...] = (20.0, 21.0)) -> MeasuredCurve:
    return MeasuredCurve(
        workspace_id=ws,
        run_id=uuid.uuid4(),
        well_id=well_id,
        channel_key="ratio",
        channel_label="Ratio",
        x_unit="°C",
        y_unit=None,
        channel_order=0,
        x=x,
        y=tuple(1.0 + i for i in range(len(x))),
        reader="stub",
    )


def query(
    well_ids: list[uuid.UUID], *, view: str = "measured", window: float | None = None
) -> GetMeasuredCurvesBatchQuery:
    return GetMeasuredCurvesBatchQuery(
        workspace_id=ws, well_ids=tuple(well_ids), channel="ratio", view=view, window=window
    )


@pytest.fixture
def curve_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_wells = AsyncMock(return_value=[curve(w2), curve(w1)])
    return repo


@pytest.fixture
def derivative() -> MagicMock:
    service = MagicMock()
    service.derivative = MagicMock(
        side_effect=lambda x, y, *, window: DerivativeCurve(x=(0.5, 1.5), y=(9.0, 9.5))
    )
    return service


@pytest.fixture
def uc(curve_repo: AsyncMock, derivative: MagicMock) -> GetMeasuredCurvesBatch:
    return GetMeasuredCurvesBatch(uow=FakeUoW(), curve_repo=curve_repo, derivative=derivative)


async def test_returns_curves_in_the_order_asked(uc, curve_repo):
    out = (await uc(query([w1, w2, w1]), auth=viewer)).unwrap()
    assert [c.well_id for c in out.curves] == [w1, w2]
    assert (out.channel, out.view, out.window) == ("ratio", "measured", None)
    curve_repo.find_by_wells.assert_awaited_once_with(ws, (w1, w2), channel_key="ratio")


async def test_position_without_a_curve_on_the_channel_is_absent(uc):
    out = (await uc(query([w1, w2, w3]), auth=viewer)).unwrap()
    assert [c.well_id for c in out.curves] == [w1, w2]


async def test_more_than_100_positions_is_refused(uc, curve_repo):
    failure = (await uc(query([uuid.uuid4() for _ in range(101)]), auth=viewer)).failure()
    assert isinstance(failure, ValidationError) and "100" in str(failure)
    assert "At most 100 positions per request" in str(failure)
    curve_repo.find_by_wells.assert_not_awaited()


async def test_exactly_100_positions_is_accepted(uc, curve_repo):
    ids = [uuid.uuid4() for _ in range(100)]
    assert (await uc(query(ids), auth=viewer)).unwrap().curves == ()
    curve_repo.find_by_wells.assert_awaited_once()


async def test_no_positions_is_empty_without_a_query(uc, curve_repo):
    out = (await uc(query([]), auth=viewer)).unwrap()
    assert out.curves == () and out.channel == "ratio"
    curve_repo.find_by_wells.assert_not_awaited()


async def test_derivative_default_window_is_over_this_requests_curves_and_is_stated(
    uc, curve_repo, derivative
):
    curve_repo.find_by_wells.return_value = [curve(w1, (20.0, 21.0)), curve(w2, (20.0, 24.0))]
    out = (await uc(query([w1, w2], view="derivative"), auth=viewer)).unwrap()
    widest_x_range = 24.0 - 20.0
    assert out.view == "derivative" and out.window == pytest.approx(0.05 * widest_x_range)
    assert {c.kwargs["window"] for c in derivative.derivative.call_args_list} == {out.window}
    assert out.curves[0].x == (0.5, 1.5)


async def test_explicit_window_is_passed_through_and_stated(uc, derivative):
    out = (await uc(query([w1, w2], view="derivative", window=0.25), auth=viewer)).unwrap()
    assert out.window == 0.25
    assert {c.kwargs["window"] for c in derivative.derivative.call_args_list} == {0.25}


async def test_window_not_above_0_is_a_validation_error(uc, derivative):
    failure = (await uc(query([w1], view="derivative", window=-1.0), auth=viewer)).failure()
    assert isinstance(failure, ValidationError)
    assert failure.message == "Enter a smoothing window greater than 0."
    derivative.derivative.assert_not_called()


async def test_measured_view_does_not_call_the_derivative_service(uc, derivative):
    out = (await uc(query([w1, w2]), auth=viewer)).unwrap()
    assert out.window is None and out.curves[0].x == (20.0, 21.0)
    derivative.derivative.assert_not_called()


async def test_other_workspace_raises_not_found(uc, curve_repo):
    with pytest.raises(NotFoundError):
        await uc(query([w1]), auth=FakeAuth(role="viewer"))
    curve_repo.find_by_wells.assert_not_awaited()


async def test_no_role_raises_authorization_error(uc, curve_repo):
    with pytest.raises(AuthorizationError):
        await uc(query([w1]), auth=FakeAuth(role="guest", workspace_id=ws))
    curve_repo.find_by_wells.assert_not_awaited()
