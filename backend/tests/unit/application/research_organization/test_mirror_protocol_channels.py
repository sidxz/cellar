"""Unit tests for MirrorProtocolChannels use case."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.mirror_protocol_channels import (
    MirrorProtocolChannels,
    MirrorProtocolChannelsCommand,
)
from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.campaign_stage import CampaignStage
from cellar.domain.research_organization.enums import (
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.screening_assay.dose_response_config import (
    DoseResponseConfig,
    InterceptSpec,
)
from cellar.domain.screening_assay.enums import (
    CurveType,
    InterceptBasis,
    InterceptKind,
    ProtocolType,
    ReadoutDataType,
    ReadoutNormalization,
)
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.errors import NotFoundError, ValidationError
from cellar.domain.shared.hit_criterion import HitCriterion, InterceptKey
from tests.unit.application.research_organization._helpers import (
    FakeResolver,
    FakeUnitOfWork,
    fake_auth,
    make_campaign_repo,
)


def _make_protocol_repo(*, protocol=None) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id_in_workspace = AsyncMock(return_value=protocol)
    return repo


def _fake_measurement(
    channel: CampaignChannel, result_id: uuid.UUID, molecule_id: uuid.UUID
) -> CampaignMeasurement:
    return CampaignMeasurement(
        result_id=result_id,
        channel_id=channel.id,
        value=42.0,
        value_qualifier=ValueQualifier.EQ,
        unit="uM",
        protocol_name_snapshot="Test Protocol",
        protocol_version_snapshot=1,
    )


def _make_draft_campaign(workspace_id: uuid.UUID) -> Campaign:
    return Campaign.create(
        workspace_id=workspace_id,
        project_id=uuid.uuid4(),
        name="Test Campaign",
        description=None,
        created_by=uuid.uuid4(),
    )


def _make_protocol(
    workspace_id: uuid.UUID,
    *,
    readouts: list[ReadoutDefinition],
    recommended: list[HitCriterion] | None = None,
) -> Protocol:
    p = Protocol.create(
        workspace_id=workspace_id,
        name="Mtb_WCA_mc2-7000_Resazurin",
        description=None,
        protocol_type=ProtocolType.CELL_BASED,
        created_by=uuid.uuid4(),
        readout_definitions=readouts,
    )
    if recommended:
        p.set_recommended_hit_criteria(recommended)
    return p


def _dr_readout(
    *,
    name: str,
    intercepts: list[InterceptSpec],
    normalizations: list[ReadoutNormalization] | None = None,
) -> ReadoutDefinition:
    return ReadoutDefinition(
        protocol_id=uuid.uuid4(),
        name=name,
        data_type=ReadoutDataType.DOSE_RESPONSE,
        unit="uM",
        normalizations=frozenset(normalizations or []),
        dose_response_config=DoseResponseConfig(
            curve_type=CurveType.IC50,
            y_readout_name="raw signal",
            intercepts=tuple(intercepts),
        ),
    )


def _numeric_readout(
    *,
    name: str,
    normalizations: list[ReadoutNormalization] | None = None,
) -> ReadoutDefinition:
    return ReadoutDefinition(
        protocol_id=uuid.uuid4(),
        name=name,
        data_type=ReadoutDataType.NUMERIC,
        unit="%",
        normalizations=frozenset(normalizations or []),
    )


def _make_dispatcher() -> AsyncMock:
    d = AsyncMock()
    d.dispatch_all = AsyncMock(return_value=None)
    return d


@pytest.mark.asyncio
async def test_mirror_creates_one_channel_per_intercept() -> None:
    """Multi-intercept DR readout (EC50 + EC90) yields two channels.

    Primary stores intercept_key=None; secondary stores explicit
    InterceptKey.
    """
    auth = fake_auth()
    campaign = _make_draft_campaign(auth.workspace_id)
    rd = _dr_readout(
        name="Resazurin",
        intercepts=[
            InterceptSpec(kind=InterceptKind.EC, level=50.0),
            InterceptSpec(kind=InterceptKind.EC, level=90.0),
        ],
    )
    protocol = _make_protocol(auth.workspace_id, readouts=[rd])

    saved: list[Campaign] = []
    uc = MirrorProtocolChannels(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(saved=saved, find_in_ws=campaign),
        protocol_repo=_make_protocol_repo(protocol=protocol),
        resolver=FakeResolver(factory=_fake_measurement),
        dispatcher=_make_dispatcher(),
    )
    out = await uc(
        MirrorProtocolChannelsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            protocol_id=protocol.id,
        ),
        auth=auth,
    )

    assert isinstance(out, Success)
    outcome = out.unwrap()
    assert outcome.channels_created == 2
    assert outcome.channels_skipped == 0
    assert len(campaign.channels) == 2

    by_ik = {ch.intercept_key: ch for ch in campaign.channels}
    primary = by_ik[None]
    secondary = by_ik[InterceptKey(kind="ec", level=90.0)]

    assert primary.label == "Resazurin EC50"
    assert primary.source_kind == ChannelSourceKind.DOSE_RESPONSE_CURVE

    assert secondary.label == "Resazurin EC90"
    assert secondary.source_kind == ChannelSourceKind.DOSE_RESPONSE_CURVE


@pytest.mark.asyncio
async def test_mirror_is_idempotent_skips_duplicates() -> None:
    """Re-mirroring leaves existing channels alone and reports them as skipped."""
    auth = fake_auth()
    campaign = _make_draft_campaign(auth.workspace_id)
    rd = _dr_readout(
        name="Resazurin",
        intercepts=[InterceptSpec(kind=InterceptKind.EC, level=50.0)],
    )
    protocol = _make_protocol(auth.workspace_id, readouts=[rd])

    uc = MirrorProtocolChannels(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(find_in_ws=campaign),
        protocol_repo=_make_protocol_repo(protocol=protocol),
        resolver=FakeResolver(factory=_fake_measurement),
        dispatcher=_make_dispatcher(),
    )
    cmd = MirrorProtocolChannelsCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign.id,
        protocol_id=protocol.id,
    )

    out1 = await uc(cmd, auth=auth)
    assert isinstance(out1, Success)
    assert out1.unwrap().channels_created == 1
    assert out1.unwrap().channels_skipped == 0
    assert len(campaign.channels) == 1

    out2 = await uc(cmd, auth=auth)
    assert isinstance(out2, Success)
    assert out2.unwrap().channels_created == 0
    assert out2.unwrap().channels_skipped == 1
    assert len(campaign.channels) == 1


@pytest.mark.asyncio
async def test_mirror_handles_non_dr_readout_with_normalization() -> None:
    """Non-DR readout becomes one readout_data channel with the primary normalization."""
    auth = fake_auth()
    campaign = _make_draft_campaign(auth.workspace_id)
    rd = _numeric_readout(
        name="RSZ (% Inhibition)",
        normalizations=[ReadoutNormalization.NONE, ReadoutNormalization.PERCENT_INHIBITION],
    )
    protocol = _make_protocol(auth.workspace_id, readouts=[rd])

    uc = MirrorProtocolChannels(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(find_in_ws=campaign),
        protocol_repo=_make_protocol_repo(protocol=protocol),
        resolver=FakeResolver(factory=_fake_measurement),
        dispatcher=_make_dispatcher(),
    )
    out = await uc(
        MirrorProtocolChannelsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            protocol_id=protocol.id,
        ),
        auth=auth,
    )

    assert isinstance(out, Success)
    assert out.unwrap().channels_created == 1
    ch = campaign.channels[0]
    assert ch.source_kind == ChannelSourceKind.READOUT_DATA
    assert ch.normalization_applied == ReadoutNormalization.PERCENT_INHIBITION.value
    assert ch.intercept_key is None
    assert ch.label == "RSZ (% Inhibition)"


@pytest.mark.asyncio
async def test_mirror_requires_draft_campaign() -> None:
    auth = fake_auth()
    campaign = _make_draft_campaign(auth.workspace_id)
    # Force-close: bypass close() since it requires >=1 channel and result; just mutate status
    campaign.status = CampaignStatus.CLOSED

    rd = _numeric_readout(name="RSZ", normalizations=[ReadoutNormalization.NONE])
    protocol = _make_protocol(auth.workspace_id, readouts=[rd])

    uc = MirrorProtocolChannels(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(find_in_ws=campaign),
        protocol_repo=_make_protocol_repo(protocol=protocol),
        resolver=FakeResolver(factory=_fake_measurement),
        dispatcher=_make_dispatcher(),
    )
    out = await uc(
        MirrorProtocolChannelsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            protocol_id=protocol.id,
        ),
        auth=auth,
    )

    assert isinstance(out, Failure)
    assert isinstance(out.failure(), ValidationError)


@pytest.mark.asyncio
async def test_mirror_protocol_not_found_returns_failure() -> None:
    auth = fake_auth()
    campaign = _make_draft_campaign(auth.workspace_id)

    uc = MirrorProtocolChannels(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(find_in_ws=campaign),
        protocol_repo=_make_protocol_repo(protocol=None),
        resolver=FakeResolver(factory=_fake_measurement),
        dispatcher=_make_dispatcher(),
    )
    out = await uc(
        MirrorProtocolChannelsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            protocol_id=uuid.uuid4(),
        ),
        auth=auth,
    )

    assert isinstance(out, Failure)
    assert isinstance(out.failure(), NotFoundError)


@pytest.mark.asyncio
async def test_mirror_label_dedups_cdd_style_readout_name() -> None:
    """rd.name == primary intercept's label → drop redundant prefix.

    A CDD-style protocol names its DR readout 'EC50' (matching the
    primary intercept's canonical label). The mirror loop should produce
    'EC50' / 'EC90' channels, not 'EC50 EC50' / 'EC50 EC90'.
    """
    auth = fake_auth()
    campaign = _make_draft_campaign(auth.workspace_id)
    rd = _dr_readout(
        name="EC50",
        intercepts=[
            InterceptSpec(kind=InterceptKind.EC, level=50.0),
            InterceptSpec(kind=InterceptKind.EC, level=90.0),
        ],
    )
    protocol = _make_protocol(auth.workspace_id, readouts=[rd])

    uc = MirrorProtocolChannels(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(find_in_ws=campaign),
        protocol_repo=_make_protocol_repo(protocol=protocol),
        resolver=FakeResolver(factory=_fake_measurement),
        dispatcher=_make_dispatcher(),
    )
    out = await uc(
        MirrorProtocolChannelsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            protocol_id=protocol.id,
        ),
        auth=auth,
    )

    assert isinstance(out, Success)
    labels = sorted(ch.label for ch in campaign.channels)
    assert labels == ["EC50", "EC90"]


# ---------------------------------------------------------------------------
# stage_name (Task 12)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mirror_creates_stage_from_recommended_criteria() -> None:
    """stage_name + a recommendation that matches a mirrored readout ->
    one CampaignStage with one criterion bound to that channel."""
    auth = fake_auth()
    campaign = _make_draft_campaign(auth.workspace_id)
    rd = _numeric_readout(name="IC50", normalizations=[ReadoutNormalization.NONE])
    protocol = _make_protocol(
        auth.workspace_id,
        readouts=[rd],
        recommended=[HitCriterion(readout_name="IC50", operator="lt", value=10.0)],
    )

    uc = MirrorProtocolChannels(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(find_in_ws=campaign),
        protocol_repo=_make_protocol_repo(protocol=protocol),
        resolver=FakeResolver(factory=_fake_measurement),
        dispatcher=_make_dispatcher(),
    )
    out = await uc(
        MirrorProtocolChannelsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            protocol_id=protocol.id,
            stage_name="Primary Hits",
        ),
        auth=auth,
    )

    assert isinstance(out, Success)
    outcome = out.unwrap()
    assert outcome.stage_created is True
    assert len(campaign.stages) == 1
    stage = campaign.stages[0]
    assert stage.name == "Primary Hits"
    assert len(stage.criteria) == 1
    assert stage.criteria[0].channel_id == campaign.channels[0].id
    assert stage.criteria[0].operator == "lt"
    assert stage.criteria[0].value == 10.0


@pytest.mark.asyncio
async def test_mirror_no_recommendations_stage_not_created() -> None:
    """stage_name given but the protocol has no recommended_hit_criteria ->
    stage_created is False and no stage is added."""
    auth = fake_auth()
    campaign = _make_draft_campaign(auth.workspace_id)
    rd = _numeric_readout(name="IC50", normalizations=[ReadoutNormalization.NONE])
    protocol = _make_protocol(auth.workspace_id, readouts=[rd])

    uc = MirrorProtocolChannels(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(find_in_ws=campaign),
        protocol_repo=_make_protocol_repo(protocol=protocol),
        resolver=FakeResolver(factory=_fake_measurement),
        dispatcher=_make_dispatcher(),
    )
    out = await uc(
        MirrorProtocolChannelsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            protocol_id=protocol.id,
            stage_name="Primary Hits",
        ),
        auth=auth,
    )

    assert isinstance(out, Success)
    outcome = out.unwrap()
    assert outcome.stage_created is False
    assert campaign.stages == []


@pytest.mark.asyncio
async def test_mirror_none_stage_name_creates_no_stage() -> None:
    """stage_name omitted (None) -> no stage even though a recommendation
    would otherwise map onto the mirrored channel."""
    auth = fake_auth()
    campaign = _make_draft_campaign(auth.workspace_id)
    rd = _numeric_readout(name="IC50", normalizations=[ReadoutNormalization.NONE])
    protocol = _make_protocol(
        auth.workspace_id,
        readouts=[rd],
        recommended=[HitCriterion(readout_name="IC50", operator="lt", value=10.0)],
    )

    uc = MirrorProtocolChannels(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(find_in_ws=campaign),
        protocol_repo=_make_protocol_repo(protocol=protocol),
        resolver=FakeResolver(factory=_fake_measurement),
        dispatcher=_make_dispatcher(),
    )
    out = await uc(
        MirrorProtocolChannelsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            protocol_id=protocol.id,
        ),
        auth=auth,
    )

    assert isinstance(out, Success)
    outcome = out.unwrap()
    assert outcome.stage_created is False
    assert campaign.stages == []


@pytest.mark.asyncio
async def test_mirror_saves_when_only_stage_created_no_new_channels() -> None:
    """Re-mirroring an already-fully-mirrored protocol creates zero new
    channels; a stage_name that maps onto the pre-existing channel must
    still be persisted (channels_created==0 must not skip the save)."""
    auth = fake_auth()
    campaign = _make_draft_campaign(auth.workspace_id)
    rd = _numeric_readout(name="IC50", normalizations=[ReadoutNormalization.NONE])
    protocol = _make_protocol(
        auth.workspace_id,
        readouts=[rd],
        recommended=[HitCriterion(readout_name="IC50", operator="lt", value=10.0)],
    )

    saved: list[Campaign] = []
    uc = MirrorProtocolChannels(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(saved=saved, find_in_ws=campaign),
        protocol_repo=_make_protocol_repo(protocol=protocol),
        resolver=FakeResolver(factory=_fake_measurement),
        dispatcher=_make_dispatcher(),
    )

    out1 = await uc(
        MirrorProtocolChannelsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            protocol_id=protocol.id,
        ),
        auth=auth,
    )
    assert isinstance(out1, Success)
    assert out1.unwrap().channels_created == 1
    saved.clear()

    out2 = await uc(
        MirrorProtocolChannelsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            protocol_id=protocol.id,
            stage_name="Primary Hits",
        ),
        auth=auth,
    )
    assert isinstance(out2, Success)
    outcome2 = out2.unwrap()
    assert outcome2.channels_created == 0
    assert outcome2.stage_created is True
    assert len(campaign.stages) == 1
    assert len(saved) == 1


@pytest.mark.asyncio
async def test_mirror_reuses_stage_with_same_name() -> None:
    """Re-mirroring under the same stage_name rewrites that stage instead of
    failing on the name-uniqueness rule — and still persists the campaign
    even though no new channel was created."""
    auth = fake_auth()
    campaign = _make_draft_campaign(auth.workspace_id)
    rd = _numeric_readout(name="IC50", normalizations=[ReadoutNormalization.NONE])
    protocol = _make_protocol(
        auth.workspace_id,
        readouts=[rd],
        recommended=[HitCriterion(readout_name="IC50", operator="lt", value=10.0)],
    )

    saved: list[Campaign] = []
    uc = MirrorProtocolChannels(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(saved=saved, find_in_ws=campaign),
        protocol_repo=_make_protocol_repo(protocol=protocol),
        resolver=FakeResolver(factory=_fake_measurement),
        dispatcher=_make_dispatcher(),
    )
    cmd = MirrorProtocolChannelsCommand(
        workspace_id=auth.workspace_id,
        campaign_id=campaign.id,
        protocol_id=protocol.id,
        stage_name="Primary Hits",
    )

    out1 = await uc(cmd, auth=auth)
    assert isinstance(out1, Success)
    assert out1.unwrap().stage_created is True
    original_stage_id = campaign.stages[0].id
    saved.clear()

    # Same name, different casing -> the same stage.
    out2 = await uc(
        MirrorProtocolChannelsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            protocol_id=protocol.id,
            stage_name="PRIMARY hits",
        ),
        auth=auth,
    )
    assert isinstance(out2, Success)
    outcome2 = out2.unwrap()
    assert outcome2.channels_created == 0
    assert outcome2.stage_created is False
    assert len(campaign.stages) == 1
    assert campaign.stages[0].id == original_stage_id
    assert len(campaign.stages[0].criteria) == 1
    assert campaign.stages[0].criteria[0].channel_id == campaign.channels[0].id
    # A reused-and-rewritten stage still has to be persisted.
    assert len(saved) == 1


@pytest.mark.asyncio
async def test_mirror_stage_created_under_parent_stage_id() -> None:
    """parent_stage_id attaches the mirrored stage under an existing one."""
    auth = fake_auth()
    campaign = _make_draft_campaign(auth.workspace_id)
    parent = CampaignStage(campaign_id=campaign.id, name="Triage", display_order=0)
    campaign.add_stage(parent)
    rd = _numeric_readout(name="IC50", normalizations=[ReadoutNormalization.NONE])
    protocol = _make_protocol(
        auth.workspace_id,
        readouts=[rd],
        recommended=[HitCriterion(readout_name="IC50", operator="lt", value=10.0)],
    )

    uc = MirrorProtocolChannels(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(find_in_ws=campaign),
        protocol_repo=_make_protocol_repo(protocol=protocol),
        resolver=FakeResolver(factory=_fake_measurement),
        dispatcher=_make_dispatcher(),
    )
    out = await uc(
        MirrorProtocolChannelsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            protocol_id=protocol.id,
            stage_name="Primary Hits",
            parent_stage_id=parent.id,
        ),
        auth=auth,
    )

    assert isinstance(out, Success)
    assert out.unwrap().stage_created is True
    child = next(s for s in campaign.stages if s.name == "Primary Hits")
    assert child.parent_stage_id == parent.id


@pytest.mark.asyncio
async def test_mirror_bad_parent_fails_before_resolving_any_measurement() -> None:
    """The stage step runs before the per-result resolve loop, so a bad
    parent id costs no resolver work."""
    auth = fake_auth()
    campaign = _make_draft_campaign(auth.workspace_id)
    campaign.results.append(
        CampaignResult(campaign_id=campaign.id, molecule_id=uuid.uuid4())
    )
    rd = _numeric_readout(name="IC50", normalizations=[ReadoutNormalization.NONE])
    protocol = _make_protocol(
        auth.workspace_id,
        readouts=[rd],
        recommended=[HitCriterion(readout_name="IC50", operator="lt", value=10.0)],
    )

    resolver = FakeResolver(factory=_fake_measurement)
    uc = MirrorProtocolChannels(
        uow=FakeUnitOfWork(),
        campaign_repo=make_campaign_repo(find_in_ws=campaign),
        protocol_repo=_make_protocol_repo(protocol=protocol),
        resolver=resolver,
        dispatcher=_make_dispatcher(),
    )
    out = await uc(
        MirrorProtocolChannelsCommand(
            workspace_id=auth.workspace_id,
            campaign_id=campaign.id,
            protocol_id=protocol.id,
            stage_name="Primary Hits",
            parent_stage_id=uuid.uuid4(),  # not a stage on this campaign
        ),
        auth=auth,
    )

    assert isinstance(out, Failure)
    assert isinstance(out.failure(), ValidationError)
    assert resolver.calls == []
    assert campaign.stages == []
