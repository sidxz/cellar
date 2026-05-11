"""HitCriterion value object — defines a single filter rule for hit identification."""

from __future__ import annotations

from dataclasses import dataclass

from chem_vault.domain.shared.errors import ValidationError

_VALID_OPERATORS = {"gt", "lt", "gte", "lte", "in", "between"}
_MAX_CRITERIA = 3


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
    """

    readout_name: str
    operator: str  # gt, lt, gte, lte, in, between
    value: float | list[str] | list[float]

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
                    "HitCriterion with 'between' operator requires value=[low, high] "
                    "(two numbers)"
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
        return {
            "readout_name": self.readout_name,
            "operator": self.operator,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> HitCriterion:
        return cls(
            readout_name=data["readout_name"],
            operator=data["operator"],
            value=data["value"],
        )


def validate_hit_criteria(criteria: list[HitCriterion]) -> None:
    if len(criteria) > _MAX_CRITERIA:
        raise ValidationError(
            f"Maximum {_MAX_CRITERIA} hit criteria rules allowed, got {len(criteria)}"
        )
