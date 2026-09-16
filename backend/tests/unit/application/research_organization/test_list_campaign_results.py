"""Unit tests for the ListCampaignResults query.

The filter runs on the verdict a chemist sees — after overrides — and the
ordering follows the chemist's reading of a screening column: a measured
number is comparable, a censored one only loosely, an ND not at all.
"""

from __future__ import annotations

import uuid

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.list_campaign_results import (
    ListCampaignResults,
    ListCampaignResultsQuery,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import CampaignStage, StageCriterion
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    StageKind,
    StageOutcome,
)
from cellar.domain.research_organization.stage_evaluation import (
    evaluate_stages,
    tally_stage_counts,
)
from cellar.domain.shared.aggregation_types import (
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ValidationError
from tests.unit.application.research_organization._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)

# ---------------------------------------------------------------------------
# Fixture campaign: one channel, one stage ("value < 10"), four compounds —
# a hit, a miss, an untested (ND) and a censored value.
# ---------------------------------------------------------------------------


def _measurement(
    result_id: uuid.UUID,
    channel_id: uuid.UUID,
    value: float | None,
    qualifier: ValueQualifier = ValueQualifier.EQ,
) -> CampaignMeasurement:
    return CampaignMeasurement(
        result_id=result_id,
        channel_id=channel_id,
        value=value,
        value_qualifier=qualifier,
        unit="uM",
        protocol_name_snapshot="Proto A",
        protocol_version_snapshot=1,
    )


