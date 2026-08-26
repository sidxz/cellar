import uuid

import pytest

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.research_organization.events import (
    CampaignClosed,
    CampaignCreated,
    CampaignSuperseded,
)
from cellar.domain.research_organization.source_ref import CollectionRef
from cellar.domain.shared.errors import ValidationError


def _make_campaign(**overrides) -> Campaign:
    defaults = dict(
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="EGFR Round 2",
        description=None,
        publishes_collection=True,
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
    c.close(closed_by=uuid.uuid4(), signature_id=uuid.uuid4(), source_protocols=[])
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


# ---------- close ----------


def test_close_requires_at_least_one_result():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    with pytest.raises(ValidationError, match="no results"):
        c.close(
            closed_by=uuid.uuid4(),
            signature_id=uuid.uuid4(),
            source_protocols=[],
        )


def test_close_requires_at_least_one_channel():
    c = _make_campaign()
    c.add_result(_make_result(c))
    with pytest.raises(ValidationError, match="no channels"):
        c.close(
            closed_by=uuid.uuid4(),
            signature_id=uuid.uuid4(),
            source_protocols=[],
        )


def test_close_transitions_and_emits_event():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    c.add_result(_make_result(c))
    closer = uuid.uuid4()
    sig = uuid.uuid4()
    c.collect_events()  # clear CampaignCreated
    c.close(
        closed_by=closer,
        signature_id=sig,
        source_protocols=[{"id": "p1", "name": "X", "version": 1}],
    )
    assert c.status == CampaignStatus.CLOSED
    assert c.closed_by == closer
    assert c.signature_id == sig
    assert c.source_protocols == [{"id": "p1", "name": "X", "version": 1}]
    events = c.collect_events()
    assert any(isinstance(e, CampaignClosed) for e in events)


def test_cannot_mutate_after_close():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    c.add_result(_make_result(c))
    c.close(
        closed_by=uuid.uuid4(),
        signature_id=uuid.uuid4(),
        source_protocols=[],
    )
    with pytest.raises(ValidationError):
        c.add_channel(_make_channel(c))
    with pytest.raises(ValidationError):
        c.add_result(_make_result(c))
    with pytest.raises(ValidationError):
        c.remove_channel(uuid.uuid4())


# ---------- publish + supersede ----------


def test_set_published_collection_requires_closed():
    c = _make_campaign()
    with pytest.raises(ValidationError, match="closed campaigns"):
        c.set_published_collection(uuid.uuid4())


def test_supersede_requires_closed():
    c = _make_campaign()
    with pytest.raises(ValidationError, match="closed campaigns"):
        c.mark_superseded_by(uuid.uuid4())


def test_supersede_transitions_and_emits_event():
    c = _make_campaign()
    c.add_channel(_make_channel(c))
    c.add_result(_make_result(c))
    c.close(closed_by=uuid.uuid4(), signature_id=uuid.uuid4(), source_protocols=[])
    new_id = uuid.uuid4()
    c.collect_events()
    c.mark_superseded_by(new_id)
    assert c.status == CampaignStatus.SUPERSEDED
    assert c.superseded_by_campaign_id == new_id
    events = c.collect_events()
    assert any(isinstance(e, CampaignSuperseded) for e in events)

