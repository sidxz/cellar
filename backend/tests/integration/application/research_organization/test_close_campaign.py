"""Integration test for CloseCampaign / ReopenCampaign use cases.

Exercises the full SQL+session+flush path:
  - inserts a Molecule + Protocol + Campaign in DRAFT,
  - runs CloseCampaign with a FakeResolver (no real runs/curves needed),
  - asserts campaign is CLOSED, source_protocols populated, close_note
    persisted, and no Collection row is created (soft close publishes
    nothing — spec §4/§5),
  - reopens the closed campaign via ReopenCampaign and asserts it round-trips
    back to DRAFT with close metadata cleared.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from returns.result import Success

from cellar.application.research_organization.channel_resolution import ChannelResolver
from cellar.application.research_organization.close_campaign import (
    CloseCampaign,
    CloseCampaignCommand,
)
from cellar.application.research_organization.refresh_campaign_from_sources import (
    RefreshFromSources,
    RefreshFromSourcesCommand,
)
from cellar.application.research_organization.reopen_campaign import (
    ReopenCampaign,
    ReopenCampaignCommand,
)
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
from cellar.domain.research_organization.source_ref import RunRef, SeedRun
from cellar.domain.screening_assay.enums import (
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
)
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (
    SQLAlchemyCampaignRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query import (
    SQLAlchemyChannelResolutionQuery,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _insert_molecule(
    uow: AsyncUnitOfWork, mol_id: uuid.UUID, ws_id: uuid.UUID
) -> None:
    """Insert a minimal molecule row (mirrors existing integration test helpers)."""
    org_id = ws_id
    async with uow:
        await uow.session.execute(
            sa.text(
                "INSERT INTO organizations (id, workspace_id, name, org_type, "
                "is_active, version) "
                "VALUES (:id, :ws, 'Test Org', 'internal', true, 1) "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": org_id, "ws": ws_id},
        )
        await uow.session.execute(
            sa.text(
                "INSERT INTO molecules (id, workspace_id, name, molecule_type, "
                "structure_status, registration_status, synthesis_status, "
                "lifecycle_stage, registration_number, originating_org_id, version) "
                "VALUES (:id, :ws, 'Test Mol', 'small_molecule', 'disclosed', "
                "'approved', 'virtual', 'registered', :reg, :org, 1)"
            ),
            {"id": mol_id, "ws": ws_id, "reg": f"CV-{mol_id.hex[:6]}", "org": org_id},
        )
        await uow.commit()


async def _insert_project(
    uow: AsyncUnitOfWork, project_id: uuid.UUID, ws_id: uuid.UUID
) -> None:
    """Insert a minimal project row."""
    async with uow:
        await uow.session.execute(
            sa.text(
                "INSERT INTO projects (id, workspace_id, name, status, created_by, version) "
                "VALUES (:id, :ws, 'Test Project', 'active', :cb, 1) "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": project_id, "ws": ws_id, "cb": uuid.uuid4()},
        )
        await uow.commit()


async def _insert_protocol(
    uow: AsyncUnitOfWork,
    ws_id: uuid.UUID,
    protocol_id: uuid.UUID,
    readout_id: uuid.UUID,
    *,
    readout_unit: str = "uM",
) -> None:
    """Insert a Protocol with one ReadoutDefinition via the domain repo."""
    rd = ReadoutDefinition(
        id=readout_id,
        protocol_id=protocol_id,
        name="IC50",
        data_type=ReadoutDataType.NUMERIC,
        unit=readout_unit,
        aggregation=ReadoutAggregation.NONE,
    )
    protocol = Protocol(
        id=protocol_id,
        workspace_id=ws_id,
        name="Test Protocol",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        readout_definitions=[rd],
    )
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        await repo.save(protocol)
        await uow.commit()


class _FakeResolver:
    """Returns a fresh measurement (value=99.0, unit='uM') for any cell."""

    async def resolve(
        self, *, workspace_id, channel, result_id, molecule_id, run_ids=None
    ) -> CampaignMeasurement:
        return CampaignMeasurement(
            result_id=result_id,
            channel_id=channel.id,
            value=99.0,
            value_qualifier=ValueQualifier.EQ,
            unit="uM",
            protocol_name_snapshot="Test Protocol",
            protocol_version_snapshot=1,
        )


class _NoOpDispatcher:
    async def dispatch_all(self, events) -> None:  # type: ignore[type-arg]
        pass


def _make_fake_auth(user_id: uuid.UUID, ws_id: uuid.UUID) -> AsyncMock:
    """Minimal editor AuthContext double."""
    auth = AsyncMock()
    auth.user_id = user_id
    auth.workspace_id = ws_id
    auth.workspace_role = "editor"
    auth.is_admin = False
    rank = {"viewer": 0, "editor": 1, "admin": 2}
    auth.has_role = lambda min_role: rank.get("editor", 0) >= rank.get(min_role, 0)
    return auth


async def _seed_and_close_campaign(
    session_factory,
    *,
    note: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Seed a DRAFT campaign (1 channel/result/measurement) and close it via
    the real use case. Returns (workspace_id, campaign_id, protocol_id, user_id)."""
    ws_id = uuid.uuid4()
    mol_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    readout_id = uuid.uuid4()
    project_id = uuid.uuid4()

    uow = AsyncUnitOfWork(session_factory)
    await _insert_molecule(uow, mol_id, ws_id)
    await _insert_project(uow, project_id, ws_id)
    await _insert_protocol(uow, ws_id, protocol_id, readout_id, readout_unit="uM")

    campaign = Campaign.create(
        workspace_id=ws_id,
        project_id=project_id,
        name="Integration Close Test",
        description=None,
        created_by=uuid.uuid4(),
    )
    ch = CampaignChannel(
        campaign_id=campaign.id,
        label="IC50",
        protocol_id=protocol_id,
        readout_definition_id=readout_id,
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    campaign.add_channel(ch)
    result = CampaignResult(campaign_id=campaign.id, molecule_id=mol_id)
    result.add_measurement(
        CampaignMeasurement(
            result_id=result.id,
            channel_id=ch.id,
            value=10.0,
            value_qualifier=ValueQualifier.EQ,
            unit="uM",
            protocol_name_snapshot="Test Protocol",
            protocol_version_snapshot=1,
        )
    )
    campaign.add_result(result)

    async with AsyncUnitOfWork(session_factory) as uow_seed:
        repo = SQLAlchemyCampaignRepository(uow_seed)
        await repo.save(campaign)
        await uow_seed.commit()

    # --- Execute CloseCampaign use case ---
    user_id = uuid.uuid4()
    cmd = CloseCampaignCommand(
        workspace_id=ws_id,
        campaign_id=campaign.id,
        user_id=user_id,
        note=note,
    )

    uow_uc = AsyncUnitOfWork(session_factory)
    uc = CloseCampaign(
        uow=uow_uc,
        campaign_repo=SQLAlchemyCampaignRepository(uow_uc),
        protocol_repo=SQLAlchemyProtocolRepository(uow_uc),
        resolver=_FakeResolver(),
        dispatcher=_NoOpDispatcher(),  # type: ignore[arg-type]
    )
    auth = _make_fake_auth(user_id, ws_id)
    out = await uc(cmd, auth=auth)
    assert isinstance(out, Success), f"Expected Success, got {out}"

    return ws_id, campaign.id, protocol_id, user_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_campaign_integration(session_factory) -> None:
    """Full DB round-trip: close persists status/source_protocols/close_note
    and creates no Collection row — soft close publishes nothing."""
    ws_id, campaign_id, protocol_id, _user_id = await _seed_and_close_campaign(
        session_factory, note="Confirmed by wet lab"
    )

    async with AsyncUnitOfWork(session_factory) as uow_check:
        camp_repo = SQLAlchemyCampaignRepository(uow_check)
        reloaded = await camp_repo.find_by_id_in_workspace(ws_id, campaign_id)

    assert reloaded is not None
    assert reloaded.status == CampaignStatus.CLOSED
    assert len(reloaded.source_protocols) == 1
    assert reloaded.source_protocols[0]["id"] == str(protocol_id)
    assert reloaded.close_note == "Confirmed by wet lab"

    # No Collection row was created for this campaign — soft close publishes
    # nothing (spec §4/§5).
    async with AsyncUnitOfWork(session_factory) as uow_coll:
        row_count = (
            await uow_coll.session.execute(
                sa.text(
                    "SELECT count(*) FROM collections WHERE derived_from_campaign_id = :cid"
                ),
                {"cid": campaign_id},
            )
        ).scalar_one()
    assert row_count == 0


@pytest.mark.asyncio
async def test_reopen_campaign_integration(session_factory) -> None:
    """close -> ReopenCampaign round-trips the campaign back to DRAFT in the DB."""
    ws_id, campaign_id, _protocol_id, user_id = await _seed_and_close_campaign(
        session_factory, note="first pass"
    )

    reopen_cmd = ReopenCampaignCommand(
        workspace_id=ws_id,
        campaign_id=campaign_id,
        user_id=user_id,
        reason="late confirmation result",
    )
    uow_reopen = AsyncUnitOfWork(session_factory)
    reopen_uc = ReopenCampaign(
        uow=uow_reopen,
        campaign_repo=SQLAlchemyCampaignRepository(uow_reopen),
        dispatcher=_NoOpDispatcher(),  # type: ignore[arg-type]
    )
    auth = _make_fake_auth(user_id, ws_id)
    out = await reopen_uc(reopen_cmd, auth=auth)
    assert isinstance(out, Success), f"Expected Success, got {out}"

    async with AsyncUnitOfWork(session_factory) as uow_check:
        camp_repo = SQLAlchemyCampaignRepository(uow_check)
        reloaded = await camp_repo.find_by_id_in_workspace(ws_id, campaign_id)

    assert reloaded is not None
    assert reloaded.status == CampaignStatus.DRAFT
    assert reloaded.closed_at is None
    assert reloaded.closed_by is None
    assert reloaded.close_note is None


@pytest.mark.asyncio
async def test_stage_writes_blocked_while_closed_then_allowed_after_reopen(
    session_factory,
) -> None:
    """spec §11: the migration-074 DB triggers are the last line of defence
    behind the application-level DataLockedError check — assert them
    directly. A raw INSERT into campaign_stage / campaign_stage_override
    against a closed campaign fails with check_violation ("writes
    blocked"); after ReopenCampaign, the same inserts succeed. Each attempt
    uses its own UoW: Postgres aborts the whole transaction on the first
    error, so a second statement on the same session would fail regardless
    of the trigger."""
    ws_id, campaign_id, _protocol_id, user_id = await _seed_and_close_campaign(
        session_factory, note="closing for trigger test"
    )

    async with AsyncUnitOfWork(session_factory) as uow_check:
        camp_repo = SQLAlchemyCampaignRepository(uow_check)
        reloaded = await camp_repo.find_by_id_in_workspace(ws_id, campaign_id)
    result_id = reloaded.results[0].id

    # --- blocked: campaign_stage --------------------------------------
    async with AsyncUnitOfWork(session_factory) as uow:
        with pytest.raises(sa.exc.IntegrityError) as exc_info:
            await uow.session.execute(
                sa.text(
                    "INSERT INTO campaign_stage (id, campaign_id, name) "
                    "VALUES (:id, :campaign_id, 'Trigger Test Stage')"
                ),
                {"id": uuid.uuid4(), "campaign_id": campaign_id},
            )
        assert "writes blocked" in str(exc_info.value)
        await uow.rollback()

    # --- blocked: campaign_stage_override ------------------------------
    # stage_id need not reference a real row: the trigger only joins
    # campaign_result -> campaign on result_id and fires before any FK is
    # checked, so it raises before the (nonexistent) stage_id ever matters.
    async with AsyncUnitOfWork(session_factory) as uow:
        with pytest.raises(sa.exc.IntegrityError) as exc_info:
            await uow.session.execute(
                sa.text(
                    "INSERT INTO campaign_stage_override "
                    "(id, result_id, stage_id, forced_outcome, reason, overridden_by, "
                    "overridden_at) "
                    "VALUES (:id, :result_id, :stage_id, 'hit', 'trigger test', "
                    ":overridden_by, now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "result_id": result_id,
                    "stage_id": uuid.uuid4(),
                    "overridden_by": user_id,
                },
            )
        assert "writes blocked" in str(exc_info.value)
        await uow.rollback()

    # --- reopen ---------------------------------------------------------
    reopen_cmd = ReopenCampaignCommand(
        workspace_id=ws_id,
        campaign_id=campaign_id,
        user_id=user_id,
        reason="reopen for trigger test",
    )
    uow_reopen = AsyncUnitOfWork(session_factory)
    reopen_uc = ReopenCampaign(
        uow=uow_reopen,
        campaign_repo=SQLAlchemyCampaignRepository(uow_reopen),
        dispatcher=_NoOpDispatcher(),  # type: ignore[arg-type]
    )
    auth = _make_fake_auth(user_id, ws_id)
    out = await reopen_uc(reopen_cmd, auth=auth)
    assert isinstance(out, Success), f"Expected Success, got {out}"

    # --- allowed: campaign_stage ----------------------------------------
    new_stage_id = uuid.uuid4()
    async with AsyncUnitOfWork(session_factory) as uow:
        await uow.session.execute(
            sa.text(
                "INSERT INTO campaign_stage (id, campaign_id, name) "
                "VALUES (:id, :campaign_id, 'Trigger Test Stage')"
            ),
            {"id": new_stage_id, "campaign_id": campaign_id},
        )
        await uow.commit()

    # --- allowed: campaign_stage_override, referencing the real stage ---
    async with AsyncUnitOfWork(session_factory) as uow:
        await uow.session.execute(
            sa.text(
                "INSERT INTO campaign_stage_override "
                "(id, result_id, stage_id, forced_outcome, reason, overridden_by, "
                "overridden_at) "
                "VALUES (:id, :result_id, :stage_id, 'hit', 'trigger test', "
                ":overridden_by, now())"
            ),
            {
                "id": uuid.uuid4(),
                "result_id": result_id,
                "stage_id": new_stage_id,
                "overridden_by": user_id,
            },
        )
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow_verify:
        stage_count = (
            await uow_verify.session.execute(
                sa.text("SELECT count(*) FROM campaign_stage WHERE id = :id"),
                {"id": new_stage_id},
            )
        ).scalar_one()
        override_count = (
            await uow_verify.session.execute(
                sa.text("SELECT count(*) FROM campaign_stage_override WHERE stage_id = :id"),
                {"id": new_stage_id},
            )
        ).scalar_one()
    assert stage_count == 1
    assert override_count == 1


async def _insert_run_with_readout(  # type: ignore[no-untyped-def]
    session_factory,
    *,
    ws_id: uuid.UUID,
    protocol_id: uuid.UUID,
    readout_id: uuid.UUID,
    run_id: uuid.UUID,
    run_date: date,
    mol_id: uuid.UUID,
    value: float,
    user_id: uuid.UUID,
) -> None:
    """An approved run of ``protocol_id`` with one well-less readout row for ``mol_id``."""
    async with session_factory() as session, session.begin():
        await session.execute(
            sa.text(
                "INSERT INTO runs "
                "(id, workspace_id, protocol_id, run_date, operator, "
                "status, is_locked, version, notes) "
                "VALUES (:id, :ws, :proto, :run_date, :user, 'approved', false, 1, NULL)"
            ),
            {"id": run_id, "ws": ws_id, "proto": protocol_id, "run_date": run_date, "user": user_id},
        )
        await session.execute(
            sa.text(
                "INSERT INTO readout_data "
                "(id, workspace_id, run_id, well_id, molecule_id, "
                "batch_id, readout_definition_id, value_numeric, "
                "value_qualifier, is_outlier, is_computed, normalization_applied) "
                "VALUES (:id, :ws, :run, NULL, :mol, :batch, :rd, "
                ":value, '=', false, false, NULL)"
            ),
            {
                "id": uuid.uuid4(),
                "ws": ws_id,
                "run": run_id,
                "mol": mol_id,
                "batch": uuid.uuid4(),
                "rd": readout_id,
                "value": value,
            },
        )


def _readout_channel(
    campaign: Campaign,
    *,
    protocol_id: uuid.UUID,
    readout_id: uuid.UUID,
    rule: SelectionRule = SelectionRule.LATEST_APPROVED_RUN,
    display_order: int = 0,
) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=campaign.id,
        label="IC50",
        protocol_id=protocol_id,
        readout_definition_id=readout_id,
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=rule,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=display_order,
    )


