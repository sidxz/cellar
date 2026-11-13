"""MeltingStep: a Tm on one position's trace, with its review rules."""

from __future__ import annotations

import math
import uuid

import pytest

from cellar.domain.screening_assay.measured_curve import ReportedPoint
from cellar.domain.screening_assay.melting_step import (
    REASON_MAX,
    MeltingStep,
    MeltingStepSource,
    MeltingStepStatus,
)
from cellar.domain.shared.errors import ValidationError

UNREVIEWED = MeltingStepStatus.UNREVIEWED
ACCEPTED = MeltingStepStatus.ACCEPTED
REJECTED = MeltingStepStatus.REJECTED
RANGE = (25.0, 95.0)


def _step(value: float = 64.0) -> MeltingStep:
    return MeltingStep.from_reported(
        workspace_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        well_id=uuid.uuid4(),
        channel_key="ratio",
        point=ReportedPoint(kind="transition", ordinal=1, label="Tm 1", value=value, unit="°C"),
    )


def test_from_reported_copies_value_and_label_unreviewed():
    step = _step()
    assert step.source is MeltingStepSource.INSTRUMENT
    assert step.value == 64.0 and step.instrument_value == 64.0
    assert step.instrument_label == "Tm 1"
    assert step.status is UNREVIEWED and step.counts
    assert step.reason is None and step.changed_by is None and step.version == 1


def test_from_reported_refuses_other_kinds():
    with pytest.raises(ValidationError):
        MeltingStep.from_reported(
            workspace_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            well_id=uuid.uuid4(),
            channel_key="ratio",
            point=ReportedPoint(kind="onset", ordinal=1, label="On", value=50.0, unit="°C"),
        )


def test_reject_needs_a_reason_and_stops_counting():
    step, u = _step(), uuid.uuid4()
    with pytest.raises(ValidationError, match="reason"):
        step.review(status=REJECTED, value=64.0, reason="  ", x_range=RANGE, by=u)
    assert step.status is UNREVIEWED and step.version == 1

    changes = step.review(status=REJECTED, value=64.0, reason=" noisy ", x_range=RANGE, by=u)
    assert changes == [("status", "unreviewed", "rejected"), ("reason", None, "noisy")]
    assert not step.counts and step.reason == "noisy"
    assert step.changed_by == u and step.changed_at is not None and step.version == 2


def test_accept_needs_no_reason_and_counts():
    step = _step()
    changes = step.review(status=ACCEPTED, value=64.0, reason=None, x_range=RANGE, by=uuid.uuid4())
    assert changes == [("status", "unreviewed", "accepted")] and step.counts


def test_correcting_away_from_instrument_value_needs_a_reason_and_keeps_the_instrument_value():
    step, u = _step(), uuid.uuid4()
    with pytest.raises(ValidationError, match="A reason is required"):
        step.review(status=UNREVIEWED, value=63.2, reason=None, x_range=RANGE, by=u)
    changes = step.review(
        status=UNREVIEWED, value=63.2, reason="peak picked by hand", x_range=RANGE, by=u
    )
    assert ("value", "64", "63.2") in changes and step.instrument_value == 64.0
    assert step.version == 2


def test_back_to_instrument_value_needs_no_reason():
    step, u = _step(), uuid.uuid4()
    step.review(status=UNREVIEWED, value=63.2, reason="hand pick", x_range=RANGE, by=u)
    changes = step.review(status=UNREVIEWED, value=64.0, reason=None, x_range=RANGE, by=u)
    assert changes == [("value", "63.2", "64"), ("reason", "hand pick", None)]
    assert step.value == 64.0 and step.version == 3


@pytest.mark.parametrize("value", [24.9, 95.1, math.nan, math.inf])
def test_value_outside_trace_range_is_validation_error(value: float):
    step = _step()
    with pytest.raises(ValidationError, match="The value must lie within the trace, 25 to 95 °C"):
        step.review(status=UNREVIEWED, value=value, reason="x", x_range=RANGE, by=uuid.uuid4())
    assert step.value == 64.0 and step.version == 1


def test_range_edges_are_inclusive():
    step = _step()
    step.review(status=UNREVIEWED, value=25.0, reason="edge", x_range=RANGE, by=uuid.uuid4())
    assert step.value == 25.0


def test_reason_longer_than_limit_is_validation_error():
    step = _step()
    with pytest.raises(ValidationError):
        step.review(
            status=REJECTED,
            value=64.0,
            reason="x" * (REASON_MAX + 1),
            x_range=RANGE,
            by=uuid.uuid4(),
        )


def test_no_change_returns_nothing_and_keeps_version():
    step = _step()
    assert (
        step.review(status=UNREVIEWED, value=64.0, reason="   ", x_range=RANGE, by=uuid.uuid4())
        == []
    )
    assert step.version == 1 and step.changed_by is None and step.changed_at is None


def test_manual_step_has_no_instrument_value_and_checks_range():
    u = uuid.uuid4()
    kwargs = dict(workspace_id=uuid.uuid4(), run_id=uuid.uuid4(), well_id=uuid.uuid4())
    with pytest.raises(ValidationError, match="within the trace"):
        MeltingStep.manual(
            **kwargs, channel_key="ratio", value=99.0, x_range=RANGE, reason=None, by=u
        )
    step = MeltingStep.manual(
        **kwargs, channel_key="ratio", value=58.5, x_range=RANGE, reason=" missed ", by=u
    )
    assert step.source is MeltingStepSource.MANUAL and step.status is UNREVIEWED
    assert step.instrument_value is None and step.instrument_label is None
    assert step.value == 58.5 and step.reason == "missed" and step.changed_by == u

    # a manual step's value changes only with a reason
    with pytest.raises(ValidationError, match="A reason is required"):
        step.review(status=UNREVIEWED, value=59.0, reason=None, x_range=RANGE, by=u)


def test_constructor_enforces_source_shape():
    base = dict(workspace_id=uuid.uuid4(), run_id=uuid.uuid4(), well_id=uuid.uuid4())
    with pytest.raises(ValidationError):
        MeltingStep(**base, channel_key="r", source=MeltingStepSource.INSTRUMENT, value=60.0)
    with pytest.raises(ValidationError):
        MeltingStep(
            **base,
            channel_key="r",
            source=MeltingStepSource.MANUAL,
            value=60.0,
            instrument_value=60.0,
            instrument_label="Tm 1",
        )
    with pytest.raises(ValidationError):
        MeltingStep(**base, channel_key="r", source=MeltingStepSource.MANUAL, value=math.nan)
