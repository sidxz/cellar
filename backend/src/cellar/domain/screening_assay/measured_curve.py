"""MeasuredCurve entity: a series of points an instrument recorded at one well."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime

from cellar.domain.shared.entity import Entity
from cellar.domain.shared.errors import ValidationError


@dataclass(frozen=True)
class ReportedPoint:
    """One value the instrument reported for a curve (for example a transition)."""

    kind: str
    ordinal: int
    label: str
    value: float
    unit: str


@dataclass(frozen=True)
class CurveChannel:
    """Which signal a curve carries, and its axes."""

    key: str
    label: str
    x_unit: str
    y_unit: str | None
    order: int
    x_label: str | None = None


class MeasuredCurve(Entity):
    """Raw (x, y) points recorded by an instrument at one well, for one channel.

    NOT an AggregateRoot: written once with the run's import, never updated,
    removed only when the run's data is reset.

    Invariants:
        - x and y have equal length, at least 2 points
        - every x, y and reported value is finite
        - channel_key and reader are not blank
        - channel_order >= 0
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        run_id: uuid.UUID,
        well_id: uuid.UUID,
        channel_key: str,
        channel_label: str,
        x_unit: str,
        y_unit: str | None,
        channel_order: int,
        x: tuple[float, ...],
        y: tuple[float, ...],
        reported: tuple[ReportedPoint, ...] = (),
        reader: str,
        x_label: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)

        if not channel_key.strip():
            raise ValidationError("channel_key must not be blank")
        if not reader.strip():
            raise ValidationError("reader must not be blank")
        if channel_order < 0:
            raise ValidationError("channel_order must be >= 0")
        if len(x) != len(y):
            raise ValidationError("x and y must have the same length")
        if len(x) < 2:
            raise ValidationError("A curve needs at least 2 points")
        if not all(math.isfinite(v) for v in (*x, *y)):
            raise ValidationError("Curve points must be finite numbers")
        if not all(math.isfinite(r.value) for r in reported):
            raise ValidationError("Reported values must be finite numbers")

        self.workspace_id = workspace_id
        self.run_id = run_id
        self.well_id = well_id
        self.channel_key = channel_key
        self.channel_label = channel_label
        self.x_unit = x_unit
        self.y_unit = y_unit
        self.x_label = x_label
        self.channel_order = channel_order
        self.x = tuple(x)
        self.y = tuple(y)
        self.reported = tuple(reported)
        self.reader = reader

    @property
    def channel(self) -> CurveChannel:
        return CurveChannel(
            key=self.channel_key,
            label=self.channel_label,
            x_unit=self.x_unit,
            y_unit=self.y_unit,
            order=self.channel_order,
            x_label=self.x_label,
        )
