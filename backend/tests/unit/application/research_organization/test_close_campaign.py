"""Unit tests for CloseCampaign use case."""

from __future__ import annotations

import uuid
from typing import Callable
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.close_campaign import (
    CloseCampaign,
    CloseCampaignCommand,
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
from cellar.domain.research_organization.events import CampaignClosed
from cellar.domain.research_organization.source_ref import RunRef
from cellar.domain.shared.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from tests.unit.application.research_organization._helpers import (
    FakeResolver,
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)


# ---------------------------------------------------------------------------
# Local builder helpers
# ---------------------------------------------------------------------------


def _make_channel(
    campaign_id: uuid.UUID,
    *,
    protocol_id: uuid.UUID | None = None,
    readout_definition_id: uuid.UUID | None = None,
    display_order: int = 0,
) -> CampaignChannel:
    return CampaignChannel(
        campaign_id=campaign_id,
        label=f"Channel-{display_order}",
        protocol_id=protocol_id or uuid.uuid4(),
        readout_definition_id=readout_definition_id or uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=display_order,
    )


def _make_measurement(
    result_id: uuid.UUID,
    channel_id: uuid.UUID,
    *,
    unit: str = "uM",
    value: float = 10.0,
    is_manual_override: bool = False,
) -> CampaignMeasurement:
    m = CampaignMeasurement(
        result_id=result_id,
        channel_id=channel_id,
        value=value,
        value_qualifier=ValueQualifier.EQ,
        unit=unit,
        protocol_name_snapshot="Proto",
        protocol_version_snapshot=1,
    )
    if is_manual_override:
        m.mark_manual_override()
    return m


def _build_campaign(
    workspace_id: uuid.UUID,
    *,
    n_channels: int = 1,
    n_results: int = 1,
    protocol_id: uuid.UUID | None = None,
    readout_definition_id: uuid.UUID | None = None,
    override_indices: set[tuple[int, int]] | None = None,
) -> tuple[Campaign, list[CampaignChannel], list[CampaignResult]]:
    """Build a DRAFT campaign with channels/results/measurements."""
    if override_indices is None:
        override_indices = set()

    campaign = Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Test Campaign",
        description=None,
        created_by=uuid.uuid4(),
    )

    channels: list[CampaignChannel] = []
    for ci in range(n_channels):
        ch = _make_channel(
            campaign.id,
            protocol_id=protocol_id,
            readout_definition_id=readout_definition_id,
            display_order=ci,
        )
        campaign.add_channel(ch)
        channels.append(ch)

    results: list[CampaignResult] = []
    for ri in range(n_results):
        result = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        for ci, ch in enumerate(channels):
            is_override = (ri, ci) in override_indices
            m = _make_measurement(result.id, ch.id, is_manual_override=is_override)
            result.add_measurement(m)
        campaign.add_result(result)
        results.append(result)

    return campaign, channels, results


def _fresh_measurement_factory(unit: str = "uM") -> Callable:
    """Returns a resolver factory that produces fresh measurements (value=99.0)."""

    def _factory(channel, result_id, molecule_id) -> CampaignMeasurement:
        return CampaignMeasurement(
            result_id=result_id,
            channel_id=channel.id,
            value=99.0,
            value_qualifier=ValueQualifier.EQ,
            unit=unit,
            protocol_name_snapshot="Proto",
            protocol_version_snapshot=1,
        )

    return _factory


def _nd_measurement_factory() -> Callable:
    """Returns a resolver factory that produces ND measurements with placeholder unit '-'."""

    def _factory(channel, result_id, molecule_id) -> CampaignMeasurement:
        return CampaignMeasurement(
            result_id=result_id,
            channel_id=channel.id,
            value=None,
            value_qualifier=ValueQualifier.ND,
            unit="-",
            protocol_name_snapshot="Proto",
            protocol_version_snapshot=1,
        )

    return _factory


def _make_protocol_repo(protocols: list | None = None) -> AsyncMock:
    """Return an AsyncMock protocol repository returning given protocols."""
    repo = AsyncMock()
    repo.find_by_ids = AsyncMock(return_value=protocols or [])
    # Effective-targets resolver — empty by default; tests asserting targets
    # override this.
    repo.find_effective_targets_for_protocols = AsyncMock(return_value={})
    return repo


def _make_fake_protocol(
    protocol_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
    *,
    unit: str | None = "uM",
    protocol_version: int = 1,
) -> AsyncMock:
    """Return a fake protocol object with one readout definition."""
    protocol = AsyncMock()
    protocol.id = protocol_id
    protocol.name = "Test Protocol"
    protocol.protocol_version = protocol_version
    protocol.target_id = None

    readout = AsyncMock()
    readout.id = readout_definition_id
    readout.unit = unit
    protocol.readout_definitions = [readout]

    return protocol