def _campaign(workspace_id: uuid.UUID) -> tuple[Campaign, CampaignChannel, CampaignStage]:
    campaign = Campaign(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Primary",
        status=CampaignStatus.DRAFT,
        created_by=uuid.uuid4(),
    )
    channel = CampaignChannel(
        campaign_id=campaign.id,
        label="Resazurin IC50",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    campaign.add_channel(channel)

    stage = CampaignStage(
        campaign_id=campaign.id,
        name="Primary Hit",
        display_order=0,
        criteria=[StageCriterion(channel_id=channel.id, operator="lt", value=10.0)],
    )
    campaign.add_stage(stage)

    # (value, qualifier) per compound, in add order.
    cells: list[tuple[float | None, ValueQualifier]] = [
        (2.0, ValueQualifier.EQ),  # hit
        (50.0, ValueQualifier.EQ),  # miss
        (None, ValueQualifier.ND),  # untested
        (5.0, ValueQualifier.LT),  # censored — "< 5" proves "< 10"
    ]
    for value, qualifier in cells:
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        result.add_measurement(_measurement(result.id, channel.id, value, qualifier))
        campaign.add_result(result)

    campaign.clear_events()
    return campaign, channel, stage


def _use_case(campaign: Campaign) -> ListCampaignResults:
    return ListCampaignResults(
        uow=FakeUnitOfWork(), campaign_repo=make_campaign_repo(find_in_ws=campaign)
    )


async def _run(campaign: Campaign, auth, **kwargs):
    query = ListCampaignResultsQuery(
        workspace_id=auth.workspace_id, campaign_id=campaign.id, **kwargs
    )
    return await _use_case(campaign)(query, auth=auth)


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_every_row_with_its_outcomes_by_default():
    auth = fake_auth(role="viewer")
    campaign, _, stage = _campaign(auth.workspace_id)

    result = await _run(campaign, auth)

    assert isinstance(result, Success)
    out = result.unwrap()
    assert len(out.page.items) == 4
    assert out.page.total_count == 4
    assert out.page.next_cursor is None
    # Outcomes come back for the page's rows, keyed the way the row DTO reads them.
    assert set(out.outcomes) == {r.id for r in out.page.items}
    assert out.outcomes[out.page.items[0].id][stage.id].outcome == StageOutcome.HIT


@pytest.mark.asyncio
async def test_filters_on_the_stage_verdict():
    auth = fake_auth(role="viewer")
    campaign, _, stage = _campaign(auth.workspace_id)

    hits = (await _run(campaign, auth, stage_id=stage.id, outcome=(StageOutcome.HIT,))).unwrap()
    misses = (await _run(campaign, auth, stage_id=stage.id, outcome=(StageOutcome.MISS,))).unwrap()
    untested = (
        await _run(campaign, auth, stage_id=stage.id, outcome=(StageOutcome.UNTESTED,))
    ).unwrap()

    # "< 5" proves "< 10", so it is a hit like any other.
    assert hits.page.total_count == 2
    assert misses.page.total_count == 1
    assert untested.page.total_count == 1
    assert len(hits.page.items) == 2


@pytest.mark.asyncio
async def test_filters_on_the_outcome_after_an_override():
    auth = fake_auth(role="viewer")
    campaign, _, stage = _campaign(auth.workspace_id)
    # The chemist demotes the compound that passed on value.
    campaign.results[0].set_stage_override(
        stage_id=stage.id,
        forced_outcome=StageOutcome.MISS,
        reason="Precipitated in the plate",
        overridden_by=auth.user_id,
    )

    hits = (await _run(campaign, auth, stage_id=stage.id, outcome=(StageOutcome.HIT,))).unwrap()
    misses = (await _run(campaign, auth, stage_id=stage.id, outcome=(StageOutcome.MISS,))).unwrap()

    assert [r.id for r in hits.page.items] == [campaign.results[3].id]
    assert campaign.results[0].id in {r.id for r in misses.page.items}
    # ...and the page says who did it.
    demoted = misses.outcomes[campaign.results[0].id][stage.id]
    assert demoted.overridden is True
    assert demoted.overridden_by == auth.user_id
    assert demoted.overridden_at is not None


# ---------------------------------------------------------------------------
# A repeated `outcome` keeps a row whose verdict is any of the values. That is
# how a consumer asks for "every compound in this stage": hit + miss +
# untested + pending is exactly the stage's population in the summary read,
# and no single value expresses it on a child stage.
# ---------------------------------------------------------------------------

EVERY_OUTCOME = (
    StageOutcome.HIT,
    StageOutcome.MISS,
    StageOutcome.UNTESTED,
    StageOutcome.PENDING,
)


def _confirmation_stage(campaign: Campaign, parent: CampaignStage) -> CampaignStage:
    """A child stage on a second channel, so its population splits into an
    untested and a hit rather than just echoing the parent's verdicts."""
    channel = CampaignChannel(
        campaign_id=campaign.id,
        label="Confirmation IC50",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=1,
    )
    campaign.add_channel(channel)
    stage = CampaignStage(
        campaign_id=campaign.id,
        name="Confirmation",
        display_order=1,
        parent_stage_id=parent.id,
        criteria=[StageCriterion(channel_id=channel.id, operator="lt", value=3.0)],
    )
    campaign.add_stage(stage)
    # Only the parent's hits are in this stage's population: the first was
    # never run on the confirmation channel, the last clears it.
    hit_never_run, _, _, hit_confirmed = campaign.results
    hit_never_run.add_measurement(
        _measurement(hit_never_run.id, channel.id, None, ValueQualifier.ND)
    )
    hit_confirmed.add_measurement(_measurement(hit_confirmed.id, channel.id, 1.0))
    return stage


@pytest.mark.asyncio
async def test_repeated_outcome_returns_the_whole_stage_population():
    auth = fake_auth(role="viewer")
    campaign, _, root = _campaign(auth.workspace_id)
    child = _confirmation_stage(campaign, root)
    in_stage = {campaign.results[0].id, campaign.results[3].id}

    out = (await _run(campaign, auth, stage_id=child.id, outcome=EVERY_OUTCOME)).unwrap()

    # The parent's two hits — one untested here, one confirmed — and neither
    # of the two rows the parent dropped.
    assert {r.id for r in out.page.items} == in_stage
    assert {out.outcomes[r.id][child.id].outcome for r in out.page.items} == {
        StageOutcome.UNTESTED,
        StageOutcome.HIT,
    }
    # ...which is what the funnel read calls this stage's population.
    counts = tally_stage_counts(campaign, evaluate_stages(campaign))
    assert out.page.total_count == counts[child.id]["population"] == 2


@pytest.mark.asyncio
async def test_a_manual_stage_answers_with_its_pending_rows():
    # `pending` only ever occurs on a manual stage, and it is part of that
    # stage's population — so "everything in the stage" has to include it.
    auth = fake_auth(role="viewer")
    campaign, _, root = _campaign(auth.workspace_id)
    stage = CampaignStage(
        campaign_id=campaign.id,
        name="Chemist review",
        display_order=1,
        parent_stage_id=root.id,
        kind=StageKind.MANUAL,
    )
    campaign.add_stage(stage)
    waiting, _, _, promoted = campaign.results
    promoted.set_stage_override(
        stage_id=stage.id,
        forced_outcome=StageOutcome.HIT,
        reason="Resynthesised and confirmed",
        overridden_by=auth.user_id,
    )

    everything = (await _run(campaign, auth, stage_id=stage.id, outcome=EVERY_OUTCOME)).unwrap()
    pending = (
        await _run(campaign, auth, stage_id=stage.id, outcome=(StageOutcome.PENDING,))
    ).unwrap()

    assert {r.id for r in everything.page.items} == {waiting.id, promoted.id}
    assert [r.id for r in pending.page.items] == [waiting.id]


@pytest.mark.asyncio
async def test_sorts_and_pages_mixed_outcomes_as_one_list():
    auth = fake_auth(role="viewer")
    campaign, channel, stage = _campaign(auth.workspace_id)
    plain_2, _miss, nd, censored_5 = campaign.results
    mixed = dict(
        stage_id=stage.id,
        outcome=(StageOutcome.HIT, StageOutcome.UNTESTED),
        order_by_channel_id=channel.id,
        limit=2,
    )

    first = (await _run(campaign, auth, **mixed)).unwrap()
    second = (
        await _run(campaign, auth, **mixed, cursor_id=uuid.UUID(first.page.next_cursor))
    ).unwrap()

    # One list ordered by the channel — the two hits are not grouped ahead of
    # the untested row, and the count spans the whole filter.
    assert first.page.total_count == 3
    assert [r.id for r in first.page.items] == [plain_2.id, censored_5.id]
    assert [r.id for r in second.page.items] == [nd.id]
    assert second.page.next_cursor is None


@pytest.mark.asyncio
async def test_orders_by_a_channel_with_nd_last_in_both_directions():
    auth = fake_auth(role="viewer")
    campaign, channel, _ = _campaign(auth.workspace_id)
    plain_2, plain_50, nd, censored_5 = campaign.results

    asc = (await _run(campaign, auth, order_by_channel_id=channel.id)).unwrap()
    desc = (await _run(campaign, auth, order_by_channel_id=channel.id, descending=True)).unwrap()

    # Plain values first (2, 50), then the censored "> 5", then ND.
    assert [r.id for r in asc.page.items] == [plain_2.id, plain_50.id, censored_5.id, nd.id]
    # Descending flips the values inside each tier; the tiers themselves hold,
    # so an ND row never floats to the top of a potency sort.
    assert [r.id for r in desc.page.items] == [plain_50.id, plain_2.id, censored_5.id, nd.id]


@pytest.mark.asyncio
async def test_pages_with_a_cursor_and_reports_the_filtered_total():
    auth = fake_auth(role="viewer")
    campaign, channel, _ = _campaign(auth.workspace_id)

    first = (await _run(campaign, auth, order_by_channel_id=channel.id, limit=2)).unwrap()
    assert [r.id for r in first.page.items] == [campaign.results[0].id, campaign.results[1].id]
    assert first.page.total_count == 4
    assert first.page.next_cursor == str(campaign.results[1].id)

    second = (
        await _run(
            campaign,
            auth,
            order_by_channel_id=channel.id,
            limit=2,
            cursor_id=uuid.UUID(first.page.next_cursor),
        )
    ).unwrap()
    assert [r.id for r in second.page.items] == [campaign.results[3].id, campaign.results[2].id]
    assert second.page.next_cursor is None


@pytest.mark.asyncio
async def test_unknown_cursor_falls_back_to_the_first_page():
    # The row a cursor names can be removed between two page reads; that is a
    # stale cursor, not an error.
    auth = fake_auth(role="viewer")
    campaign, _, _ = _campaign(auth.workspace_id)

    out = (await _run(campaign, auth, cursor_id=uuid.uuid4(), limit=2)).unwrap()

    assert [r.id for r in out.page.items] == [campaign.results[0].id, campaign.results[1].id]


@pytest.mark.asyncio
async def test_outcome_without_a_stage_is_a_validation_error():
    auth = fake_auth(role="viewer")
    campaign, _, _ = _campaign(auth.workspace_id)

    result = await _run(campaign, auth, outcome=(StageOutcome.HIT,))

    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ValidationError)