class _RunScopeHarness:
    """One molecule, one project, the real resolver + SQL query, and the
    real Refresh / Close / Reopen use cases against ``session_factory``."""

    def __init__(self, session_factory) -> None:  # type: ignore[no-untyped-def]
        self.sf = session_factory
        self.ws_id = uuid.uuid4()
        self.mol_id = uuid.uuid4()
        self.project_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.auth = _make_fake_auth(self.user_id, self.ws_id)
        self.resolver = ChannelResolver(SQLAlchemyChannelResolutionQuery(session_factory))
        self.campaign: Campaign | None = None

    async def setup(self) -> None:
        uow = AsyncUnitOfWork(self.sf)
        await _insert_molecule(uow, self.mol_id, self.ws_id)
        await _insert_project(uow, self.project_id, self.ws_id)

    async def add_protocol(self, protocol_id: uuid.UUID, readout_id: uuid.UUID) -> None:
        await _insert_protocol(AsyncUnitOfWork(self.sf), self.ws_id, protocol_id, readout_id)

    async def add_run(
        self, protocol_id: uuid.UUID, readout_id: uuid.UUID, run_date: date, value: float
    ) -> uuid.UUID:
        run_id = uuid.uuid4()
        await _insert_run_with_readout(
            self.sf,
            ws_id=self.ws_id,
            protocol_id=protocol_id,
            readout_id=readout_id,
            run_id=run_id,
            run_date=run_date,
            mol_id=self.mol_id,
            value=value,
            user_id=self.user_id,
        )
        return run_id

    def new_campaign(self, name: str) -> Campaign:
        self.campaign = Campaign.create(
            workspace_id=self.ws_id,
            project_id=self.project_id,
            name=name,
            description=None,
            created_by=self.user_id,
        )
        self.campaign.add_result(
            CampaignResult(campaign_id=self.campaign.id, molecule_id=self.mol_id)
        )
        return self.campaign

    async def save(self) -> None:
        async with AsyncUnitOfWork(self.sf) as uow:
            await SQLAlchemyCampaignRepository(uow).save(self.campaign)
            await uow.commit()

    async def reload(self) -> Campaign:
        async with AsyncUnitOfWork(self.sf) as uow:
            c = await SQLAlchemyCampaignRepository(uow).find_by_id_in_workspace(
                self.ws_id, self.campaign.id
            )
        assert c is not None
        return c

    async def cell(self, channel_id: uuid.UUID) -> float | None:
        c = await self.reload()
        m = c.results[0].find_measurement(channel_id)
        assert m is not None
        return m.value

    async def refresh(self) -> None:
        uow = AsyncUnitOfWork(self.sf)
        uc = RefreshFromSources(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            resolver=self.resolver,
            dispatcher=_NoOpDispatcher(),  # type: ignore[arg-type]
        )
        out = await uc(
            RefreshFromSourcesCommand(workspace_id=self.ws_id, campaign_id=self.campaign.id),
            auth=self.auth,
        )
        assert isinstance(out, Success), f"Expected Success, got {out}"

    async def close(self) -> None:
        uow = AsyncUnitOfWork(self.sf)
        uc = CloseCampaign(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            protocol_repo=SQLAlchemyProtocolRepository(uow),
            resolver=self.resolver,
            dispatcher=_NoOpDispatcher(),  # type: ignore[arg-type]
        )
        out = await uc(
            CloseCampaignCommand(
                workspace_id=self.ws_id,
                campaign_id=self.campaign.id,
                user_id=self.user_id,
                note=None,
            ),
            auth=self.auth,
        )
        assert isinstance(out, Success), f"Expected Success, got {out}"

    async def reopen(self) -> None:
        uow = AsyncUnitOfWork(self.sf)
        uc = ReopenCampaign(
            uow=uow,
            campaign_repo=SQLAlchemyCampaignRepository(uow),
            dispatcher=_NoOpDispatcher(),  # type: ignore[arg-type]
        )
        out = await uc(
            ReopenCampaignCommand(
                workspace_id=self.ws_id,
                campaign_id=self.campaign.id,
                user_id=self.user_id,
                reason="late confirmation result",
            ),
            auth=self.auth,
        )
        assert isinstance(out, Success), f"Expected Success, got {out}"


