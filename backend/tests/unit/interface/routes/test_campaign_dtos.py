"""Unit tests for the campaign interface-DTO projections (_campaign_dtos)."""

from __future__ import annotations

import uuid

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import CampaignStage, StageCriterion
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    StageKind,
    ValueQualifier,
)
from cellar.domain.research_organization.source_ref import (
    CollectionRef,
    RunRef,
)
from cellar.interface.routes._campaign_dtos import (
    CampaignResponse,
    CampaignSummaryResponse,
    StageCheckResponse,
    _derive_compound_sources,
)


def _result(campaign_id: uuid.UUID, added_from) -> CampaignResult:
    return CampaignResult(
        campaign_id=campaign_id,
        molecule_id=uuid.uuid4(),
        added_from=added_from,
    )


class TestDeriveCompoundSources:
    def test_two_runs_no_description_stay_distinct(self) -> None:
        """Two runs with description=None must group by run_id, not collapse.

        Reproduces the production bug: the add-run wizard records a RunRef
        with description=None, so two distinct runs were merged into one
        ("run", None) bucket — losing the second source row.
        """
        campaign_id = uuid.uuid4()
        run_a = uuid.uuid4()
        run_b = uuid.uuid4()
        results = [
            _result(campaign_id, RunRef(run_id=run_a)),
            _result(campaign_id, RunRef(run_id=run_b)),
            _result(campaign_id, RunRef(run_id=run_b)),
        ]

        sources = _derive_compound_sources(results)

        assert len(sources) == 2
        by_run = {s["run_id"]: s["count"] for s in sources}
        assert by_run == {str(run_a): 1, str(run_b): 2}

    def test_same_run_groups_into_one(self) -> None:
        campaign_id = uuid.uuid4()
        run = uuid.uuid4()
        results = [
            _result(campaign_id, RunRef(run_id=run)),
            _result(campaign_id, RunRef(run_id=run)),
        ]

        sources = _derive_compound_sources(results)

        assert len(sources) == 1
        assert sources[0]["run_id"] == str(run)
        assert sources[0]["count"] == 2

    def test_two_collections_no_description_stay_distinct(self) -> None:
        campaign_id = uuid.uuid4()
        coll_a = uuid.uuid4()
        coll_b = uuid.uuid4()
        results = [
            _result(campaign_id, CollectionRef(collection_id=coll_a)),
            _result(campaign_id, CollectionRef(collection_id=coll_b)),
        ]

        sources = _derive_compound_sources(results)

        assert len(sources) == 2
        by_coll = {s["collection_id"]: s["count"] for s in sources}
        assert by_coll == {str(coll_a): 1, str(coll_b): 1}

    def test_all_manual_group_into_one(self) -> None:
        campaign_id = uuid.uuid4()
        results = [
            _result(campaign_id, None),
            _result(campaign_id, None),
            _result(campaign_id, None),
        ]

        sources = _derive_compound_sources(results)

        assert len(sources) == 1
        assert sources[0]["kind"] == "manual"
        assert sources[0]["count"] == 3


