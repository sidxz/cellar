import uuid

import pytest

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import (
    CampaignStage,
    StageCriterion,
)
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    StageKind,
    StageOutcome,
    ValueQualifier,
)
from cellar.domain.research_organization.events import (
    CampaignClosed,
    CampaignCreated,
    CampaignReopened,
    CampaignSuperseded,
)
from cellar.domain.research_organization.source_ref import (
    CollectionRef,
    RunRef,
    SeedRun,
)
from cellar.domain.shared.errors import ConflictError, NotFoundError, ValidationError


def _make_campaign(**overrides) -> Campaign:
    defaults = dict(
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="EGFR Round 2",
        description=None,
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    return Campaign.create(**defaults)


def _make_channel(campaign: Campaign) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=campaign.id,
        label="IC50",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )


def _make_result(campaign: Campaign, molecule_id: uuid.UUID | None = None) -> CampaignResult:
    return CampaignResult(
        campaign_id=campaign.id,
        molecule_id=molecule_id or uuid.uuid4(),
    )


def _make_stage(campaign: Campaign, **overrides) -> CampaignStage:
    defaults = dict(
        campaign_id=campaign.id,
        name="Screening Hits",
        display_order=0,
    )
    defaults.update(overrides)
    return CampaignStage(**defaults)


# ---------- creation ----------


def test_create_registers_event():
    c = _make_campaign()
    events = c.collect_events()
    assert any(isinstance(e, CampaignCreated) for e in events)
    assert c.status == CampaignStatus.DRAFT


def test_create_rejects_empty_name():
    with pytest.raises(ValidationError):
        _make_campaign(name="   ")


def test_create_strips_name():
    c = _make_campaign(name="  My Campaign  ")
    assert c.name == "My Campaign"


def test_create_starts_empty():
    c = _make_campaign()
    assert c.results == []
    assert c.channels == []
    assert c.stages == []


# ---------- channels ----------


def test_add_channel_appends():
    c = _make_campaign()
    ch = _make_channel(c)
    c.add_channel(ch)
    assert ch in c.channels