@pytest.mark.asyncio
async def test_refresh_resolves_only_the_campaigns_seed_runs(session_factory) -> None:
    """Spec D4, end to end against real SQL: a campaign seeded from run A keeps
    run A's number when a newer run B of the same protocol lands. Flipping the
    channel's ``resolve_from_all_runs`` opt-out lets run B win.
    """
    h = _RunScopeHarness(session_factory)
    await h.setup()
    protocol_id, readout_id = uuid.uuid4(), uuid.uuid4()
    await h.add_protocol(protocol_id, readout_id)
    run_a = await h.add_run(protocol_id, readout_id, date(2026, 1, 1), 1.0)
    await h.add_run(protocol_id, readout_id, date(2026, 6, 1), 9.0)

    campaign = h.new_campaign("Run Scope")
    channel = _readout_channel(campaign, protocol_id=protocol_id, readout_id=readout_id)
    campaign.add_channel(channel)
    campaign.record_seed_runs([SeedRun(run_a, protocol_id)])
    await h.save()

    await h.refresh()
    assert await h.cell(channel.id) == 1.0, "Run B is outside the campaign's run scope"

    # Opt the channel out of the run scope — now the latest run wins.
    loaded = await h.reload()
    loaded.channels[0].resolve_from_all_runs = True
    h.campaign = loaded
    await h.save()

    await h.refresh()
    assert await h.cell(channel.id) == 9.0


