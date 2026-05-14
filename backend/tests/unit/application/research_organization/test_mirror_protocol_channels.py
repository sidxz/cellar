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
        publishes_collection=True,
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
    InterceptKey. The recommended criteria for EC50 (primary) and EC90
    (secondary) are carried forward as the channels' hit_threshold.
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
    protocol = _make_protocol(
        auth.workspace_id,
        readouts=[rd],
        recommended=[
            HitCriterion(readout_name="Resazurin", operator="lt", value=50.0),
            HitCriterion(
                readout_name="Resazurin",
                operator="lt",
                value=150.0,
                intercept_key=InterceptKey(kind="ec", level=90.0),
            ),
        ],
    )

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
    assert primary.hit_threshold is not None
    assert primary.hit_threshold.value == 50.0
    assert primary.hit_threshold.intercept_key is None

    assert secondary.label == "Resazurin EC90"
    assert secondary.source_kind == ChannelSourceKind.DOSE_RESPONSE_CURVE
    assert secondary.hit_threshold is not None
    assert secondary.hit_threshold.value == 150.0
    assert secondary.hit_threshold.intercept_key == InterceptKey(kind="ec", level=90.0)


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
    # Force-close: bypass close() since it requires signature_id; just mutate status
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
