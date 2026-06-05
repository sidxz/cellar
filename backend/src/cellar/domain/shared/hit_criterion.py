"""HitCriterion value object — defines a single filter rule for hit identification."""

from __future__ import annotations

from dataclasses import dataclass

from cellar.domain.shared.errors import ValidationError

_VALID_OPERATORS = {"gt", "lt", "gte", "lte", "in", "between"}
_VALID_INTERCEPT_KINDS = {"ec", "ic"}
_MAX_CRITERIA = 3


@dataclass(frozen=True)
class InterceptKey:
    """Identifies one intercept on a dose-response curve by (kind, level).

    Used by :class:`HitCriterion` to target a specific intercept (e.g. EC90)
    instead of the curve's primary fitted value. Matches the persisted
    ``intercept_values[].spec.kind`` and ``.spec.level`` on a fitted curve.
    """

    kind: str  # "ec" or "ic"
    level: float  # (0, 100) exclusive — percent on the relative basis

    def __post_init__(self) -> None:
        if self.kind not in _VALID_INTERCEPT_KINDS:
            raise ValidationError(
                f"InterceptKey kind must be one of {_VALID_INTERCEPT_KINDS}, got '{self.kind}'"
            )
        if not (0 < self.level < 100):
            raise ValidationError(f"InterceptKey level must be in (0, 100), got {self.level}")

    def to_dict(self) -> dict:
        return {"kind": self.kind, "level": self.level}

    @classmethod
    def from_dict(cls, data: dict) -> InterceptKey:
        return cls(kind=data["kind"], level=data["level"])


@dataclass(frozen=True)
class HitCriterion:
    """Filter rule. Operators:

    - ``gt``/``lt``/``gte``/``lte``: value is a single number; hit if
      ``measurement <op> value``.
    - ``in``: value is a non-empty list of strings; hit if measurement
      string is in the list. (Not applicable to numeric channel cells; the
      campaign hit-call evaluator skips it.)
    - ``between``: value is a 2-element list of numbers ``[low, high]``;
      hit if ``low <= measurement <= high`` (inclusive on both ends).

    ``intercept_key`` (optional) targets a specific dose-response intercept
    (e.g. ``EC90``) on the named readout's fitted curve. ``None`` means
    "use the channel cell value as-is", which for a DR channel equals the
    curve's primary fitted value — preserves legacy criteria.
    """

    readout_name: str
    operator: str  # gt, lt, gte, lte, in, between
    value: float | list[str] | list[float]
    intercept_key: InterceptKey | None = None

    def __post_init__(self) -> None:
        if not self.readout_name or not self.readout_name.strip():
            raise ValidationError("HitCriterion readout_name must not be empty")
        if self.operator not in _VALID_OPERATORS:
            raise ValidationError(
                f"HitCriterion operator must be one of {_VALID_OPERATORS}, got '{self.operator}'"
            )
        if self.operator == "in":
            if not isinstance(self.value, list) or not self.value:
                raise ValidationError(
                    "HitCriterion with 'in' operator requires a non-empty list value"
                )
        elif self.operator == "between":
            if (
                not isinstance(self.value, list)
                or len(self.value) != 2
                or not all(isinstance(v, (int, float)) for v in self.value)
            ):
                raise ValidationError(
                    "HitCriterion with 'between' operator requires value=[low, high] (two numbers)"
                )
            low, high = self.value
            if low > high:
                raise ValidationError(
                    f"HitCriterion 'between' requires low <= high; got [{low}, {high}]"
                )
        else:
            if not isinstance(self.value, (int, float)):
                raise ValidationError(
                    f"HitCriterion with '{self.operator}' operator requires a numeric value"
                )

    def to_dict(self) -> dict:
        d: dict = {
            "readout_name": self.readout_name,
            "operator": self.operator,
            "value": self.value,
        }
        if self.intercept_key is not None:
            d["intercept_key"] = self.intercept_key.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> HitCriterion:
        ik_raw = data.get("intercept_key")
        return cls(
            readout_name=data["readout_name"],
            operator=data["operator"],
            value=data["value"],
            intercept_key=InterceptKey.from_dict(ik_raw) if ik_raw else None,
        )


def validate_hit_criteria(criteria: list[HitCriterion]) -> None:
    if len(criteria) > _MAX_CRITERIA:
        raise ValidationError(
            f"Maximum {_MAX_CRITERIA} hit criteria rules allowed, got {len(criteria)}"
        )