@pytest.mark.asyncio
async def test_run_refs_alone_do_not_scope_resolution(session_factory) -> None:
    """A campaign whose rows carry RunRefs but which recorded no seed runs
    resolves protocol-wide (the D4 fallback for pre-079 data the backfill
    could not attribute)."""
    h = _RunScopeHarness(session_factory)
    await h.setup()
    protocol_id, readout_id = uuid.uuid4(), uuid.uuid4()
    await h.add_protocol(protocol_id, readout_id)
    run_a = await h.add_run(protocol_id, readout_id, date(2026, 1, 1), 1.0)
    await h.add_run(protocol_id, readout_id, date(2026, 6, 1), 9.0)

    campaign = h.new_campaign("RunRef only")
    channel = _readout_channel(campaign, protocol_id=protocol_id, readout_id=readout_id)
    campaign.add_channel(channel)
    campaign.results[0].added_from = RunRef(run_id=run_a)
    await h.save()

    await h.refresh()
    assert await h.cell(channel.id) == 9.0


@pytest.mark.asyncio
async def test_three_run_mean_survives_close_reopen_refresh(session_factory) -> None:
    """The C1 regression: a mean over three seed runs stays a three-run mean
    through close (which re-resolves every cell) → reopen → refresh, even
    though a fourth run of the protocol exists and no row's RunRef names
    runs 2 or 3."""
    h = _RunScopeHarness(session_factory)
    await h.setup()
    protocol_id, readout_id = uuid.uuid4(), uuid.uuid4()
    await h.add_protocol(protocol_id, readout_id)
    seed_runs = [
        await h.add_run(protocol_id, readout_id, date(2026, m, 1), float(v))
        for m, v in ((1, 1.0), (2, 2.0), (3, 3.0))
    ]
    await h.add_run(protocol_id, readout_id, date(2026, 6, 1), 90.0)  # not a seed run

    campaign = h.new_campaign("Three-run mean")
    channel = _readout_channel(
        campaign,
        protocol_id=protocol_id,
        readout_id=readout_id,
        rule=SelectionRule.MEAN_ACROSS_RUNS,
    )
    campaign.add_channel(channel)
    # As add-from-runs attributes it: the row names one run, the campaign all three.
    campaign.results[0].added_from = RunRef(run_id=seed_runs[0])
    campaign.record_seed_runs(SeedRun(r, protocol_id) for r in seed_runs)
    await h.save()

    await h.refresh()
    assert await h.cell(channel.id) == 2.0

    await h.close()
    assert (await h.reload()).status == CampaignStatus.CLOSED
    assert await h.cell(channel.id) == 2.0

    await h.reopen()
    await h.refresh()
    reloaded = await h.reload()
    assert reloaded.status == CampaignStatus.DRAFT
    assert reloaded.results[0].find_measurement(channel.id).value == 2.0