def test_add_channel_rejects_mismatched_campaign_id():
    c = _make_campaign()
    bogus_channel = CampaignChannel(
        campaign_id=uuid.uuid4(),  # not c.id
        label="x",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    with pytest.raises(ValidationError, match="campaign_id"):
        c.add_channel(bogus_channel)


def test_remove_channel_drops_channel_and_its_measurements():
    c = _make_campaign()
    ch = _make_channel(c)
    c.add_channel(ch)
    r = _make_result(c)
    c.add_result(r)
    m = CampaignMeasurement(
        result_id=r.id,
        channel_id=ch.id,
        value=1.0,
        value_qualifier=ValueQualifier.EQ,
        unit="nM",
        protocol_name_snapshot="x",
        protocol_version_snapshot=1,
    )
    r.add_measurement(m)
    c.remove_channel(ch.id)
    assert ch not in c.channels
    assert r.measurements == []


# ---------- results — single add ----------


def test_add_result_rejects_duplicate_molecule():
    c = _make_campaign()
    mol = uuid.uuid4()
    c.add_result(_make_result(c, molecule_id=mol))
    with pytest.raises(ValidationError, match="already contains"):
        c.add_result(_make_result(c, molecule_id=mol))


# ---------- results — bulk add_results ----------


def test_add_results_happy_path():
    c = _make_campaign()
    mols = [uuid.uuid4() for _ in range(5)]
    new_results = [CampaignResult(campaign_id=c.id, molecule_id=m) for m in mols]
    added, skipped = c.add_results(new_results)
    assert added == 5
    assert skipped == 0
    assert len(c.results) == 5


def test_add_results_idempotent_dedupe():
    c = _make_campaign()
    mol_a, mol_b, mol_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    c.add_result(CampaignResult(campaign_id=c.id, molecule_id=mol_a))
    c.add_result(CampaignResult(campaign_id=c.id, molecule_id=mol_b))
    # mol_a and mol_b already in campaign; mol_c is new
    new_results = [
        CampaignResult(campaign_id=c.id, molecule_id=mol_a),
        CampaignResult(campaign_id=c.id, molecule_id=mol_b),
        CampaignResult(campaign_id=c.id, molecule_id=mol_c),
    ]
    added, skipped = c.add_results(new_results)
    assert added == 1
    assert skipped == 2
    assert len(c.results) == 3


def test_add_results_dedupe_within_batch():
    c = _make_campaign()
    mol = uuid.uuid4()
    # Same molecule twice in the input list — should be added once
    new_results = [
        CampaignResult(campaign_id=c.id, molecule_id=mol),
        CampaignResult(campaign_id=c.id, molecule_id=mol),
    ]
    added, skipped = c.add_results(new_results)
    assert added == 1
    assert skipped == 1
    assert len(c.results) == 1


def test_add_results_rejects_mismatched_campaign_id():
    c = _make_campaign()
    bad = CampaignResult(campaign_id=uuid.uuid4(), molecule_id=uuid.uuid4())
    with pytest.raises(ValidationError, match="campaign_id mismatch"):
        c.add_results([bad])


def test_add_results_draft_guard():
    c = _make_campaign()
    ch = _make_channel(c)
    c.add_channel(ch)
    c.add_result(_make_result(c))
    c.close(closed_by=uuid.uuid4(), note=None, source_protocols=[])
    with pytest.raises(ValidationError):
        c.add_results([_make_result(c)])


def test_add_results_carries_source_ref():
    c = _make_campaign()
    coll_id = uuid.uuid4()
    ref = CollectionRef(collection_id=coll_id)
    r = CampaignResult(campaign_id=c.id, molecule_id=uuid.uuid4(), added_from=ref)
    c.add_results([r])
    assert c.results[0].added_from is ref


def test_add_results_empty_list_returns_zero_zero():
    c = _make_campaign()
    added, skipped = c.add_results([])
    assert added == 0
    assert skipped == 0


# ---------- stages ----------


def test_find_stage_returns_none_when_missing():
    c = _make_campaign()
    assert c.find_stage(uuid.uuid4()) is None


def test_add_stage_appends():
    c = _make_campaign()
    stage = _make_stage(c)
    c.add_stage(stage)
    assert stage in c.stages
    assert c.find_stage(stage.id) is stage


def test_add_stage_rejects_mismatched_campaign_id():
    c = _make_campaign()
    bogus_stage = CampaignStage(campaign_id=uuid.uuid4(), name="x", display_order=0)
    with pytest.raises(ValidationError, match="campaign_id"):
        c.add_stage(bogus_stage)


def test_add_stage_rejects_duplicate_id():
    c = _make_campaign()
    stage = _make_stage(c)
    c.add_stage(stage)
    dup = _make_stage(c, id=stage.id, name="Different Name", display_order=1)
    with pytest.raises(ValidationError, match="already on campaign"):
        c.add_stage(dup)


def test_add_stage_rejects_duplicate_name_case_insensitive():
    c = _make_campaign()
    c.add_stage(_make_stage(c, name="Screening Hits", display_order=0))
    with pytest.raises(ValidationError, match="already used"):
        c.add_stage(_make_stage(c, name="screening hits", display_order=1))


def test_add_stage_rejects_unknown_channel_in_criteria():
    c = _make_campaign()
    criterion = StageCriterion(channel_id=uuid.uuid4(), operator="gte", value=50.0)
    stage = _make_stage(c, criteria=[criterion])
    with pytest.raises(ValidationError, match="not a channel"):
        c.add_stage(stage)


def test_add_stage_rejects_missing_parent():
    c = _make_campaign()
    stage = _make_stage(c, parent_stage_id=uuid.uuid4())
    with pytest.raises(ValidationError, match="parent"):
        c.add_stage(stage)


def test_add_stage_rejects_self_parent():
    c = _make_campaign()
    stage_id = uuid.uuid4()
    stage = _make_stage(c, id=stage_id, parent_stage_id=stage_id)
    with pytest.raises(ValidationError, match="own parent"):
        c.add_stage(stage)


def test_add_stage_draft_guard():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    c.add_result(_make_result(c))
    c.close(closed_by=uuid.uuid4(), note=None, source_protocols=[])
    with pytest.raises(ValidationError):
        c.add_stage(_make_stage(c))


def test_update_stage_missing_raises_not_found():
    c = _make_campaign()
    with pytest.raises(NotFoundError):
        c.update_stage(uuid.uuid4(), name="X")


def test_update_stage_replaces_criteria_whole():
    c = _make_campaign()
    ch = _make_channel(c)
    c.add_channel(ch)
    stage = _make_stage(c, criteria=[StageCriterion(channel_id=ch.id, operator="gte", value=50.0)])
    c.add_stage(stage)
    new_criteria = [StageCriterion(channel_id=ch.id, operator="lt", value=10.0)]
    updated = c.update_stage(stage.id, criteria=new_criteria)
    assert updated is stage
    assert updated.criteria == new_criteria


def test_update_stage_to_manual_rejects_existing_criteria():
    c = _make_campaign()
    ch = _make_channel(c)
    c.add_channel(ch)
    stage = _make_stage(c, criteria=[StageCriterion(channel_id=ch.id, operator="gte", value=50.0)])
    c.add_stage(stage)
    with pytest.raises(ValidationError, match="manual stage has no criteria"):
        c.update_stage(stage.id, kind=StageKind.MANUAL)
    assert stage.kind == StageKind.CRITERIA


def test_update_stage_to_manual_with_cleared_criteria():
    c = _make_campaign()
    ch = _make_channel(c)
    c.add_channel(ch)
    stage = _make_stage(c, criteria=[StageCriterion(channel_id=ch.id, operator="gte", value=50.0)])
    c.add_stage(stage)
    updated = c.update_stage(stage.id, kind=StageKind.MANUAL, criteria=[])
    assert updated.kind == StageKind.MANUAL
    assert updated.criteria == []


def test_update_stage_leaves_kind_alone_when_unset():
    c = _make_campaign()
    stage = _make_stage(c, kind=StageKind.MANUAL)
    c.add_stage(stage)
    updated = c.update_stage(stage.id, name="Renamed")
    assert updated.kind == StageKind.MANUAL


def test_update_stage_rejects_duplicate_name():
    c = _make_campaign()
    c.add_stage(_make_stage(c, name="Screening Hits", display_order=0))
    other = _make_stage(c, name="Confirmed Hits", display_order=1)
    c.add_stage(other)
    with pytest.raises(ValidationError, match="already used"):
        c.update_stage(other.id, name="screening hits")


def test_update_stage_rejects_cycle():
    c = _make_campaign()
    a = _make_stage(c, name="A", display_order=0)
    c.add_stage(a)
    b = _make_stage(c, name="B", display_order=1, parent_stage_id=a.id)
    c.add_stage(b)
    with pytest.raises(ValidationError, match="cycle"):
        c.update_stage(a.id, parent_stage_id=b.id)


def test_update_stage_draft_guard():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    c.add_result(_make_result(c))
    stage = _make_stage(c)
    c.add_stage(stage)
    c.close(closed_by=uuid.uuid4(), note=None, source_protocols=[])
    with pytest.raises(ValidationError):
        c.update_stage(stage.id, name="Renamed")


def test_remove_stage_missing_raises_not_found():
    c = _make_campaign()
    with pytest.raises(NotFoundError):
        c.remove_stage(uuid.uuid4())


def test_remove_stage_rejects_when_children_exist():
    c = _make_campaign()
    parent = _make_stage(c, name="Parent", display_order=0)
    c.add_stage(parent)
    child = _make_stage(c, name="Child", display_order=1, parent_stage_id=parent.id)
    c.add_stage(child)
    with pytest.raises(ConflictError):
        c.remove_stage(parent.id)


def test_remove_stage_clears_overrides_on_results():
    c = _make_campaign()
    stage = _make_stage(c)
    c.add_stage(stage)
    r = _make_result(c)
    c.add_result(r)
    r.set_stage_override(
        stage_id=stage.id,
        forced_outcome=StageOutcome.HIT,
        reason="manual",
        overridden_by=uuid.uuid4(),
    )
    c.remove_stage(stage.id)
    assert stage not in c.stages
    assert stage.id not in r.stage_overrides


def test_remove_stage_draft_guard():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    c.add_result(_make_result(c))
    stage = _make_stage(c)
    c.add_stage(stage)
    c.close(closed_by=uuid.uuid4(), note=None, source_protocols=[])
    with pytest.raises(ValidationError):
        c.remove_stage(stage.id)


def test_remove_channel_strips_stage_criteria_referencing_it():
    c = _make_campaign()
    ch1 = _make_channel(c)
    c.add_channel(ch1)
    ch2 = _make_channel(c)
    c.add_channel(ch2)
    mixed_stage = _make_stage(
        c,
        name="Mixed",
        criteria=[
            StageCriterion(channel_id=ch1.id, operator="gte", value=50.0),
            StageCriterion(channel_id=ch2.id, operator="lt", value=10.0),
        ],
    )
    c.add_stage(mixed_stage)
    other_stage = _make_stage(
        c,
        name="Other",
        display_order=1,
        criteria=[StageCriterion(channel_id=ch2.id, operator="gte", value=1.0)],
    )
    c.add_stage(other_stage)

    c.remove_channel(ch1.id)

    assert [crit.channel_id for crit in mixed_stage.criteria] == [ch2.id]
    assert [crit.channel_id for crit in other_stage.criteria] == [ch2.id]


# ---------- close ----------


def test_close_requires_at_least_one_result():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    with pytest.raises(ValidationError, match="no results"):
        c.close(
            closed_by=uuid.uuid4(),
            note=None,
            source_protocols=[],
        )


def test_close_requires_at_least_one_channel():
    c = _make_campaign()
    c.add_result(_make_result(c))
    with pytest.raises(ValidationError, match="no channels"):
        c.close(
            closed_by=uuid.uuid4(),
            note=None,
            source_protocols=[],
        )


def test_close_transitions_and_emits_event():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    c.add_result(_make_result(c))
    closer = uuid.uuid4()
    c.collect_events()  # clear CampaignCreated
    c.close(
        closed_by=closer,
        note="Confirmed by wet lab",
        source_protocols=[{"id": "p1", "name": "X", "version": 1}],
    )
    assert c.status == CampaignStatus.CLOSED
    assert c.closed_by == closer
    assert c.close_note == "Confirmed by wet lab"
    assert c.source_protocols == [{"id": "p1", "name": "X", "version": 1}]
    events = c.collect_events()
    closed_events = [e for e in events if isinstance(e, CampaignClosed)]
    assert len(closed_events) == 1
    assert closed_events[0].note == "Confirmed by wet lab"


def test_close_with_no_note_leaves_close_note_none():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    c.add_result(_make_result(c))
    c.close(closed_by=uuid.uuid4(), note=None, source_protocols=[])
    assert c.close_note is None


def test_cannot_mutate_after_close():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    c.add_result(_make_result(c))
    c.close(
        closed_by=uuid.uuid4(),
        note=None,
        source_protocols=[],
    )
    with pytest.raises(ValidationError):
        c.add_channel(_make_channel(c))
    with pytest.raises(ValidationError):
        c.add_result(_make_result(c))
    with pytest.raises(ValidationError):
        c.remove_channel(uuid.uuid4())


# ---------- reopen ----------


def test_reopen_from_closed_clears_metadata_and_emits_event():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    c.add_result(_make_result(c))
    c.close(closed_by=uuid.uuid4(), note="first pass", source_protocols=[])
    c.collect_events()  # clear CampaignClosed
    reopener = uuid.uuid4()
    c.reopen(reopened_by=reopener, reason="late confirmation result")
    assert c.status == CampaignStatus.DRAFT
    assert c.closed_at is None
    assert c.closed_by is None
    assert c.close_note is None
    events = c.collect_events()
    reopened_events = [e for e in events if isinstance(e, CampaignReopened)]
    assert len(reopened_events) == 1
    assert reopened_events[0].reopened_by == reopener
    assert reopened_events[0].reason == "late confirmation result"


def test_reopen_refused_from_draft():
    c = _make_campaign()
    with pytest.raises(ValidationError, match="draft"):
        c.reopen(reopened_by=uuid.uuid4(), reason="oops")


def test_reopen_refused_from_superseded():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    c.add_result(_make_result(c))
    c.close(closed_by=uuid.uuid4(), note=None, source_protocols=[])
    c.mark_superseded_by(uuid.uuid4())
    with pytest.raises(ValidationError, match="superseded"):
        c.reopen(reopened_by=uuid.uuid4(), reason="oops")


def test_reopen_rejects_empty_reason():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    c.add_result(_make_result(c))
    c.close(closed_by=uuid.uuid4(), note=None, source_protocols=[])
    with pytest.raises(ValidationError, match="reason"):
        c.reopen(reopened_by=uuid.uuid4(), reason="   ")


# ---------- supersede ----------


def test_supersede_requires_closed():
    c = _make_campaign()
    with pytest.raises(ValidationError, match="closed campaigns"):
        c.mark_superseded_by(uuid.uuid4())


def test_supersede_transitions_and_emits_event():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    c.add_result(_make_result(c))
    c.close(closed_by=uuid.uuid4(), note=None, source_protocols=[])
    new_id = uuid.uuid4()
    c.collect_events()
    c.mark_superseded_by(new_id)
    assert c.status == CampaignStatus.SUPERSEDED
    assert c.superseded_by_campaign_id == new_id
    events = c.collect_events()
    assert any(isinstance(e, CampaignSuperseded) for e in events)


# ---------------------------------------------------------------------------
# seed runs — the campaign's resolution run scope (spec D4)
# ---------------------------------------------------------------------------


def test_record_seed_runs_appends_in_order_and_ignores_repeats():
    c = _make_campaign()
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    run_a, run_b, run_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    c.record_seed_runs([SeedRun(run_b, p1), SeedRun(run_a, p1)])
    c.record_seed_runs([SeedRun(run_a, p1), SeedRun(run_c, p2), SeedRun(run_b, p1)])
    assert c.seed_runs == [SeedRun(run_b, p1), SeedRun(run_a, p1), SeedRun(run_c, p2)]


def test_seed_run_ids_for_filters_by_protocol_in_insertion_order():
    c = _make_campaign()
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    run_a, run_b, run_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    c.record_seed_runs([SeedRun(run_b, p1), SeedRun(run_c, p2), SeedRun(run_a, p1)])
    assert c.seed_run_ids_for(p1) == [run_b, run_a]
    assert c.seed_run_ids_for(p2) == [run_c]
    assert c.seed_run_ids_for(uuid.uuid4()) == []


def test_seed_runs_are_not_derived_from_run_refs():
    """A RunRef names only the run that won a pick, so rows alone never widen
    the scope — only record_seed_runs does."""
    c = _make_campaign()
    c.add_result(
        CampaignResult(campaign_id=c.id, molecule_id=uuid.uuid4(), added_from=RunRef(run_id=uuid.uuid4()))
    )
    assert c.seed_runs == []


def test_record_seed_runs_is_draft_only():
    c = _make_campaign()
    c.status = CampaignStatus.CLOSED
    with pytest.raises(ValidationError, match="record seed runs"):
        c.record_seed_runs([SeedRun(uuid.uuid4(), uuid.uuid4())])
    assert c.seed_runs == []
