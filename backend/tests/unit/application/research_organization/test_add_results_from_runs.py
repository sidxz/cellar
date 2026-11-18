"""Unit tests for AddResultsFromRuns (B6 commit path).

The stage-scoped cases (spec §12) live in ``test_stage_scoped_cases.py``; these
cover the request itself: scope and filters, column reuse, seed runs, stage_name,
the D1 endpoint fallback and the curve-class row filter.
"""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.add_results_from_runs import (
    AddResultsFromRuns,
    AddResultsFromRunsCommand,
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
    MeasurementBasis,
    QualifierHandling,
    SelectionRule,
    UnresolvedReason,
    ValueQualifier,
)
from cellar.domain.research_organization.source_ref import RunRef, SeedRun
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ValidationError
from cellar.domain.shared.hit_criterion import HitCriterion, InterceptKey
from tests.unit.application.research_organization._helpers import (
    FakeRunData,
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
    reading,
)

PROTO = uuid.uuid4()


def _draft_campaign(workspace_id) -> Campaign:
    return Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="C",
        description=None,
        created_by=uuid.uuid4(),
    )


def _run_repo(run_ids, protocol_id=PROTO):
    """Fake RunRepository — ``find_by_ids`` returns ``{id: run}`` like the port."""
    repo = AsyncMock()
    repo.find_by_ids = AsyncMock(
        return_value={r: SimpleNamespace(id=r, protocol_id=protocol_id) for r in run_ids}
    )
    return repo


def _config(
    readout,
    rule=SelectionRule.LATEST_RUN,
    *,
    protocol=PROTO,
    kind=ChannelSourceKind.READOUT_DATA,
    lt: float | None = None,
    **kw,
) -> ChannelImportConfig:
    return ChannelImportConfig(
        protocol_id=protocol,
        readout_definition_id=readout,
        label="IC50",
        source_kind=kind,
        selection_rule=rule,
        hit_threshold=(
            HitCriterion(readout_name="IC50", operator="lt", value=lt) if lt is not None else None
        ),
        **kw,
    )


def _channel(campaign, readout, *, stage_id=None) -> CampaignChannel:
    ch = CampaignChannel(
        campaign_id=campaign.id,
        label="IC50",
        display_order=len(campaign.channels),
        protocol_id=PROTO,
        readout_definition_id=readout,
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.LATEST_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        stage_id=stage_id,
    )
    campaign.add_channel(ch)
    return ch


def _uc(campaign, data, run_ids, protocol_id=PROTO, saved=None) -> AddResultsFromRuns:
    return AddResultsFromRuns(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(saved=saved, find_in_ws=campaign),
        run_repo=_run_repo(run_ids, protocol_id),
        query=data,
        dispatcher=AsyncMock(),
    )


def _cmd(auth, campaign, run_ids, *configs, **kw) -> AddResultsFromRunsCommand:
    return AddResultsFromRunsCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign.id,
        run_ids=list(run_ids),
        channel_configs=list(configs),
        **kw,
    )


