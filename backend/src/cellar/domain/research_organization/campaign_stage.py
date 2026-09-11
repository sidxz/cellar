"""CampaignStage and StageCriterion — named hit-triage stages for a Campaign.

A stage is a named AND-combination of rules over the campaign's channels
(readouts). Stages form a forest via `parent_stage_id`: a child stage is
evaluated only on its parent's hits (see `stage_evaluation.evaluate_stages`,
added separately). `StageOverride` (owned by CampaignResult, one per
(result, stage)) lets a chemist manually promote/demote a compound with an
audited reason.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from cellar.domain.research_organization.enums import StageOutcome
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.hit_criterion import compare

MAX_STAGE_NAME_LEN = 120
MAX_STAGE_CRITERIA = 10

_VALID_STAGE_OPERATORS = {"lt", "lte", "gt", "gte", "between"}


class _Unset:
    """Singleton sentinel meaning "caller did not supply this field".

    Same shape as `application.research_organization.update_campaign_channel
    ._Unset`, but domain-owned so `Campaign.update_stage` (and its command,
    Task 9) can import one sentinel instead of each layer defining its own.
    """

    _instance: _Unset | None = None

    def __new__(cls) -> _Unset:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNSET"


UNSET = _Unset()


def normalize_stage_name(name: str) -> str:
    """Trim `name`; raise `ValidationError` if empty or over `MAX_STAGE_NAME_LEN`."""
    normalized = (name or "").strip()
    if not normalized:
        raise ValidationError("CampaignStage.name must not be empty")
    if len(normalized) > MAX_STAGE_NAME_LEN:
        raise ValidationError(
            f"CampaignStage.name must be at most {MAX_STAGE_NAME_LEN} chars, "
            f"got {len(normalized)}"
        )
    return normalized


@dataclass(frozen=True)
class StageCriterion:
    """One AND-ed rule inside a CampaignStage. Numeric only — unlike
    HitCriterion, the string-based `in` operator is not accepted here."""

    channel_id: uuid.UUID
    operator: str  # lt, lte, gt, gte, between
    value: float | list[float]

    def __post_init__(self) -> None:
        if self.operator not in _VALID_STAGE_OPERATORS:
            raise ValidationError(
                f"StageCriterion operator must be one of {_VALID_STAGE_OPERATORS}, "
                f"got '{self.operator}'"
            )
        if self.operator == "between":
            if (
                not isinstance(self.value, list)
                or len(self.value) != 2
                or not all(
                    isinstance(v, (int, float)) and not isinstance(v, bool) for v in self.value
                )
            ):
                raise ValidationError(
                    "StageCriterion with 'between' operator requires value=[low, high] "
                    "(two numbers)"
                )
            low, high = self.value
            if low > high:
                raise ValidationError(
                    f"StageCriterion 'between' requires low <= high; got [{low}, {high}]"
                )
        else:
            if not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
                raise ValidationError(
                    f"StageCriterion with '{self.operator}' operator requires a numeric value"
                )

    def is_met(self, value: float) -> bool:
        return compare(self.operator, value, self.value)

    def to_dict(self) -> dict:
        return {
            "channel_id": str(self.channel_id),
            "operator": self.operator,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> StageCriterion:
        return cls(
            channel_id=uuid.UUID(d["channel_id"]),
            operator=d["operator"],
            value=d["value"],
        )


@dataclass
class CampaignStage:
    """Owned entity of Campaign. Zero-criteria stages are valid — a scaffold
    while the chemist is still building the funnel; the UI flags them as
    "no criteria yet"."""

    campaign_id: uuid.UUID
    name: str
    display_order: int
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    parent_stage_id: uuid.UUID | None = None
    criteria: list[StageCriterion] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = normalize_stage_name(self.name)
        if self.display_order < 0:
            raise ValidationError("CampaignStage.display_order must be >= 0")
        if len(self.criteria) > MAX_STAGE_CRITERIA:
            raise ValidationError(
                f"Maximum {MAX_STAGE_CRITERIA} stage criteria allowed, got {len(self.criteria)}"
            )


@dataclass(frozen=True)
class StageOverride:
    """Owned by CampaignResult, keyed by stage_id. Manually forces a stage's
    outcome for one compound, with an audited reason."""

    result_id: uuid.UUID
    stage_id: uuid.UUID
    forced_outcome: StageOutcome
    reason: str
    overridden_by: uuid.UUID
    overridden_at: datetime

    def __post_init__(self) -> None:
        if self.forced_outcome not in (StageOutcome.HIT, StageOutcome.MISS):
            raise ValidationError(
                f"StageOverride.forced_outcome must be hit or miss, got '{self.forced_outcome}'"
            )
        reason = (self.reason or "").strip()
        if not reason:
            raise ValidationError("StageOverride.reason must not be empty")
        object.__setattr__(self, "reason", reason)