@pytest.mark.asyncio
async def test_unknown_campaign_stage_and_channel_are_not_found():
    auth = fake_auth(role="viewer")
    campaign, _, _ = _campaign(auth.workspace_id)

    missing_campaign = await ListCampaignResults(
        uow=FakeUnitOfWork(), campaign_repo=make_campaign_repo(find_in_ws=None)
    )(
        ListCampaignResultsQuery(workspace_id=auth.workspace_id, campaign_id=uuid.uuid4()),
        auth=auth,
    )
    assert isinstance(missing_campaign.failure(), NotFoundError)

    bad_stage = await _run(campaign, auth, stage_id=uuid.uuid4())
    assert isinstance(bad_stage.failure(), NotFoundError)

    bad_channel = await _run(campaign, auth, order_by_channel_id=uuid.uuid4())
    assert isinstance(bad_channel.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_requires_a_workspace_member():
    auth = fake_auth(role="viewer")
    auth.has_role = lambda _minimum_role: False
    campaign, _, _ = _campaign(auth.workspace_id)

    with pytest.raises(AuthorizationError):
        await _use_case(campaign)(
            ListCampaignResultsQuery(workspace_id=auth.workspace_id, campaign_id=campaign.id),
            auth=auth,
        )


@pytest.mark.asyncio
async def test_another_workspace_cannot_read_the_rows():
    auth = fake_auth(role="viewer")
    campaign, _, _ = _campaign(auth.workspace_id)

    with pytest.raises(NotFoundError):
        await _use_case(campaign)(
            ListCampaignResultsQuery(workspace_id=uuid.uuid4(), campaign_id=campaign.id),
            auth=auth,
        )