def _make_command(
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    note: str | None = None,
) -> CloseCampaignCommand:
    return CloseCampaignCommand(
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        user_id=user_id or uuid.uuid4(),
        note=note,
    )


def _make_use_case(
    campaign,
    *,
    protocol_id: uuid.UUID | None = None,
    readout_definition_id: uuid.UUID | None = None,
    readout_unit: str | None = "uM",
    resolver_unit: str = "uM",
    resolver_factory: Callable | None = None,
) -> tuple[CloseCampaign, AsyncMock, AsyncMock, FakeResolver]:
    """Build a CloseCampaign use case with fakes; return (uc, campaign_repo, protocol_repo, resolver).

    No ``collection_repo`` — soft close publishes nothing (spec §4/§5).
    """
    saved: list[Campaign] = []
    campaign_repo = make_campaign_repo(saved=saved, find_in_ws=campaign)

    protocols = []
    if protocol_id is not None and readout_definition_id is not None:
        protocols = [
            _make_fake_protocol(protocol_id, readout_definition_id, unit=readout_unit)
        ]

    protocol_repo = _make_protocol_repo(protocols)

    factory = resolver_factory or _fresh_measurement_factory(resolver_unit)
    resolver = FakeResolver(factory=factory)

    dispatcher = AsyncMock()
    dispatcher.dispatch_all = AsyncMock()

    uc = CloseCampaign(
        uow=FakeUnitOfWork(),
        campaign_repo=campaign_repo,
        protocol_repo=protocol_repo,
        resolver=resolver,
        dispatcher=dispatcher,
    )
    return uc, campaign_repo, protocol_repo, resolver


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------


