import uuid

import pytest

from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import StageOverride
from cellar.domain.research_organization.enums import (
    CampaignDecision,
    StageOutcome,
    ValueQualifier,
)
from cellar.domain.shared.errors import ValidationError


def _make_measurement(
    result_id: uuid.UUID, channel_id: uuid.UUID | None = None
) -> CampaignMeasurement:
    return CampaignMeasurement(
        result_id=result_id,
        channel_id=channel_id or uuid.uuid4(),
        value=1.0,
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )


def test_default_decision_deferred():
    r = CampaignResult(
        campaign_id=uuid.uuid4(),
        molecule_id=uuid.uuid4(),
    )
    assert r.decision == CampaignDecision.DEFERRED
    assert r.measurements == []
    assert r.id is not None
    assert r.stage_overrides == {}


def test_add_measurement():
    r = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    m = _make_measurement(r.id)
    r.add_measurement(m)
    assert len(r.measurements) == 1


def test_set_decision_updates_field():
    r = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    r.set_decision(CampaignDecision.SELECTED, reason="Best in series")
    assert r.decision == CampaignDecision.SELECTED
    assert r.decision_reason == "Best in series"


def test_set_decision_without_reason_clears_existing_reason():
    r = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    r.set_decision(CampaignDecision.SELECTED, reason="One")
    r.set_decision(CampaignDecision.REJECTED)  # no reason -> None
    assert r.decision_reason is None


def test_reject_measurement_for_wrong_result():
    r = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    m = _make_measurement(uuid.uuid4())  # wrong result_id
    with pytest.raises(ValidationError):
        r.add_measurement(m)


def test_remove_measurement_for_channel():
    r = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    channel_id = uuid.uuid4()
    keep = _make_measurement(r.id)
    drop = _make_measurement(r.id, channel_id=channel_id)
    r.add_measurement(keep)
    r.add_measurement(drop)
    r.remove_measurement_for_channel(channel_id)
    assert r.measurements == [keep]


def test_find_measurement_by_channel():
    r = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    channel_id = uuid.uuid4()
    m = _make_measurement(r.id, channel_id=channel_id)
    r.add_measurement(m)
    assert r.find_measurement(channel_id) is m
    assert r.find_measurement(uuid.uuid4()) is None


# ---------- stage overrides ----------


def test_set_stage_override_creates_entry():
    r = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    stage_id = uuid.uuid4()
    user_id = uuid.uuid4()
    override = r.set_stage_override(
        stage_id=stage_id,
        forced_outcome=StageOutcome.HIT,
        reason="Confirmed active by chemist",
        overridden_by=user_id,
    )
    assert isinstance(override, StageOverride)
    assert override.result_id == r.id
    assert override.stage_id == stage_id
    assert override.forced_outcome == StageOutcome.HIT
    assert override.reason == "Confirmed active by chemist"
    assert override.overridden_by == user_id
    assert r.stage_overrides == {stage_id: override}


def test_set_stage_override_replaces_existing():
    r = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    stage_id = uuid.uuid4()
    r.set_stage_override(
        stage_id=stage_id,
        forced_outcome=StageOutcome.HIT,
        reason="first pass",
        overridden_by=uuid.uuid4(),
    )
    second = r.set_stage_override(
        stage_id=stage_id,
        forced_outcome=StageOutcome.MISS,
        reason="reversed on review",
        overridden_by=uuid.uuid4(),
    )
    assert len(r.stage_overrides) == 1
    assert r.stage_overrides[stage_id] is second
    assert r.stage_overrides[stage_id].forced_outcome == StageOutcome.MISS


def test_clear_stage_override_removes_and_returns_true():
    r = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    stage_id = uuid.uuid4()
    r.set_stage_override(
        stage_id=stage_id,
        forced_outcome=StageOutcome.HIT,
        reason="manual promote",
        overridden_by=uuid.uuid4(),
    )
    assert r.clear_stage_override(stage_id) is True
    assert stage_id not in r.stage_overrides


def test_clear_stage_override_missing_returns_false():
    r = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    assert r.clear_stage_override(uuid.uuid4()) is False
