"""Unit tests for SetCellQcVerdicts: a person's QC verdict on many campaign cells at once.

The fixture campaign has a stage "Primary" (hit when column A < 10) owning columns A and B,
plus a column C on no stage, and five compounds:

    row  A                        B        C
    r0   2  (hit)                 5        1
    r1   50 (miss, forced HIT)    6        1
    r2   ND, no curve (no result) missing  1
    r3   3  (hit), already FAILED 7        1
    r4   4  (hit, forced MISS)    8        1
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.campaign_row_selection import RowSelection
from cellar.application.research_organization.set_cell_qc_verdicts import (
    QcTarget,
    QcVerdictCounts,
    SetCellQcVerdicts,
    SetCellQcVerdictsCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import CampaignMeasurement
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_result_filters import (
    CampaignResultFilters,
    MeasurementFilter,
)
from cellar.domain.research_organization.campaign_stage import CampaignStage, StageCriterion
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QcVerdict,
    StageOutcome,
)
from cellar.domain.shared.aggregation_types import (
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.shared.errors import (
    AuthorizationError,
    DataLockedError,
    NotFoundError,
    ValidationError,
)
from tests.unit.application.research_organization._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)

EARLIER = datetime(2026, 1, 1, tzinfo=UTC)
SOMEONE = uuid.uuid4()


@dataclass
class Fx:
    campaign: Campaign
    stage: CampaignStage
    a: CampaignChannel
    b: CampaignChannel
    c: CampaignChannel
    rows: list[CampaignResult]

    @property
    def labels(self) -> dict[uuid.UUID, str]:
        return {self.a.id: "a", self.b.id: "b", self.c.id: "c"}


def _channel(campaign: Campaign, label: str, order: int) -> CampaignChannel:
    channel = CampaignChannel(
        campaign_id=campaign.id,
        label=label,
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.LATEST_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=order,
    )
    campaign.add_channel(channel)
    return channel


def _cell(result: CampaignResult, channel: CampaignChannel, value: float | None) -> None:
    result.add_measurement(
        CampaignMeasurement(
            result_id=result.id,
            channel_id=channel.id,
            value=value,
            value_qualifier=ValueQualifier.EQ if value is not None else ValueQualifier.ND,
            unit="uM",
            protocol_name_snapshot="Proto",
            protocol_version_snapshot=1,
        )
    )


def _fixture(workspace_id: uuid.UUID, status: CampaignStatus = CampaignStatus.DRAFT) -> Fx:
    campaign = Campaign(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Primary screen",
        status=CampaignStatus.DRAFT,
        created_by=uuid.uuid4(),
    )
    a = _channel(campaign, "A", 0)
    b = _channel(campaign, "B", 1)
    c = _channel(campaign, "C", 2)
    stage = CampaignStage(
        campaign_id=campaign.id,
        name="Primary",
        display_order=0,
        criteria=[StageCriterion(channel_id=a.id, operator="lt", value=10.0)],
    )
    a.stage_id = stage.id
    b.stage_id = stage.id
    campaign.add_stage(stage)

    cells: list[tuple[float | None, float | None]] = [
        (2.0, 5.0),
        (50.0, 6.0),
        (None, None),
        (3.0, 7.0),
        (4.0, 8.0),
    ]
    rows = []
    for i, (a_value, b_value) in enumerate(cells):
        row = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        _cell(row, a, a_value)
        if i != 2:
            _cell(row, b, b_value)
        _cell(row, c, 1.0)
        campaign.add_result(row)
        rows.append(row)

    m = rows[3].find_measurement(a.id)
    assert m is not None
    m.qc_verdict, m.qc_verdict_by, m.qc_verdict_at = QcVerdict.FAILED, SOMEONE, EARLIER
    for row, forced in ((rows[1], StageOutcome.HIT), (rows[4], StageOutcome.MISS)):
        row.set_stage_override(
            stage_id=stage.id, forced_outcome=forced, reason="Review", overridden_by=SOMEONE
        )
    campaign.status = status
    campaign.updated_at = EARLIER
    campaign.clear_events()
    return Fx(campaign, stage, a, b, c, rows)


class _AllMatch:
    """Identity reader whose search matches every compound."""

    async def matching_ids(self, workspace_id, molecule_ids, search):
        return set(molecule_ids)


def _use_case(fx: Fx | None, repo: AsyncMock | None = None) -> SetCellQcVerdicts:
    dispatcher = AsyncMock()
    return SetCellQcVerdicts(
        uow=FakeUnitOfWork(),
        campaign_repo=repo or make_campaign_repo(find_in_ws=fx.campaign if fx else None),
        identity_reader=_AllMatch(),
        dispatcher=dispatcher,
    )


def _command(auth, fx: Fx, *targets: QcTarget, **kwargs) -> SetCellQcVerdictsCommand:
    kwargs.setdefault("verdict", QcVerdict.VERIFIED)
    return SetCellQcVerdictsCommand(
        workspace_id=auth.workspace_id,
        campaign_id=fx.campaign.id,
        user_id=auth.user_id,
        targets=targets,
        **kwargs,
    )


def _verified(fx: Fx) -> set[tuple[int, str]]:
    return {
        (i, fx.labels[m.channel_id])
        for i, row in enumerate(fx.rows)
        for m in row.measurements
        if m.qc_verdict == QcVerdict.VERIFIED
    }


def _counts(changed: int = 0, unchanged: int = 0, kept: int = 0, no_result: int = 0):
    return QcVerdictCounts(changed=changed, unchanged=unchanged, kept=kept, no_result=no_result)


def _target(channels, rows=None, where=None) -> QcTarget:
    return QcTarget(
        channel_ids=tuple(ch.id for ch in channels),
        result_ids=None if rows is None else tuple(r.id for r in rows),
        where=where,
    )


# ---------------------------------------------------------------------------
# Scopes
# ---------------------------------------------------------------------------

SCOPES: dict[str, tuple[Callable[[Fx], QcTarget], set[tuple[int, str]], QcVerdictCounts]] = {
    "one_cell": (lambda f: _target([f.a], [f.rows[0]]), {(0, "a")}, _counts(changed=1)),
    "compounds_by_all_columns": (
        lambda f: _target([f.a, f.b, f.c], [f.rows[0], f.rows[2]]),
        {(0, "a"), (0, "b"), (0, "c"), (2, "c")},
        _counts(changed=4, no_result=2),
    ),
    "whole_column": (
        lambda f: _target([f.b]),
        {(0, "b"), (1, "b"), (3, "b"), (4, "b")},
        _counts(changed=4, no_result=1),
    ),
    "whole_stage": (
        lambda f: _target(f.campaign.channels_of_stage(f.stage.id)),
        {(0, "a"), (1, "a"), (4, "a"), (0, "b"), (1, "b"), (3, "b"), (4, "b")},
        _counts(changed=7, kept=1, no_result=2),
    ),
    # Hits after overrides (r0, r1 forced HIT, r3; not r4 forced MISS) whose A cell is
    # still awaiting QC (not r3, already failed).
    "where_hits_awaiting_qc": (
        lambda f: _target(
            [f.a],
            where=RowSelection(
                stage_id=f.stage.id,
                outcome=(StageOutcome.HIT,),
                filters=CampaignResultFilters(
                    search="ref",
                    measurements=(MeasurementFilter(channel_id=f.a.id, qc="not_tested"),),
                ),
            ),
        ),
        {(0, "a"), (1, "a")},
        _counts(changed=2),
    ),
}


@pytest.mark.parametrize("scope", list(SCOPES))
async def test_targets_expand(scope: str) -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)
    build, expected, counts = SCOPES[scope]

    out = await _use_case(fx)(_command(auth, fx, build(fx)), auth=auth)

    assert out == Success(counts)
    assert _verified(fx) == expected
    for i, label in expected:
        m = fx.rows[i].find_measurement({"a": fx.a, "b": fx.b, "c": fx.c}[label].id)
        assert m is not None and m.qc_verdict_by == auth.user_id


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------


async def test_counts_changed_unchanged_kept_no_result() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)
    r0a = fx.rows[0].find_measurement(fx.a.id)
    assert r0a is not None
    r0a.qc_verdict, r0a.qc_verdict_by, r0a.qc_verdict_at = QcVerdict.VERIFIED, SOMEONE, EARLIER

    out = await _use_case(fx)(_command(auth, fx, _target([fx.a])), auth=auth)

    # r0 already verified, r1/r4 newly verified, r2 has no result, r3 keeps its FAILED.
    assert out == Success(_counts(changed=2, unchanged=1, kept=1, no_result=1))
    assert (r0a.qc_verdict_by, r0a.qc_verdict_at) == (SOMEONE, EARLIER)
    r3a = fx.rows[3].find_measurement(fx.a.id)
    assert r3a is not None and r3a.qc_verdict == QcVerdict.FAILED


async def test_overwrite_replaces_the_other_verdict() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)

    out = await _use_case(fx)(
        _command(auth, fx, _target([fx.a], [fx.rows[3]]), overwrite=True, note="re-read plate"),
        auth=auth,
    )

    assert out == Success(_counts(changed=1))
    m = fx.rows[3].find_measurement(fx.a.id)
    assert m is not None
    assert (m.qc_verdict, m.qc_verdict_by, m.qc_verdict_note) == (
        QcVerdict.VERIFIED,
        auth.user_id,
        "re-read plate",
    )


async def test_overwrite_naming_no_note_leaves_a_same_verdict_cell_alone() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)
    m = fx.rows[3].find_measurement(fx.a.id)
    assert m is not None
    m.qc_verdict_note = "edge well"
    target = _target([fx.a], [fx.rows[3]])

    out = await _use_case(fx)(
        _command(auth, fx, target, verdict=QcVerdict.FAILED, overwrite=True), auth=auth
    )
    assert out == Success(_counts(unchanged=1))
    assert (m.qc_verdict_by, m.qc_verdict_note) == (SOMEONE, "edge well")

    # An explicit null is "no note": it re-stamps and removes the note.
    out = await _use_case(fx)(
        _command(auth, fx, target, verdict=QcVerdict.FAILED, overwrite=True, note=None),
        auth=auth,
    )
    assert out == Success(_counts(changed=1))
    assert (m.qc_verdict_by, m.qc_verdict_note) == (auth.user_id, None)


async def test_overlapping_targets_count_each_cell_once() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)

    out = await _use_case(fx)(
        _command(auth, fx, _target([fx.a], [fx.rows[0]]), _target([fx.a, fx.b])), auth=auth
    )

    assert out == Success(_counts(changed=7, kept=1, no_result=2))


async def test_where_matching_no_rows_is_all_zero() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)
    where = RowSelection(stage_id=fx.stage.id, outcome=(StageOutcome.PENDING,))

    out = await _use_case(fx)(_command(auth, fx, _target([fx.a], where=where)), auth=auth)

    assert out == Success(_counts())
    assert fx.campaign.updated_at == EARLIER


async def test_missing_measurement_counts_no_result() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)

    out = await _use_case(fx)(_command(auth, fx, _target([fx.b], [fx.rows[2]])), auth=auth)

    assert out == Success(_counts(no_result=1))
    assert fx.rows[2].find_measurement(fx.b.id) is None


# ---------------------------------------------------------------------------
# All or nothing
# ---------------------------------------------------------------------------


async def _refused(fx: Fx, auth, *targets: QcTarget, **kwargs):
    repo = make_campaign_repo(find_in_ws=fx.campaign)
    before = _verified(fx)
    out = await _use_case(fx, repo)(_command(auth, fx, *targets, **kwargs), auth=auth)
    assert isinstance(out, Failure)
    assert _verified(fx) == before
    repo.save.assert_not_awaited()
    return out.failure()


async def test_unknown_result_id_is_404_nothing_applied() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)
    stranger = CampaignResult(campaign_id=fx.campaign.id, molecule_id=uuid.uuid4())

    error = await _refused(
        fx, auth, _target([fx.a], [fx.rows[0]]), _target([fx.a], [fx.rows[1], stranger])
    )

    assert isinstance(error, NotFoundError)


async def test_unknown_channel_id_is_404_nothing_applied() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)

    error = await _refused(
        fx,
        auth,
        _target([fx.a], [fx.rows[0]]),
        QcTarget(channel_ids=(fx.b.id, uuid.uuid4())),
    )

    assert isinstance(error, NotFoundError)


async def test_unknown_where_stage_is_404() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)

    error = await _refused(
        fx,
        auth,
        _target([fx.a], [fx.rows[0]]),
        _target([fx.a], where=RowSelection(stage_id=uuid.uuid4())),
    )

    assert isinstance(error, NotFoundError)


async def test_where_outcome_without_stage_is_422() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)

    error = await _refused(
        fx, auth, _target([fx.a], where=RowSelection(outcome=(StageOutcome.HIT,)))
    )

    assert isinstance(error, ValidationError)


async def test_both_result_ids_and_where_is_422() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)

    error = await _refused(
        fx, auth, _target([fx.a], [fx.rows[0]], where=RowSelection(stage_id=fx.stage.id))
    )

    assert isinstance(error, ValidationError)


async def test_note_with_clear_is_422_nothing_applied() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)
    r0a = fx.rows[0].find_measurement(fx.a.id)
    assert r0a is not None
    r0a.qc_verdict = QcVerdict.VERIFIED

    error = await _refused(fx, auth, _target([fx.a]), verdict=None, note="bad well")

    assert isinstance(error, ValidationError)


async def test_note_with_clear_reaching_no_cell_is_422() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)
    repo = make_campaign_repo(find_in_ws=fx.campaign)
    nothing = RowSelection(stage_id=fx.stage.id, outcome=(StageOutcome.PENDING,))

    out = await _use_case(fx, repo)(
        _command(auth, fx, _target([fx.a], where=nothing), verdict=None, note="bad well"),
        auth=auth,
    )

    assert isinstance(out.failure(), ValidationError)
    repo.find_by_id_in_workspace.assert_not_awaited()


# ---------------------------------------------------------------------------
# Guards and persistence
# ---------------------------------------------------------------------------


async def test_closed_campaign_is_423() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id, status=CampaignStatus.CLOSED)

    error = await _refused(fx, auth, _target([fx.a]))

    assert isinstance(error, DataLockedError)


async def test_unknown_campaign_is_404() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)
    repo = make_campaign_repo(find_in_ws=None)

    out = await _use_case(None, repo)(_command(auth, fx, _target([fx.a])), auth=auth)

    assert isinstance(out.failure(), NotFoundError)


async def test_viewer_is_forbidden() -> None:
    auth = fake_auth(role="viewer")
    fx = _fixture(auth.workspace_id)
    repo = make_campaign_repo(find_in_ws=fx.campaign)

    with pytest.raises(AuthorizationError):
        await _use_case(fx, repo)(_command(auth, fx, _target([fx.a])), auth=auth)
    repo.save.assert_not_awaited()


async def test_save_called_once() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)
    repo = make_campaign_repo(find_in_ws=fx.campaign)
    uc = _use_case(fx, repo)

    out = await uc(_command(auth, fx, _target([fx.a, fx.b, fx.c])), auth=auth)

    assert isinstance(out, Success)
    repo.save.assert_awaited_once_with(fx.campaign)
    assert fx.campaign.updated_at > EARLIER
    uc._dispatcher.dispatch_all.assert_awaited_once()


async def test_nothing_changed_does_not_save() -> None:
    auth = fake_auth()
    fx = _fixture(auth.workspace_id)
    repo = make_campaign_repo(find_in_ws=fx.campaign)
    uc = _use_case(fx, repo)

    # r3's A cell is already failed; r2's has no result.
    out = await uc(
        _command(auth, fx, _target([fx.a], [fx.rows[2], fx.rows[3]]), verdict=QcVerdict.FAILED),
        auth=auth,
    )

    assert out == Success(_counts(unchanged=1, no_result=1))
    repo.save.assert_not_awaited()
    uc._dispatcher.dispatch_all.assert_not_awaited()
    assert fx.campaign.updated_at == EARLIER