class TestCloseCampaign:
    # ------------------------------------------------------------------
    # 1. Happy path — no signature, no collection, note persisted
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_happy_path_persists_note_and_source_protocols(self) -> None:
        """1 channel, 3 results; note is persisted; no collection is touched."""
        auth = fake_auth()
        pid = uuid.uuid4()
        rdid = uuid.uuid4()

        campaign = Campaign.create(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="Alpha",
            description=None,
            created_by=uuid.uuid4(),
        )
        ch = _make_channel(campaign.id, protocol_id=pid, readout_definition_id=rdid)
        campaign.add_channel(ch)

        for _ in range(3):
            r = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
            r.add_measurement(_make_measurement(r.id, ch.id))
            campaign.add_result(r)

        uc, campaign_repo, protocol_repo, resolver = _make_use_case(
            campaign, protocol_id=pid, readout_definition_id=rdid
        )
        cmd = _make_command(auth.workspace_id, campaign.id, note="Confirmed by wet lab")
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        c = out.unwrap()
        assert c.status == CampaignStatus.CLOSED
        assert c.close_note == "Confirmed by wet lab"

        # source_protocols populated
        assert len(c.source_protocols) == 1
        assert c.source_protocols[0]["id"] == str(pid)
        assert c.source_protocols[0]["name"] == "Test Protocol"

        dispatcher = uc._dispatcher
        dispatcher.dispatch_all.assert_awaited_once()
        # Events remain on the campaign — FakeUnitOfWork doesn't auto-drain them.
        all_events = campaign.collect_events()
        event_types = {type(e) for e in all_events}
        assert CampaignClosed in event_types

    # ------------------------------------------------------------------
    # 2. No note supplied → close_note stays None
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_close_without_note_leaves_close_note_none(self) -> None:
        auth = fake_auth()
        pid = uuid.uuid4()
        rdid = uuid.uuid4()
        campaign, _, _ = _build_campaign(
            auth.workspace_id, protocol_id=pid, readout_definition_id=rdid
        )

        uc, _, _, _ = _make_use_case(campaign, protocol_id=pid, readout_definition_id=rdid)
        cmd = _make_command(auth.workspace_id, campaign.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        c = out.unwrap()
        assert c.close_note is None

    # ------------------------------------------------------------------
    # 3. Re-resolve respects manual override
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_manual_override_not_re_resolved(self) -> None:
        """Cells with is_manual_override=True are not re-resolved."""
        auth = fake_auth()
        pid = uuid.uuid4()
        rdid = uuid.uuid4()
        campaign, channels, results = _build_campaign(
            auth.workspace_id,
            protocol_id=pid,
            readout_definition_id=rdid,
            override_indices={(0, 0)},
        )

        uc, _, _, resolver = _make_use_case(
            campaign, protocol_id=pid, readout_definition_id=rdid
        )
        cmd = _make_command(auth.workspace_id, campaign.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        # 1 result × 1 channel = 1 cell, and it's an override → resolver NOT called
        assert len(resolver.calls) == 0
        # The override measurement value is still 10.0
        m = campaign.results[0].find_measurement(channels[0].id)
        assert m is not None
        assert m.value == 10.0

    # ------------------------------------------------------------------
    # 4. ND unit repair: unit "-" replaced with real ReadoutDefinition.unit
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_nd_unit_repaired_when_readout_has_unit(self) -> None:
        """Non-override ND measurement with unit='-' gets unit from ReadoutDefinition."""
        auth = fake_auth()
        pid = uuid.uuid4()
        rdid = uuid.uuid4()

        campaign = Campaign.create(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="ND Repair",
            description=None,
            created_by=uuid.uuid4(),
        )
        ch = _make_channel(campaign.id, protocol_id=pid, readout_definition_id=rdid)
        campaign.add_channel(ch)
        r = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        r.add_measurement(_make_measurement(r.id, ch.id))
        campaign.add_result(r)

        # Resolver returns ND with placeholder unit "-"
        uc, _, _, resolver = _make_use_case(
            campaign,
            protocol_id=pid,
            readout_definition_id=rdid,
            readout_unit="uM",
            resolver_factory=_nd_measurement_factory(),
        )
        # Capture the existing measurement's id before the use-case call so we
        # can assert the rebuild path preserved it (avoiding a DELETE+INSERT that
        # would collide with the non-deferrable unique(result_id, channel_id) constraint).
        original_id = campaign.results[0].find_measurement(ch.id).id
        cmd = _make_command(auth.workspace_id, campaign.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        m = campaign.results[0].find_measurement(ch.id)
        assert m is not None
        assert m.unit == "uM"  # repaired from "-"
        assert m.id == original_id  # id preserved — no DELETE+INSERT collision

    # ------------------------------------------------------------------
    # 5. ND unit NOT repaired when readout's unit is None
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_nd_unit_not_repaired_when_readout_unit_none(self) -> None:
        """Placeholder unit '-' is left unchanged when readout's unit is None."""
        auth = fake_auth()
        pid = uuid.uuid4()
        rdid = uuid.uuid4()

        campaign = Campaign.create(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="ND No Repair",
            description=None,
            created_by=uuid.uuid4(),
        )
        ch = _make_channel(campaign.id, protocol_id=pid, readout_definition_id=rdid)
        campaign.add_channel(ch)
        r = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        r.add_measurement(_make_measurement(r.id, ch.id))
        campaign.add_result(r)

        # readout_unit=None → no repair
        uc, _, _, resolver = _make_use_case(
            campaign,
            protocol_id=pid,
            readout_definition_id=rdid,
            readout_unit=None,
            resolver_factory=_nd_measurement_factory(),
        )
        cmd = _make_command(auth.workspace_id, campaign.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        m = campaign.results[0].find_measurement(ch.id)
        assert m is not None
        assert m.unit == "-"  # left as-is

    # ------------------------------------------------------------------
    # 6. No channels → ValidationError from aggregate.close
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_no_channels_returns_validation_failure(self) -> None:
        """Aggregate.close raises ValidationError when no channels exist."""
        auth = fake_auth()
        campaign = Campaign.create(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="No Channels",
            description=None,
            created_by=uuid.uuid4(),
        )
        r = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        campaign.add_result(r)

        uc, campaign_repo, _, _ = _make_use_case(campaign)
        cmd = _make_command(auth.workspace_id, campaign.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 7. No results → ValidationError from aggregate.close
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_no_results_returns_validation_failure(self) -> None:
        """Aggregate.close raises ValidationError when no results exist."""
        auth = fake_auth()
        campaign = Campaign.create(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="No Results",
            description=None,
            created_by=uuid.uuid4(),
        )
        ch = _make_channel(campaign.id)
        campaign.add_channel(ch)
        # no results added

        uc, campaign_repo, _, _ = _make_use_case(campaign)
        cmd = _make_command(auth.workspace_id, campaign.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 8. Campaign not found
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_campaign_not_found_returns_not_found_failure(self) -> None:
        auth = fake_auth()
        campaign_repo = make_campaign_repo(find_in_ws=None)
        protocol_repo = _make_protocol_repo()
        dispatcher = AsyncMock()
        resolver = FakeResolver(factory=_fresh_measurement_factory())

        uc = CloseCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=campaign_repo,
            protocol_repo=protocol_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = _make_command(auth.workspace_id, uuid.uuid4())
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), NotFoundError)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 9. Campaign already CLOSED → ValidationError
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_already_closed_returns_validation_failure(self) -> None:
        auth = fake_auth()
        campaign, _, _ = _build_campaign(auth.workspace_id)
        campaign.status = CampaignStatus.CLOSED  # type: ignore[misc]

        uc, campaign_repo, _, _ = _make_use_case(campaign)
        cmd = _make_command(auth.workspace_id, campaign.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Failure)
        assert isinstance(out.failure(), ValidationError)
        campaign_repo.save.assert_not_awaited()

    # ------------------------------------------------------------------
    # 10. Unauthorized viewer → AuthorizationError
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_unauthorized_viewer_returns_authorization_failure(self) -> None:
        auth = fake_auth(role="viewer")
        campaign, _, _ = _build_campaign(auth.workspace_id)

        uc, campaign_repo, _, _ = _make_use_case(campaign)
        cmd = _make_command(auth.workspace_id, campaign.id)
        with pytest.raises(AuthorizationError):
            await uc(cmd, auth=auth)

    # ------------------------------------------------------------------
    # 11. Deduplication: two channels sharing one protocol_id → 1 source_protocol
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_source_protocols_dedupes_shared_protocol(self) -> None:
        """Two channels sharing the same protocol_id → source_protocols has 1 entry."""
        auth = fake_auth()
        shared_pid = uuid.uuid4()
        rdid1 = uuid.uuid4()
        rdid2 = uuid.uuid4()

        campaign = Campaign.create(
            workspace_id=auth.workspace_id,
            project_id=uuid.uuid4(),
            name="Dedup",
            description=None,
            created_by=uuid.uuid4(),
        )
        ch1 = _make_channel(
            campaign.id, protocol_id=shared_pid, readout_definition_id=rdid1, display_order=0
        )
        ch2 = _make_channel(
            campaign.id, protocol_id=shared_pid, readout_definition_id=rdid2, display_order=1
        )
        campaign.add_channel(ch1)
        campaign.add_channel(ch2)

        r = CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
        r.add_measurement(_make_measurement(r.id, ch1.id))
        r.add_measurement(_make_measurement(r.id, ch2.id))
        campaign.add_result(r)

        fake_proto = _make_fake_protocol(shared_pid, rdid1)
        fake_proto.readout_definitions = [
            _make_fake_protocol(shared_pid, rdid1).readout_definitions[0],
            _make_fake_protocol(shared_pid, rdid2, unit="nM").readout_definitions[0],
        ]
        protocol_repo = _make_protocol_repo([fake_proto])
        resolver = FakeResolver(factory=_fresh_measurement_factory())
        dispatcher = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = CloseCampaign(
            uow=FakeUnitOfWork(),
            campaign_repo=make_campaign_repo(find_in_ws=campaign),
            protocol_repo=protocol_repo,
            resolver=resolver,
            dispatcher=dispatcher,
        )
        cmd = _make_command(auth.workspace_id, campaign.id)
        out = await uc(cmd, auth=auth)

        assert isinstance(out, Success)
        c = out.unwrap()
        assert len(c.source_protocols) == 1
        assert c.source_protocols[0]["id"] == str(shared_pid)
        # Dedup: find_by_ids called once with that one id
        protocol_repo.find_by_ids.assert_awaited_once()
        assert set(protocol_repo.find_by_ids.call_args.args[1]) == {shared_pid}

    @pytest.mark.asyncio
    async def test_resolution_is_scoped_to_the_campaigns_source_runs(self) -> None:
        """Spec D4 — the close-time re-resolve honours the campaign's runs."""
        auth = fake_auth()
        campaign, channels, results = _build_campaign(auth.workspace_id)
        run_id = uuid.uuid4()
        results[0].added_from = RunRef(run_id=run_id)

        uc, _, _, resolver = _make_use_case(campaign)
        out = await uc(_make_command(auth.workspace_id, campaign.id), auth=auth)
        assert isinstance(out, Success)
        assert resolver.run_ids_seen == [[run_id]]

    @pytest.mark.asyncio
    async def test_close_opt_out_channel_resolves_unrestricted(self) -> None:
        auth = fake_auth()
        campaign, channels, results = _build_campaign(auth.workspace_id)
        results[0].added_from = RunRef(run_id=uuid.uuid4())
        channels[0].resolve_from_all_runs = True

        uc, _, _, resolver = _make_use_case(campaign)
        out = await uc(_make_command(auth.workspace_id, campaign.id), auth=auth)
        assert isinstance(out, Success)
        assert resolver.run_ids_seen == [None]
