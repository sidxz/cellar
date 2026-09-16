"""Unit tests for CampaignStage, StageCriterion, and StageOverride value objects."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.domain.research_organization.campaign_stage import (
    MAX_STAGE_CRITERIA,
    MAX_STAGE_NAME_LEN,
    UNSET,
    CampaignStage,
    StageCriterion,
    StageOverride,
    _Unset,
    normalize_stage_name,
)
from cellar.domain.research_organization.enums import StageKind, StageOutcome
from cellar.domain.shared.errors import ValidationError


class TestStageCriterion:
    @pytest.mark.parametrize(
        ("operator", "value"),
        [
            ("lt", 10.0),
            ("lte", 10.0),
            ("gt", 10.0),
            ("gte", 10.0),
            ("between", [10.0, 20.0]),
        ],
    )
    def test_accepts_valid_operators(self, operator: str, value: float | list[float]) -> None:
        StageCriterion(channel_id=uuid.uuid4(), operator=operator, value=value)  # no raise

    def test_rejects_in_operator(self) -> None:
        # "in" is HitCriterion-only (string-based); StageCriterion is numeric only.
        with pytest.raises(ValidationError):
            StageCriterion(channel_id=uuid.uuid4(), operator="in", value=10.0)

    def test_rejects_unknown_operator(self) -> None:
        with pytest.raises(ValidationError):
            StageCriterion(channel_id=uuid.uuid4(), operator="bogus", value=10.0)

    def test_between_requires_low_lte_high(self) -> None:
        with pytest.raises(ValidationError):
            StageCriterion(channel_id=uuid.uuid4(), operator="between", value=[20.0, 10.0])

    def test_between_accepts_equal_bounds(self) -> None:
        StageCriterion(channel_id=uuid.uuid4(), operator="between", value=[10.0, 10.0])  # no raise

    def test_between_requires_exactly_two_numbers(self) -> None:
        with pytest.raises(ValidationError):
            StageCriterion(channel_id=uuid.uuid4(), operator="between", value=[10.0])
        with pytest.raises(ValidationError):
            StageCriterion(channel_id=uuid.uuid4(), operator="between", value=10.0)

    def test_rejects_bool_value(self) -> None:
        with pytest.raises(ValidationError):
            StageCriterion(channel_id=uuid.uuid4(), operator="lt", value=True)
        with pytest.raises(ValidationError):
            StageCriterion(channel_id=uuid.uuid4(), operator="between", value=[True, 20.0])

    def test_rejects_non_numeric_value(self) -> None:
        with pytest.raises(ValidationError):
            StageCriterion(channel_id=uuid.uuid4(), operator="lt", value="10")  # type: ignore[arg-type]

    def test_is_frozen(self) -> None:
        crit = StageCriterion(channel_id=uuid.uuid4(), operator="lt", value=10.0)
        with pytest.raises(Exception):
            crit.operator = "gt"  # type: ignore[misc]

    def test_is_met(self) -> None:
        crit = StageCriterion(channel_id=uuid.uuid4(), operator="lt", value=10.0)
        assert crit.is_met(5.0) is True
        assert crit.is_met(15.0) is False

    def test_is_met_between_inclusive(self) -> None:
        crit = StageCriterion(channel_id=uuid.uuid4(), operator="between", value=[10.0, 20.0])
        assert crit.is_met(10.0) is True
        assert crit.is_met(20.0) is True
        assert crit.is_met(9.9) is False

    def test_to_dict_from_dict_round_trip(self) -> None:
        channel_id = uuid.uuid4()
        original = StageCriterion(channel_id=channel_id, operator="between", value=[10.0, 20.0])
        d = original.to_dict()
        assert d == {"channel_id": str(channel_id), "operator": "between", "value": [10.0, 20.0]}
        assert StageCriterion.from_dict(d) == original


class TestNormalizeStageName:
    def test_strips_whitespace(self) -> None:
        assert normalize_stage_name("  Screening Hits  ") == "Screening Hits"

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValidationError):
            normalize_stage_name("   ")

    def test_accepts_max_length(self) -> None:
        name = "x" * MAX_STAGE_NAME_LEN
        assert normalize_stage_name(name) == name

    def test_rejects_too_long(self) -> None:
        with pytest.raises(ValidationError):
            normalize_stage_name("x" * (MAX_STAGE_NAME_LEN + 1))


class TestCampaignStage:
    def test_name_is_normalized(self) -> None:
        stage = CampaignStage(campaign_id=uuid.uuid4(), name="  Screening Hits  ", display_order=0)
        assert stage.name == "Screening Hits"

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValidationError):
            CampaignStage(campaign_id=uuid.uuid4(), name="   ", display_order=0)

    def test_rejects_name_too_long(self) -> None:
        with pytest.raises(ValidationError):
            CampaignStage(
                campaign_id=uuid.uuid4(), name="x" * (MAX_STAGE_NAME_LEN + 1), display_order=0
            )

    def test_rejects_negative_display_order(self) -> None:
        with pytest.raises(ValidationError):
            CampaignStage(campaign_id=uuid.uuid4(), name="Stage", display_order=-1)

    def test_defaults(self) -> None:
        stage = CampaignStage(campaign_id=uuid.uuid4(), name="Stage", display_order=0)
        assert isinstance(stage.id, uuid.UUID)
        assert stage.parent_stage_id is None
        assert stage.criteria == []
        assert stage.kind == StageKind.CRITERIA

    def test_manual_stage_without_criteria_is_valid(self) -> None:
        stage = CampaignStage(
            campaign_id=uuid.uuid4(), name="Triage", display_order=0, kind=StageKind.MANUAL
        )
        assert stage.kind == StageKind.MANUAL
        assert stage.criteria == []

    def test_manual_stage_rejects_criteria(self) -> None:
        with pytest.raises(ValidationError, match="manual stage has no criteria"):
            CampaignStage(
                campaign_id=uuid.uuid4(),
                name="Triage",
                display_order=0,
                kind=StageKind.MANUAL,
                criteria=[StageCriterion(channel_id=uuid.uuid4(), operator="lt", value=10.0)],
            )

    def test_accepts_up_to_max_criteria(self) -> None:
        criteria = [
            StageCriterion(channel_id=uuid.uuid4(), operator="lt", value=float(i))
            for i in range(MAX_STAGE_CRITERIA)
        ]
        stage = CampaignStage(
            campaign_id=uuid.uuid4(), name="Stage", display_order=0, criteria=criteria
        )
        assert len(stage.criteria) == MAX_STAGE_CRITERIA

    def test_rejects_more_than_max_criteria(self) -> None:
        criteria = [
            StageCriterion(channel_id=uuid.uuid4(), operator="lt", value=float(i))
            for i in range(MAX_STAGE_CRITERIA + 1)
        ]
        with pytest.raises(ValidationError):
            CampaignStage(
                campaign_id=uuid.uuid4(), name="Stage", display_order=0, criteria=criteria
            )

    def test_criteria_default_is_independent_per_instance(self) -> None:
        # Guards against a mutable-default-argument bug (`criteria: list = []`
        # shared across instances instead of `field(default_factory=list)`).
        s1 = CampaignStage(campaign_id=uuid.uuid4(), name="A", display_order=0)
        s2 = CampaignStage(campaign_id=uuid.uuid4(), name="B", display_order=1)
        s1.criteria.append(StageCriterion(channel_id=uuid.uuid4(), operator="lt", value=1.0))
        assert s2.criteria == []


class TestStageOverride:
    def _make(self, **overrides: object) -> StageOverride:
        defaults: dict = dict(
            result_id=uuid.uuid4(),
            stage_id=uuid.uuid4(),
            forced_outcome=StageOutcome.HIT,
            reason="Confirmed by manual review",
            overridden_by=uuid.uuid4(),
            overridden_at=datetime.now(UTC),
        )
        defaults.update(overrides)
        return StageOverride(**defaults)

    def test_accepts_hit_and_miss(self) -> None:
        self._make(forced_outcome=StageOutcome.HIT)
        self._make(forced_outcome=StageOutcome.MISS)

    @pytest.mark.parametrize(
        "outcome",
        [StageOutcome.UNTESTED, StageOutcome.NOT_IN_STAGE, StageOutcome.PENDING],
    )
    def test_rejects_outcomes_other_than_hit_or_miss(self, outcome: StageOutcome) -> None:
        with pytest.raises(ValidationError):
            self._make(forced_outcome=outcome)

    def test_reason_is_stripped(self) -> None:
        override = self._make(reason="  looks real to me  ")
        assert override.reason == "looks real to me"

    def test_rejects_empty_reason(self) -> None:
        with pytest.raises(ValidationError):
            self._make(reason="   ")

    def test_is_frozen(self) -> None:
        override = self._make()
        with pytest.raises(Exception):
            override.reason = "changed"  # type: ignore[misc]


class TestUnset:
    def test_is_singleton(self) -> None:
        assert UNSET is _Unset()

    def test_repr(self) -> None:
        assert repr(UNSET) == "UNSET"