def _make_campaign_with_chained_stages() -> tuple[Campaign, uuid.UUID]:
    """Two chained stages over one channel: A (root) gated on <= 10,
    B (parent A) gated on < 1 — same channel, a tighter cut, exactly as
    the spec's "same IC50 with a tighter cut" example allows. Returns
    (campaign, channel_id) with one result whose measurement (5.0)
    passes A (hit) and fails B (miss)."""
    campaign = Campaign(
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        name="Campaign",
        status=CampaignStatus.DRAFT,
        created_by=uuid.uuid4(),
    )
    channel = CampaignChannel(
        campaign_id=campaign.id,
        label="IC50",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    campaign.add_channel(channel)

    stage_a = CampaignStage(
        campaign_id=campaign.id,
        name="Stage A",
        display_order=0,
        criteria=[StageCriterion(channel_id=channel.id, operator="lte", value=10.0)],
    )
    campaign.add_stage(stage_a)
    stage_b = CampaignStage(
        campaign_id=campaign.id,
        name="Stage B",
        display_order=1,
        parent_stage_id=stage_a.id,
        criteria=[StageCriterion(channel_id=channel.id, operator="lt", value=1.0)],
    )
    campaign.add_stage(stage_b)

    result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
    result.add_measurement(
        CampaignMeasurement(
            result_id=result.id,
            channel_id=channel.id,
            value=5.0,
            value_qualifier=ValueQualifier.EQ,
            unit="uM",
            protocol_name_snapshot="IC50 Proto",
            protocol_version_snapshot=1,
        )
    )
    campaign.add_result(result)
    return campaign, channel.id


class TestCampaignResponseStageOutcomes:
    def test_from_domain_orders_stage_outcomes_like_campaign_stages_with_checks(self) -> None:
        campaign, channel_id = _make_campaign_with_chained_stages()

        response = CampaignResponse.from_domain(campaign)

        assert len(response.results) == 1
        outcomes = response.results[0].stage_outcomes
        assert [o.stage_id for o in outcomes] == [s.id for s in campaign.stages]

        stage_a_outcome, stage_b_outcome = outcomes
        assert stage_a_outcome.outcome == "hit"
        assert stage_a_outcome.overridden is False
        assert stage_a_outcome.checks == [
            StageCheckResponse(channel_id=channel_id, verdict="pass")
        ]

        assert stage_b_outcome.outcome == "miss"
        assert stage_b_outcome.checks == [
            StageCheckResponse(channel_id=channel_id, verdict="fail")
        ]

    def test_from_domain_carries_stage_kind_and_pending_outcome(self) -> None:
        campaign, _channel_id = _make_campaign_with_chained_stages()
        manual = CampaignStage(
            campaign_id=campaign.id,
            name="Manual Triage",
            display_order=2,
            kind=StageKind.MANUAL,
        )
        campaign.add_stage(manual)

        response = CampaignResponse.from_domain(campaign)

        kinds = {s.name: s.kind for s in response.stages}
        assert kinds == {"Stage A": "criteria", "Stage B": "criteria", "Manual Triage": "manual"}
        manual_outcome = next(
            o for o in response.results[0].stage_outcomes if o.stage_id == manual.id
        )
        assert manual_outcome.outcome == "pending"
        assert manual_outcome.checks == []


class TestStageCounts:
    """Stage funnel counts ride along on every stage projection."""

    def test_counts_present_on_each_stage_with_seven_buckets(self) -> None:
        campaign, _channel_id = _make_campaign_with_chained_stages()

        response = CampaignResponse.from_domain(campaign)

        by_name = {s.name: s.counts for s in response.stages}
        assert set(by_name) == {"Stage A", "Stage B"}
        assert set(by_name["Stage A"].model_dump()) == {
            "population",
            "hit",
            "miss",
            "untested",
            "pending",
            "not_in_stage",
            "overridden",
        }
        # The single result is a hit on A (root: everyone is in the stage)
        # and a miss on its child B.
        assert by_name["Stage A"].model_dump() == {
            "population": 1,
            "hit": 1,
            "miss": 0,
            "untested": 0,
            "pending": 0,
            "not_in_stage": 0,
            "overridden": 0,
        }
        assert by_name["Stage B"].population == 1
        assert by_name["Stage B"].miss == 1

    def test_child_stage_counts_not_in_stage_when_parent_misses(self) -> None:
        campaign, _channel_id = _make_campaign_with_chained_stages()
        # Push the only measurement past Stage A's <= 10 cut so the result
        # never enters Stage B.
        campaign.results[0].measurements[0].value = 50.0

        stages = {s.name: s.counts for s in CampaignResponse.from_domain(campaign).stages}

        assert stages["Stage A"].miss == 1
        assert stages["Stage B"].population == 0
        assert stages["Stage B"].not_in_stage == 1


class TestCampaignSummaryResponse:
    def test_summary_drops_results_and_counts_them(self) -> None:
        campaign, _channel_id = _make_campaign_with_chained_stages()

        summary = CampaignSummaryResponse.from_domain(campaign)

        assert "results" not in summary.model_dump()
        assert summary.result_count == len(campaign.results) == 1

    def test_summary_matches_the_full_read_on_every_shared_field(self) -> None:
        campaign, _channel_id = _make_campaign_with_chained_stages()

        full = CampaignResponse.from_domain(campaign).model_dump()
        summary = CampaignSummaryResponse.from_domain(campaign).model_dump()

        assert set(full) - set(summary) == {"results"}
        assert set(summary) - set(full) == {"result_count"}
        for field in set(summary) - {"result_count"}:
            assert summary[field] == full[field], field


class TestChannelOrdering:
    def test_channels_tied_on_display_order_come_back_in_id_order(self) -> None:
        """A failed second PATCH in the reorder swap leaves two channels on the
        same display_order; the projection must still be deterministic."""
        campaign, _channel_id = _make_campaign_with_chained_stages()
        tied = sorted(
            (uuid.UUID(int=2), uuid.UUID(int=1)),
            reverse=True,  # added high id first, so a display_order-only sort keeps it first
        )
        for channel_id in tied:
            campaign.add_channel(
                CampaignChannel(
                    id=channel_id,
                    campaign_id=campaign.id,
                    label=f"Tied {channel_id.int}",
                    protocol_id=uuid.uuid4(),
                    readout_definition_id=uuid.uuid4(),
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
                    display_order=7,
                )
            )

        response = CampaignResponse.from_domain(campaign)

        assert [c.id for c in response.channels if c.display_order == 7] == sorted(tied)
