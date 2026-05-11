from chem_vault.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    CampaignDecision,
    HitCall,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)


def test_campaign_status_values():
    assert CampaignStatus.DRAFT.value == "draft"
    assert CampaignStatus.CLOSED.value == "closed"
    assert CampaignStatus.SUPERSEDED.value == "superseded"


def test_selection_rule_members():
    assert {r.value for r in SelectionRule} == {
        "latest_approved_run",
        "mean_across_runs",
        "geometric_mean",
        "manual_pick",
    }


def test_value_qualifier_members():
    assert {q.value for q in ValueQualifier} == {"=", "<", ">", "nd", "excluded"}


def test_hit_call_members():
    assert {h.value for h in HitCall} == {"hit", "miss", "inconclusive"}


def test_decision_members():
    assert {d.value for d in CampaignDecision} == {"selected", "deferred", "rejected"}


def test_channel_source_kind_members():
    assert {k.value for k in ChannelSourceKind} == {"readout_data", "dose_response_curve"}


def test_qualifier_handling_members():
    assert {q.value for q in QualifierHandling} == {
        "include_qualified",
        "exclude_qualified",
        "treat_as_limit",
    }
