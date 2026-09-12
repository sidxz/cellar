"""Unit tests for AddResultsFromRuns (B6 commit path)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.add_results_from_runs import (
    AddResultsFromRuns,
    AddResultsFromRunsCommand,
)
from cellar.application.research_organization.channel_resolution import (
    ResolvedCandidate,
)
from cellar.application.research_organization.preview_run_import import (
    ChannelImportConfig,
)
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
    ValueQualifier,
)
from cellar.domain.shared.hit_criterion import HitCriterion
from cellar.domain.shared.errors import AuthorizationError, ValidationError
from tests.unit.application.research_organization._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeChannelQuery:
    def __init__(self, candidates_by_channel=None, endpoints_by_channel=None) -> None:
        self._data = candidates_by_channel or {}
        self._endpoints = endpoints_by_channel or {}

    @staticmethod
    def _scoped(data, protocol_id, readout_definition_id, run_ids):
        run_set = set(run_ids)
        out: dict[uuid.UUID, list[ResolvedCandidate]] = {}
        for mol_id, cands in data.get((protocol_id, readout_definition_id), {}).items():
            kept = [c for c in cands if c.run_id in run_set]
            if kept:
                out[mol_id] = kept
        return out

    async def fetch_candidates(self, *, workspace_id, channel, molecule_id):
        return []

    async def fetch_endpoint_candidates(self, *, workspace_id, channel, molecule_id):
        return []

    async def fetch_candidates_for_runs(
        self,
        *,
        workspace_id,
        run_ids,
        protocol_id,
        readout_definition_id,
        source_kind,
        normalization_applied=None,
    ):
        return self._scoped(self._data, protocol_id, readout_definition_id, run_ids)

    async def fetch_endpoint_candidates_for_runs(
        self,
        *,
        workspace_id,
        run_ids,
        protocol_id,
        readout_definition_id,
        normalization_applied=None,
    ):
        return self._scoped(self._endpoints, protocol_id, readout_definition_id, run_ids)


def _candidate(
    *,
    value: float = 50.0,
    qualifier: ValueQualifier = ValueQualifier.EQ,
    unit: str = "nM",
    run_id: uuid.UUID | None = None,
    run_date: date | None = None,
    approved: bool = True,
    z_prime: float | None = 0.8,
) -> ResolvedCandidate:
    return ResolvedCandidate(
        value=value,
        qualifier=qualifier,
        unit=unit,
        run_id=run_id or uuid.uuid4(),
        run_date=run_date or date(2026, 1, 1),
        run_approved=approved,
        z_prime=z_prime,
        protocol_name="Proto",
        protocol_version=1,
        curve_id=None,
        readout_id=uuid.uuid4(),
    )


def _draft_campaign(workspace_id) -> Campaign:
    return Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="C",
        description=None,
        created_by=uuid.uuid4(),
    )


def _run_repo(run_ids):
    repo = AsyncMock()
    repo.find_by_ids = AsyncMock(return_value=[SimpleNamespace(id=r) for r in run_ids])
    return repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAddResultsFromRuns:
    @pytest.mark.asyncio
    async def test_unauthorized(self) -> None:
        auth = fake_auth(role="viewer")
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=None),
            run_repo=_run_repo([]),
            channel_query=FakeChannelQuery(),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=uuid.uuid4(),
            run_ids=[uuid.uuid4()],
            channel_configs=[],
        )
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)
    @pytest.mark.asyncio
    async def test_locked_campaign_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        campaign.status = CampaignStatus.CLOSED  # type: ignore[misc]
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([uuid.uuid4()]),
            channel_query=FakeChannelQuery(),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[uuid.uuid4()],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=uuid.uuid4(),
                    readout_definition_id=uuid.uuid4(),
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                )
            ],
        )
        out = await uc(cmd, auth=auth)
        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_hits_only_with_threshold_adds_only_hits(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        proto = uuid.uuid4()
        readout = uuid.uuid4()
        run_id = uuid.uuid4()
        mol_hit = uuid.uuid4()
        mol_miss = uuid.uuid4()
        candidates = {
            (proto, readout): {
                mol_hit: [_candidate(value=42.0, run_id=run_id)],
                mol_miss: [_candidate(value=9000.0, run_id=run_id)],
            }
        }
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([run_id]),
            channel_query=FakeChannelQuery(candidates),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto,
                    readout_definition_id=readout,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=HitCriterion(
                        readout_name="IC50", operator="lt", value=1000.0
                    ),
                )
            ],
            scope="hits_only",
        )
        out = await uc(cmd, auth=auth)
        assert isinstance(out, Success)
        outcome = out.unwrap()
        assert outcome.added == 1
        assert outcome.channels_created == 1
        assert outcome.channels_reused == 0
        assert any(r.molecule_id == mol_hit for r in campaign.results)

    @pytest.mark.asyncio
    async def test_scope_all_adds_everyone(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        proto, readout, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        m1, m2 = uuid.uuid4(), uuid.uuid4()
        candidates = {
            (proto, readout): {
                m1: [_candidate(value=100.0, run_id=run_id)],
                m2: [_candidate(value=5000.0, run_id=run_id)],
            }
        }
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([run_id]),
            channel_query=FakeChannelQuery(candidates),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto,
                    readout_definition_id=readout,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                )
            ],
            scope="all",
        )
        out = await uc(cmd, auth=auth)
        assert isinstance(out, Success)
        assert out.unwrap().added == 2
        assert {r.molecule_id for r in campaign.results} == {m1, m2}

    @pytest.mark.asyncio
    async def test_channel_reuse_when_matching_exists(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        proto, readout, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        existing = CampaignChannel(
            campaign_id=campaign.id,
            label="orig",
            display_order=0,
            protocol_id=proto,
            readout_definition_id=readout,
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.LATEST_APPROVED_RUN,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        )
        campaign.channels.append(existing)
        mol = uuid.uuid4()
        candidates = {
            (proto, readout): {mol: [_candidate(value=10.0, run_id=run_id)]}
        }
        new_threshold = HitCriterion(
            readout_name="IC50", operator="lt", value=500.0
        )
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([run_id]),
            channel_query=FakeChannelQuery(candidates),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto,
                    readout_definition_id=readout,
                    label="updated",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.MEAN_ACROSS_RUNS,  # changed!
                    hit_threshold=new_threshold,  # changed!
                )
            ],
            scope="all",
        )
        out = await uc(cmd, auth=auth)
        assert isinstance(out, Success)
        outcome = out.unwrap()
        assert outcome.channels_reused == 1
        assert outcome.channels_created == 0
        # Original channel still exists (id stable); selection rule updated.
        # The threshold is import-time filtering only — never persisted to
        # the channel record.
        assert len(campaign.channels) == 1
        assert campaign.channels[0].id == existing.id
        assert campaign.channels[0].selection_rule == SelectionRule.MEAN_ACROSS_RUNS

    @pytest.mark.asyncio
    async def test_idempotent_rerun_does_not_duplicate(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        proto, readout, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        mol = uuid.uuid4()
        candidates = {(proto, readout): {mol: [_candidate(value=42.0, run_id=run_id)]}}
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([run_id]),
            channel_query=FakeChannelQuery(candidates),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto,
                    readout_definition_id=readout,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=HitCriterion(
                        readout_name="IC50", operator="lt", value=1000.0
                    ),
                )
            ],
            scope="hits_only",
        )
        out1 = await uc(cmd, auth=auth)
        assert isinstance(out1, Success)
        assert out1.unwrap().added == 1
        out2 = await uc(cmd, auth=auth)
        assert isinstance(out2, Success)
        assert out2.unwrap().added == 0  # already in campaign

    @pytest.mark.asyncio
    async def test_refresh_existing_cells_updates_non_override(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        proto, readout, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        mol = uuid.uuid4()

        # Pre-existing channel + result + measurement (non-override)
        channel = CampaignChannel(
            campaign_id=campaign.id,
            label="IC50",
            display_order=0,
            protocol_id=proto,
            readout_definition_id=readout,
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.LATEST_APPROVED_RUN,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        )
        campaign.channels.append(channel)
        result = CampaignResult(campaign_id=campaign.id, molecule_id=mol)
        old_m = CampaignMeasurement(
            result_id=result.id,
            channel_id=channel.id,
            value=999.0,
            value_qualifier=ValueQualifier.EQ,
            unit="nM",
            protocol_name_snapshot="OLD",
            protocol_version_snapshot=1,
            is_manual_override=False,
        )
        result.add_measurement(old_m)
        campaign.results.append(result)

        candidates = {(proto, readout): {mol: [_candidate(value=42.0, run_id=run_id)]}}
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([run_id]),
            channel_query=FakeChannelQuery(candidates),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto,
                    readout_definition_id=readout,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                )
            ],
            scope="all",
            refresh_existing_cells=True,
        )
        out = await uc(cmd, auth=auth)
        assert isinstance(out, Success)
        new_m = campaign.results[0].find_measurement(channel.id)
        assert new_m is not None
        assert new_m.value == 42.0
        assert new_m.is_manual_override is False

    @pytest.mark.asyncio
    async def test_refresh_existing_cells_preserves_overrides(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        proto, readout, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        mol = uuid.uuid4()
        channel = CampaignChannel(
            campaign_id=campaign.id,
            label="IC50",
            display_order=0,
            protocol_id=proto,
            readout_definition_id=readout,
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.LATEST_APPROVED_RUN,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        )
        campaign.channels.append(channel)
        result = CampaignResult(campaign_id=campaign.id, molecule_id=mol)
        override = CampaignMeasurement(
            result_id=result.id,
            channel_id=channel.id,
            value=11.0,  # manually set
            value_qualifier=ValueQualifier.EQ,
            unit="nM",
            protocol_name_snapshot="MANUAL",
            protocol_version_snapshot=1,
            is_manual_override=True,
            override_reason="reviewer correction",
        )
        result.add_measurement(override)
        campaign.results.append(result)

        candidates = {(proto, readout): {mol: [_candidate(value=42.0, run_id=run_id)]}}
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([run_id]),
            channel_query=FakeChannelQuery(candidates),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto,
                    readout_definition_id=readout,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                )
            ],
            scope="all",
            refresh_existing_cells=True,
        )
        await uc(cmd, auth=auth)
        m = campaign.results[0].find_measurement(channel.id)
        assert m is not None
        assert m.value == 11.0  # preserved
        assert m.is_manual_override is True
        assert m.override_reason == "reviewer correction"

    @pytest.mark.asyncio
    async def test_all_use_for_filter_false_with_hits_only_adds_zero(self) -> None:
        """All filters disabled + hits_only -> no molecule qualifies."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        proto, readout, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        mol = uuid.uuid4()
        candidates = {(proto, readout): {mol: [_candidate(value=42.0, run_id=run_id)]}}
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([run_id]),
            channel_query=FakeChannelQuery(candidates),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto,
                    readout_definition_id=readout,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=HitCriterion(
                        readout_name="IC50", operator="lt", value=1000.0
                    ),
                    use_for_filter=False,  # disabled
                )
            ],
            scope="hits_only",
        )
        out = await uc(cmd, auth=auth)
        assert isinstance(out, Success)
        assert out.unwrap().added == 0

    @pytest.mark.asyncio
    async def test_snapshot_fields_populate_on_new_measurement(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        proto, readout = uuid.uuid4(), uuid.uuid4()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        mol = uuid.uuid4()
        candidates = {
            (proto, readout): {
                mol: [
                    _candidate(value=10.0, run_id=r1),
                    _candidate(value=14.0, run_id=r2),
                ]
            }
        }
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([r1, r2]),
            channel_query=FakeChannelQuery(candidates),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[r1, r2],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto,
                    readout_definition_id=readout,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
                )
            ],
            scope="all",
        )
        out = await uc(cmd, auth=auth)
        assert isinstance(out, Success)
        assert campaign.results[0].measurements[0].replicate_count == 2
        assert campaign.results[0].measurements[0].qc_pass is True
        assert set(
            campaign.results[0].measurements[0].contributing_run_ids
        ) == {r1, r2}

    # ------------------------------------------------------------------
    # stage_name (Task 12)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_stage_created_with_criteria_bound_to_channels(self) -> None:
        """stage_name + N filtering configs -> one CampaignStage, N criteria,
        each bound to the channel its own config resolved to."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        proto1, readout1, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        proto2, readout2 = uuid.uuid4(), uuid.uuid4()
        mol = uuid.uuid4()
        candidates = {
            (proto1, readout1): {mol: [_candidate(value=42.0, run_id=run_id)]},
            (proto2, readout2): {mol: [_candidate(value=7.0, run_id=run_id)]},
        }
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([run_id]),
            channel_query=FakeChannelQuery(candidates),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto1,
                    readout_definition_id=readout1,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=HitCriterion(
                        readout_name="IC50", operator="lt", value=1000.0
                    ),
                ),
                ChannelImportConfig(
                    protocol_id=proto2,
                    readout_definition_id=readout2,
                    label="CC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=HitCriterion(
                        readout_name="CC50", operator="gt", value=5.0
                    ),
                ),
            ],
            scope="all",
            stage_name="Primary Hits",
        )
        out = await uc(cmd, auth=auth)
        assert isinstance(out, Success)
        assert out.unwrap().stage_created is True
        assert len(campaign.stages) == 1
        stage = campaign.stages[0]
        assert stage.name == "Primary Hits"
        assert stage.parent_stage_id is None
        assert len(stage.criteria) == 2

        ic50_channel = next(
            ch for ch in campaign.channels if ch.readout_definition_id == readout1
        )
        cc50_channel = next(
            ch for ch in campaign.channels if ch.readout_definition_id == readout2
        )
        by_channel = {c.channel_id: c for c in stage.criteria}
        assert by_channel[ic50_channel.id].operator == "lt"
        assert by_channel[ic50_channel.id].value == 1000.0
        assert by_channel[cc50_channel.id].operator == "gt"
        assert by_channel[cc50_channel.id].value == 5.0

    @pytest.mark.asyncio
    async def test_no_stage_when_no_filter_criteria(self) -> None:
        """stage_name given but no config has use_for_filter+hit_threshold ->
        no stage is created; not an error."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        proto, readout, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        mol = uuid.uuid4()
        candidates = {(proto, readout): {mol: [_candidate(value=42.0, run_id=run_id)]}}
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([run_id]),
            channel_query=FakeChannelQuery(candidates),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto,
                    readout_definition_id=readout,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    # no hit_threshold -> nothing qualifies for the stage
                )
            ],
            scope="all",
            stage_name="Primary Hits",
        )
        out = await uc(cmd, auth=auth)
        assert isinstance(out, Success)
        assert out.unwrap().stage_created is False
        assert campaign.stages == []

    @pytest.mark.asyncio
    async def test_stage_skips_in_operator_configs(self) -> None:
        """A config whose hit_threshold uses the string-based 'in' operator
        contributes no StageCriterion (StageCriterion — unlike HitCriterion —
        doesn't support it, same as the mirror-protocol path); the stage is
        still built from the remaining numeric config(s)."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        proto1, readout1, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        proto2, readout2 = uuid.uuid4(), uuid.uuid4()
        mol = uuid.uuid4()
        candidates = {
            (proto1, readout1): {mol: [_candidate(value=42.0, run_id=run_id)]},
            (proto2, readout2): {mol: [_candidate(value=7.0, run_id=run_id)]},
        }
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([run_id]),
            channel_query=FakeChannelQuery(candidates),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto1,
                    readout_definition_id=readout1,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=HitCriterion(readout_name="IC50", operator="lt", value=1000.0),
                ),
                ChannelImportConfig(
                    protocol_id=proto2,
                    readout_definition_id=readout2,
                    label="Curve Class",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=HitCriterion(
                        readout_name="Curve Class", operator="in", value=["full"]
                    ),
                ),
            ],
            scope="all",
            stage_name="Primary Hits",
        )
        out = await uc(cmd, auth=auth)
        assert isinstance(out, Success)
        assert out.unwrap().stage_created is True
        assert len(campaign.stages) == 1
        stage = campaign.stages[0]
        assert len(stage.criteria) == 1  # the 'in' config contributed nothing
        ic50_channel = next(ch for ch in campaign.channels if ch.readout_definition_id == readout1)
        assert stage.criteria[0].channel_id == ic50_channel.id

    @pytest.mark.asyncio
    async def test_stage_name_collision_returns_failure(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        proto, readout, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        mol = uuid.uuid4()

        other_channel = CampaignChannel(
            campaign_id=campaign.id,
            label="Other",
            display_order=0,
            protocol_id=uuid.uuid4(),
            readout_definition_id=uuid.uuid4(),
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.LATEST_APPROVED_RUN,
            qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        )
        campaign.channels.append(other_channel)
        campaign.add_stage(
            CampaignStage(
                campaign_id=campaign.id,
                name="Primary Hits",
                display_order=0,
                criteria=[
                    StageCriterion(channel_id=other_channel.id, operator="lt", value=1.0)
                ],
            )
        )

        candidates = {(proto, readout): {mol: [_candidate(value=42.0, run_id=run_id)]}}
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([run_id]),
            channel_query=FakeChannelQuery(candidates),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto,
                    readout_definition_id=readout,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                    hit_threshold=HitCriterion(
                        readout_name="IC50", operator="lt", value=1000.0
                    ),
                )
            ],
            scope="all",
            stage_name="Primary Hits",  # collides with the pre-existing stage
        )
        out = await uc(cmd, auth=auth)
        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        # The colliding stage attempt must not have appended a duplicate.
        assert len(campaign.stages) == 1

    # ---- D1: dose-response fallback to reported endpoint rows ----

    @staticmethod
    def _curve_candidate(*, value: float, run_id: uuid.UUID) -> ResolvedCandidate:
        c = _candidate(value=value, run_id=run_id)
        return replace(c, curve_id=uuid.uuid4(), readout_id=None, curve_class="full")

    @pytest.mark.asyncio
    async def test_dr_config_falls_back_to_endpoint_when_molecule_has_no_curve(
        self,
    ) -> None:
        """A DR channel imports a molecule that only has a summary-imported
        reported endpoint; a molecule with a fitted curve keeps its curve."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        proto, readout, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        mol_curve, mol_endpoint = uuid.uuid4(), uuid.uuid4()
        curve = self._curve_candidate(value=10.0, run_id=run_id)
        curve_mol_endpoint = _candidate(value=999.0, run_id=run_id)
        endpoint = _candidate(value=32.0, run_id=run_id)
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([run_id]),
            channel_query=FakeChannelQuery(
                {(proto, readout): {mol_curve: [curve]}},
                {
                    (proto, readout): {
                        mol_curve: [curve_mol_endpoint],
                        mol_endpoint: [endpoint],
                    }
                },
            ),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto,
                    readout_definition_id=readout,
                    label="IC50",
                    source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                )
            ],
            scope="all",
        )
        out = await uc(cmd, auth=auth)
        assert isinstance(out, Success)
        assert out.unwrap().added == 2

        by_mol = {r.molecule_id: r for r in campaign.results}
        endpoint_cell = by_mol[mol_endpoint].measurements[0]
        assert endpoint_cell.value == 32.0
        assert endpoint_cell.source_readout_id == endpoint.readout_id
        assert endpoint_cell.source_curve_id is None

        # The molecule with a curve keeps the curve — its endpoint row is ignored.
        curve_cell = by_mol[mol_curve].measurements[0]
        assert curve_cell.value == 10.0
        assert curve_cell.source_curve_id == curve.curve_id
        assert curve_cell.source_readout_id is None

    @pytest.mark.asyncio
    async def test_readout_config_does_not_fetch_endpoint_fallback(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        proto, readout, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        mol = uuid.uuid4()
        uc = AddResultsFromRuns(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            run_repo=_run_repo([run_id]),
            channel_query=FakeChannelQuery(
                {},
                {(proto, readout): {mol: [_candidate(value=32.0, run_id=run_id)]}},
            ),
            dispatcher=AsyncMock(),
        )
        cmd = AddResultsFromRunsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            run_ids=[run_id],
            channel_configs=[
                ChannelImportConfig(
                    protocol_id=proto,
                    readout_definition_id=readout,
                    label="IC50",
                    source_kind=ChannelSourceKind.READOUT_DATA,
                    selection_rule=SelectionRule.LATEST_APPROVED_RUN,
                )
            ],
            scope="all",
        )
        out = await uc(cmd, auth=auth)
        assert isinstance(out, Success)
        assert out.unwrap().added == 0
