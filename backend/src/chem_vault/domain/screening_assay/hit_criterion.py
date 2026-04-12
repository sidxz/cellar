"""HitCriterion value object — defines a single filter rule for hit identification."""

from __future__ import annotations

from dataclasses import dataclass

from chem_vault.domain.shared.errors import ValidationError

_VALID_OPERATORS = {"gt", "lt", "gte", "lte", "in"}
_MAX_CRITERIA = 3


@dataclass(frozen=True)
class HitCriterion:
    readout_name: str
    operator: str  # gt, lt, gte, lte, in
    value: float | list[str]

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