class TestAddResultsFromRuns:
    @pytest.mark.asyncio
    async def test_unauthorized(self) -> None:
        auth = fake_auth(role="viewer")
        uc = _uc(None, FakeRunData(), [])
        with pytest.raises(AuthorizationError):
            await uc(_cmd(auth, SimpleNamespace(id=uuid.uuid4()), [uuid.uuid4()]), auth=auth)

    @pytest.mark.asyncio
    async def test_locked_campaign_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        campaign.status = CampaignStatus.CLOSED  # type: ignore[misc]
        run_id = uuid.uuid4()
        out = await _uc(campaign, FakeRunData(), [run_id])(
            _cmd(auth, campaign, [run_id], _config(uuid.uuid4())), auth=auth
        )
        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_unknown_stage_id_is_not_found(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        run_id = uuid.uuid4()
        out = await _uc(campaign, FakeRunData(), [run_id])(
            _cmd(auth, campaign, [run_id], _config(uuid.uuid4()), stage_id=uuid.uuid4()),
            auth=auth,
        )
        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        assert campaign.seed_runs == []

    @pytest.mark.asyncio
    async def test_hits_only_with_threshold_adds_only_hits(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        mol_hit, mol_miss = uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(readout, reading(mol_hit, 42.0, run_id), reading(mol_miss, 9000.0, run_id))
        out = await _uc(campaign, data, [run_id])(
            _cmd(auth, campaign, [run_id], _config(readout, lt=1000.0), scope="hits_only"),
            auth=auth,
        )
        assert isinstance(out, Success)
        outcome = out.unwrap()
        assert (outcome.added, outcome.channels_created, outcome.channels_reused) == (1, 1, 0)
        assert [r.molecule_id for r in campaign.results] == [mol_hit]

    @pytest.mark.asyncio
    async def test_scope_all_adds_everyone(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        m1, m2 = uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(readout, reading(m1, 100.0, run_id), reading(m2, 5000.0, run_id))
        out = await _uc(campaign, data, [run_id])(
            _cmd(auth, campaign, [run_id], _config(readout), scope="all"), auth=auth
        )
        assert isinstance(out, Success)
        assert out.unwrap().added == 2
        assert {r.molecule_id for r in campaign.results} == {m1, m2}
        # Without a stage: campaign runs, campaign columns.
        assert campaign.seed_runs == [SeedRun(run_id, PROTO)]
        assert [c.stage_id for c in campaign.channels] == [None]

    @pytest.mark.asyncio
    async def test_channel_reuse_when_matching_exists(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        existing = _channel(campaign, readout)
        data = FakeRunData()
        data.add(readout, reading(uuid.uuid4(), 10.0, run_id))
        out = await _uc(campaign, data, [run_id])(
            _cmd(
                auth,
                campaign,
                [run_id],
                _config(readout, SelectionRule.MEAN_ACROSS_RUNS, lt=500.0),
                scope="all",
            ),
            auth=auth,
        )
        assert isinstance(out, Success)
        assert (out.unwrap().channels_reused, out.unwrap().channels_created) == (1, 0)
        # Same column; the config's rule is applied, the threshold is never saved on it.
        assert campaign.channels == [existing]
        assert existing.selection_rule == SelectionRule.MEAN_ACROSS_RUNS

    @pytest.mark.asyncio
    async def test_idempotent_rerun_does_not_duplicate(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, run_id, mol = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(readout, reading(mol, 42.0, run_id))
        uc = _uc(campaign, data, [run_id])
        cmd = _cmd(auth, campaign, [run_id], _config(readout, lt=1000.0), scope="hits_only")
        assert (await uc(cmd, auth=auth)).unwrap().added == 1
        again = (await uc(cmd, auth=auth)).unwrap()
        assert (again.added, again.skipped) == (0, 1)
        assert len(campaign.results) == 1
        assert len(campaign.results[0].measurements) == 1

    @pytest.mark.asyncio
    async def test_existing_rows_recompute_and_overrides_survive(self) -> None:
        """Every add recomputes the target column for every row it already has;
        a manual override is never rewritten."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        mol, kept = uuid.uuid4(), uuid.uuid4()
        channel = _channel(campaign, readout)
        old = {}
        for m, override in ((mol, False), (kept, True)):
            row = CampaignResult(campaign_id=campaign.id, molecule_id=m)
            cell = CampaignMeasurement(
                result_id=row.id,
                channel_id=channel.id,
                value=11.0,
                value_qualifier=ValueQualifier.EQ,
                unit="nM",
                protocol_name_snapshot="OLD",
                protocol_version_snapshot=1,
            )
            if override:
                cell.mark_manual_override("reviewer correction")
            row.add_measurement(cell)
            campaign.add_result(row)
            old[m] = cell
        data = FakeRunData()
        data.add(readout, reading(mol, 42.0, run_id), reading(kept, 42.0, run_id))

        out = await _uc(campaign, data, [run_id])(
            _cmd(auth, campaign, [run_id], _config(readout), scope="all"), auth=auth
        )

        assert isinstance(out, Success)
        assert (out.unwrap().added, out.unwrap().skipped) == (0, 2)
        by_mol = {r.molecule_id: r.find_measurement(channel.id) for r in campaign.results}
        assert (by_mol[mol].value, by_mol[mol].id) == (42.0, old[mol].id)
        assert by_mol[kept] is old[kept]
        assert by_mol[kept].value == 11.0

    @pytest.mark.asyncio
    async def test_all_use_for_filter_false_with_hits_only_adds_zero(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(readout, reading(uuid.uuid4(), 42.0, run_id))
        out = await _uc(campaign, data, [run_id])(
            _cmd(
                auth,
                campaign,
                [run_id],
                _config(readout, lt=1000.0, use_for_filter=False),
                scope="hits_only",
            ),
            auth=auth,
        )
        assert isinstance(out, Success)
        assert out.unwrap().added == 0

    @pytest.mark.asyncio
    async def test_facts_populate_on_new_measurement(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, mol = uuid.uuid4(), uuid.uuid4()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(readout, reading(mol, 10.0, r1), reading(mol, 14.0, r2))
        out = await _uc(campaign, data, [r1, r2])(
            _cmd(
                auth,
                campaign,
                [r1, r2],
                _config(readout, SelectionRule.MEAN_ACROSS_RUNS),
                scope="all",
            ),
            auth=auth,
        )
        assert isinstance(out, Success)
        [cell] = campaign.results[0].measurements
        assert cell.value == pytest.approx(12.0)
        assert cell.replicate_count == 2
        assert set(cell.contributing_run_ids) == {r1, r2}
        assert cell.basis == MeasurementBasis.MEASURED

    # ------------------------------------------------------------------
    # seed runs (spec D4) — every input run is recorded, on every call
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_every_input_run_is_recorded_even_when_its_value_never_wins(self) -> None:
        """Latest-run rule over two runs: the cell names one run, both are seed
        runs, in the order the chemist selected them."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, mol = uuid.uuid4(), uuid.uuid4()
        r_old, r_new = uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(
            readout,
            reading(mol, 10.0, r_old, run_date=date(2026, 1, 1)),
            reading(mol, 14.0, r_new, run_date=date(2026, 6, 1)),
        )
        out = await _uc(campaign, data, [r_old, r_new])(
            _cmd(auth, campaign, [r_new, r_old], _config(readout), scope="all"), auth=auth
        )
        assert isinstance(out, Success)
        assert campaign.results[0].measurements[0].source_run_id == r_new
        assert campaign.seed_runs == [SeedRun(r_new, PROTO), SeedRun(r_old, PROTO)]
        # The row is attributed to the earliest run it was measured in.
        assert campaign.results[0].added_from == RunRef(run_id=r_old)

    @pytest.mark.asyncio
    async def test_adding_a_run_to_existing_rows_widens_the_seed_set(self) -> None:
        """Adding run R2 adds no row but must widen the seed set, and the cell
        reads both runs."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, mol = uuid.uuid4(), uuid.uuid4()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        campaign.add_runs_to_stage([SeedRun(r1, PROTO)], None)
        channel = _channel(campaign, readout)
        campaign.add_result(CampaignResult(campaign_id=campaign.id, molecule_id=mol))
        data = FakeRunData()
        data.add(
            readout,
            reading(mol, 10.0, r1, run_date=date(2026, 1, 1)),
            reading(mol, 42.0, r2, run_date=date(2026, 2, 1)),
        )
        out = await _uc(campaign, data, [r2])(
            _cmd(auth, campaign, [r2], _config(readout, SelectionRule.MEAN_ACROSS_RUNS)),
            auth=auth,
        )
        assert isinstance(out, Success)
        assert out.unwrap().added == 0
        assert campaign.results[0].find_measurement(channel.id).value == pytest.approx(26.0)
        assert campaign.campaign_run_ids(PROTO) == [r1, r2]

    @pytest.mark.asyncio
    async def test_hits_only_import_that_adds_no_row_still_records_the_run(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(readout, reading(uuid.uuid4(), 9000.0, run_id))
        out = await _uc(campaign, data, [run_id])(
            _cmd(auth, campaign, [run_id], _config(readout, lt=100.0), scope="hits_only"),
            auth=auth,
        )
        assert isinstance(out, Success)
        assert out.unwrap().added == 0
        assert campaign.results == []
        assert campaign.seed_runs == [SeedRun(run_id, PROTO)]

    # ------------------------------------------------------------------
    # stage_name
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_stage_created_with_criteria_bound_to_channels(self) -> None:
        """stage_name + N filtering configs -> one stage owning the runs and the
        columns, one criterion per config bound to its column."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        ic50, cc50, run_id, mol = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(ic50, reading(mol, 42.0, run_id))
        data.add(cc50, reading(mol, 7.0, run_id))
        cc50_cfg = ChannelImportConfig(
            protocol_id=PROTO,
            readout_definition_id=cc50,
            label="CC50",
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.LATEST_RUN,
            hit_threshold=HitCriterion(readout_name="CC50", operator="gt", value=5.0),
        )
        out = await _uc(campaign, data, [run_id])(
            _cmd(
                auth,
                campaign,
                [run_id],
                _config(ic50, lt=1000.0),
                cc50_cfg,
                scope="all",
                stage_name="Primary Hits",
            ),
            auth=auth,
        )
        assert isinstance(out, Success)
        assert out.unwrap().stage_created is True
        [stage] = campaign.stages
        assert (stage.name, stage.parent_stage_id) == ("Primary Hits", None)
        assert campaign.seed_runs == [SeedRun(run_id, PROTO, (stage.id,))]
        by_readout = {c.readout_definition_id: c for c in campaign.channels}
        assert {c.stage_id for c in campaign.channels} == {stage.id}
        assert stage.criteria == [
            StageCriterion(channel_id=by_readout[ic50].id, operator="lt", value=1000.0),
            StageCriterion(channel_id=by_readout[cc50].id, operator="gt", value=5.0),
        ]

    @pytest.mark.asyncio
    async def test_stage_name_without_thresholds_still_creates_the_stage(self) -> None:
        """stage_name behaves as in mirror-protocol (§10): the stage is created and
        owns the runs and columns; with no threshold it has no criteria."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(readout, reading(uuid.uuid4(), 42.0, run_id))
        out = await _uc(campaign, data, [run_id])(
            _cmd(auth, campaign, [run_id], _config(readout), scope="all", stage_name="Primary"),
            auth=auth,
        )
        assert isinstance(out, Success)
        assert out.unwrap().stage_created is True
        [stage] = campaign.stages
        assert stage.criteria == []
        assert [c.stage_id for c in campaign.channels] == [stage.id]

    @pytest.mark.asyncio
    async def test_stage_skips_in_operator_configs(self) -> None:
        """A config using the string-based 'in' operator contributes no criterion
        (StageCriterion doesn't support it); the numeric config still does."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        ic50, klass, run_id, mol = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(ic50, reading(mol, 42.0, run_id))
        data.add(klass, reading(mol, 7.0, run_id))
        in_cfg = ChannelImportConfig(
            protocol_id=PROTO,
            readout_definition_id=klass,
            label="Curve Class",
            source_kind=ChannelSourceKind.READOUT_DATA,
            selection_rule=SelectionRule.LATEST_RUN,
            hit_threshold=HitCriterion(readout_name="Curve Class", operator="in", value=["full"]),
        )
        out = await _uc(campaign, data, [run_id])(
            _cmd(
                auth,
                campaign,
                [run_id],
                _config(ic50, lt=1000.0),
                in_cfg,
                scope="all",
                stage_name="Primary Hits",
            ),
            auth=auth,
        )
        assert isinstance(out, Success)
        [stage] = campaign.stages
        ic50_channel = next(c for c in campaign.channels if c.readout_definition_id == ic50)
        assert [c.channel_id for c in stage.criteria] == [ic50_channel.id]

    @pytest.mark.asyncio
    async def test_stage_name_reuses_existing_stage(self) -> None:
        """Re-importing under a name already on the campaign rewrites that stage's
        criteria instead of failing on the uniqueness rule."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        existing = CampaignStage(campaign_id=campaign.id, name="Primary Hits", display_order=0)
        campaign.add_stage(existing)
        other = _channel(campaign, uuid.uuid4(), stage_id=existing.id)
        campaign.update_stage(
            existing.id,
            criteria=[StageCriterion(channel_id=other.id, operator="lt", value=1.0)],
        )
        data = FakeRunData()
        data.add(readout, reading(uuid.uuid4(), 42.0, run_id))
        out = await _uc(campaign, data, [run_id])(
            _cmd(
                auth,
                campaign,
                [run_id],
                _config(readout, lt=1000.0),
                scope="all",
                stage_name="primary HITS",
            ),
            auth=auth,
        )
        assert isinstance(out, Success)
        assert out.unwrap().stage_created is False
        assert campaign.stages == [existing]
        imported = next(c for c in campaign.channels if c.readout_definition_id == readout)
        assert existing.criteria == [
            StageCriterion(channel_id=imported.id, operator="lt", value=1000.0)
        ]

    @pytest.mark.asyncio
    async def test_stage_created_under_parent_stage_id(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        parent = CampaignStage(campaign_id=campaign.id, name="Triage", display_order=0)
        campaign.add_stage(parent)
        data = FakeRunData()
        data.add(readout, reading(uuid.uuid4(), 42.0, run_id))
        out = await _uc(campaign, data, [run_id])(
            _cmd(
                auth,
                campaign,
                [run_id],
                _config(readout, lt=1000.0),
                scope="all",
                stage_name="Primary Hits",
                parent_stage_id=parent.id,
            ),
            auth=auth,
        )
        assert isinstance(out, Success)
        child = next(s for s in campaign.stages if s.name == "Primary Hits")
        assert child.parent_stage_id == parent.id

    @pytest.mark.asyncio
    async def test_unknown_parent_stage_id_returns_failure(self) -> None:
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        out = await _uc(campaign, FakeRunData(), [run_id])(
            _cmd(
                auth,
                campaign,
                [run_id],
                _config(readout, lt=1000.0),
                scope="all",
                stage_name="Primary Hits",
                parent_stage_id=uuid.uuid4(),
            ),
            auth=auth,
        )
        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        assert campaign.stages == []

    # ---- D1 and the curve-class row filter ----

    @pytest.mark.asyncio
    async def test_dr_config_falls_back_to_endpoint_when_molecule_has_no_curve(self) -> None:
        """A dose-response column takes a reported endpoint only for a compound with
        no fitted curve; a compound with a curve keeps the curve."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, run_id = uuid.uuid4(), uuid.uuid4()
        mol_curve, mol_endpoint = uuid.uuid4(), uuid.uuid4()
        curve = reading(mol_curve, 10.0, run_id, unit="nM", curve_class="full")
        endpoint = reading(mol_endpoint, 32.0, run_id, unit="nM", well=False)
        data = FakeRunData()
        data.add(
            readout, curve, reading(mol_curve, 999.0, run_id, unit="nM", well=False), endpoint
        )
        out = await _uc(campaign, data, [run_id])(
            _cmd(
                auth,
                campaign,
                [run_id],
                _config(readout, kind=ChannelSourceKind.DOSE_RESPONSE_CURVE),
                scope="all",
            ),
            auth=auth,
        )
        assert isinstance(out, Success)
        assert out.unwrap().added == 2
        by_mol = {r.molecule_id: r.measurements[0] for r in campaign.results}
        assert (by_mol[mol_endpoint].value, by_mol[mol_endpoint].source_readout_id) == (
            32.0,
            endpoint.run.readout_id,
        )
        assert (by_mol[mol_curve].value, by_mol[mol_curve].source_curve_id) == (
            10.0,
            curve.run.curve_id,
        )

    @pytest.mark.asyncio
    async def test_allowed_curve_classes_is_a_row_filter_only(self) -> None:
        """allowed_curve_classes decides which compounds are added — a compound whose
        every curve is out of class is skipped, an endpoint-only one is not — and
        never which values a cell reads."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        readout, r1, r2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        out_of_class, endpoint_only, mixed = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        data = FakeRunData()
        data.add(
            readout,
            reading(out_of_class, 10.0, r1, unit="nM", curve_class="inactive"),
            reading(endpoint_only, 32.0, r1, unit="nM", well=False),
            reading(mixed, 5.0, r1, unit="nM", curve_class="full", run_date=date(2026, 1, 1)),
            reading(mixed, 7.0, r2, unit="nM", curve_class="partial", run_date=date(2026, 2, 1)),
        )
        out = await _uc(campaign, data, [r1, r2])(
            _cmd(
                auth,
                campaign,
                [r1, r2],
                _config(
                    readout,
                    kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
                    allowed_curve_classes=["full"],
                ),
                scope="all",
            ),
            auth=auth,
        )
        assert isinstance(out, Success)
        by_mol = {r.molecule_id: r.measurements[0] for r in campaign.results}
        assert set(by_mol) == {endpoint_only, mixed}
        assert by_mol[endpoint_only].value == 32.0
        # The latest curve wins although its class is not in the allowed set.
        assert by_mol[mixed].value == 7.0

    # ---- every column whose run scope the add changes is recomputed (§6.3, G5) ----

    @pytest.mark.asyncio
    async def test_add_from_runs_recomputes_sibling_intercept_column(self) -> None:
        """Mirror-protocol made IC50 and IC90 on the stage before it had runs (IC90 is
        untested, no runs at stage). An add naming only IC50 still resolves IC90, for
        the existing row and the new one."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        stage = CampaignStage(campaign_id=campaign.id, name="Confirmation", display_order=0)
        campaign.add_stage(stage)
        readout, run_id, old_mol, new_mol = (uuid.uuid4() for _ in range(4))
        columns = {}
        for name, key in (("IC50", None), ("IC90", InterceptKey(kind="ic", level=90.0))):
            columns[name] = CampaignChannel(
                campaign_id=campaign.id,
                label=name,
                display_order=len(campaign.channels),
                protocol_id=PROTO,
                readout_definition_id=readout,
                source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
                selection_rule=SelectionRule.LATEST_RUN,
                qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
                intercept_key=key,
                stage_id=stage.id,
            )
            campaign.add_channel(columns[name])
        row = CampaignResult(campaign_id=campaign.id, molecule_id=old_mol)
        untested = CampaignMeasurement(
            result_id=row.id,
            channel_id=columns["IC90"].id,
            value=None,
            value_qualifier=ValueQualifier.ND,
            unit="-",
            protocol_name_snapshot="-",
            protocol_version_snapshot=0,
            unresolved_reason=UnresolvedReason.NO_RUNS_AT_STAGE,
        )
        row.add_measurement(untested)
        campaign.add_result(row)
        ivs = [
            {"spec": {"kind": "ic", "level": 50.0}, "value": 2.0},
            {"spec": {"kind": "ic", "level": 90.0}, "value": 8.0},
        ]
        data = FakeRunData()
        for mol in (old_mol, new_mol):
            data.add(
                readout,
                reading(mol, 2.0, run_id, unit="µM", curve_class="full", intercept_values=ivs),
            )

        out = await _uc(campaign, data, [run_id])(
            _cmd(
                auth,
                campaign,
                [run_id],
                _config(readout, kind=ChannelSourceKind.DOSE_RESPONSE_CURVE),
                scope="all",
                stage_id=stage.id,
            ),
            auth=auth,
        )

        assert isinstance(out, Success)
        assert len(campaign.channels) == 2
        for result in campaign.results:
            ic90 = result.find_measurement(columns["IC90"].id)
            assert ic90 is not None, result.molecule_id
            assert (ic90.value, ic90.unresolved_reason) == (8.0, None)
            assert result.find_measurement(columns["IC50"].id).value == 2.0
        assert campaign.results[0].find_measurement(columns["IC90"].id).id == untested.id
        # One fetch per column for the recompute (plus the config's row lookup).
        fetched = [channel_id for channel_id, _, _ in data.calls]
        assert fetched.count(columns["IC90"].id) == 1

    @pytest.mark.asyncio
    async def test_add_from_runs_recomputes_campaign_columns_of_that_protocol(self) -> None:
        """A run added to a stage is also a campaign run of its protocol, so the
        protocol's campaign columns read it: the old row is recomputed and the new
        row gets a cell there too."""
        auth = fake_auth()
        campaign = _draft_campaign(auth.workspace_id)
        stage = CampaignStage(campaign_id=campaign.id, name="Primary", display_order=0)
        campaign.add_stage(stage)
        reference, staged, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        old_mol, new_mol = uuid.uuid4(), uuid.uuid4()
        campaign_column = _channel(campaign, reference)
        row = CampaignResult(campaign_id=campaign.id, molecule_id=old_mol)
        row.add_measurement(
            CampaignMeasurement(
                result_id=row.id,
                channel_id=campaign_column.id,
                value=11.0,
                value_qualifier=ValueQualifier.EQ,
                unit="%",
                protocol_name_snapshot="OLD",
                protocol_version_snapshot=1,
            )
        )
        campaign.add_result(row)
        data = FakeRunData()
        data.add(staged, reading(old_mol, 1.0, run_id), reading(new_mol, 2.0, run_id))
        data.add(reference, reading(old_mol, 42.0, run_id), reading(new_mol, 43.0, run_id))

        out = await _uc(campaign, data, [run_id])(
            _cmd(auth, campaign, [run_id], _config(staged), scope="all", stage_id=stage.id),
            auth=auth,
        )

        assert isinstance(out, Success)
        values = {
            r.molecule_id: r.find_measurement(campaign_column.id).value for r in campaign.results
        }
        assert values == {old_mol: 42.0, new_mol: 43.0}