@pytest.mark.asyncio
async def test_channel_on_an_unseeded_protocol_resolves_protocol_wide(session_factory) -> None:
    """The I1 regression: a mirrored counter-screen on a protocol the campaign
    was never seeded from is not ND — it resolves against every run of its
    own protocol, while the seeded protocol's channel stays run-scoped."""
    h = _RunScopeHarness(session_factory)
    await h.setup()
    p1, r1 = uuid.uuid4(), uuid.uuid4()
    p2, r2 = uuid.uuid4(), uuid.uuid4()
    await h.add_protocol(p1, r1)
    await h.add_protocol(p2, r2)
    seed_run = await h.add_run(p1, r1, date(2026, 1, 1), 1.0)
    await h.add_run(p1, r1, date(2026, 6, 1), 9.0)
    await h.add_run(p2, r2, date(2026, 6, 1), 55.0)  # counter-screen, never a seed run

    campaign = h.new_campaign("Counter-screen")
    primary = _readout_channel(campaign, protocol_id=p1, readout_id=r1, display_order=0)
    counter = _readout_channel(campaign, protocol_id=p2, readout_id=r2, display_order=1)
    campaign.add_channel(primary)
    campaign.add_channel(counter)
    campaign.record_seed_runs([SeedRun(seed_run, p1)])
    await h.save()

    await h.refresh()
    assert await h.cell(primary.id) == 1.0
    assert await h.cell(counter.id) == 55.0
