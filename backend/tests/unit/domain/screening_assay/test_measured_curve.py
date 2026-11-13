"""Tests for the MeasuredCurve entity."""

import uuid

import pytest

from cellar.domain.screening_assay.measured_curve import (
    CurveChannel,
    MeasuredCurve,
    ReportedPoint,
)
from cellar.domain.shared.errors import ValidationError


def _curve(**overrides) -> MeasuredCurve:
    fields = dict(
        workspace_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        well_id=uuid.uuid4(),
        channel_key="ratio",
        channel_label="Ratio",
        x_unit="°C",
        y_unit=None,
        channel_order=0,
        x=(25.0, 25.057, 25.114),
        y=(0.81, 0.82, 0.83),
        reader="test-reader",
    )
    fields.update(overrides)
    return MeasuredCurve(**fields)


def test_points_are_kept_unchanged():
    c = _curve(x=(25.0, 25.057, 25.114), y=(0.81, 0.82, 0.83))
    assert c.x == (25.0, 25.057, 25.114) and c.y == (0.81, 0.82, 0.83)
    assert c.channel == CurveChannel(key="ratio", label="Ratio", x_unit="°C", y_unit=None, order=0)


@pytest.mark.parametrize(
    "x,y",
    [
        ((1.0,), (1.0,)),
        ((1.0, 2.0), (1.0,)),
        ((1.0, float("nan")), (1.0, 2.0)),
        ((1.0, 2.0), (1.0, float("inf"))),
    ],
)
def test_rejects_short_mismatched_or_non_finite_points(x, y):
    with pytest.raises(ValidationError):
        _curve(x=x, y=y)


def test_rejects_non_finite_reported_value():
    with pytest.raises(ValidationError):
        _curve(reported=(ReportedPoint("transition", 1, "T", float("nan"), "°C"),))


def test_rejects_blank_channel_key_and_negative_order():
    with pytest.raises(ValidationError):
        _curve(channel_key="  ")
    with pytest.raises(ValidationError):
        _curve(channel_order=-1)


def test_rejects_blank_reader():
    with pytest.raises(ValidationError):
        _curve(reader=" ")


def test_rejects_x_label_over_100_characters():
    assert _curve(x_label="T" * 100).x_label == "T" * 100
    with pytest.raises(ValidationError, match="100"):
        _curve(x_label="T" * 101)
