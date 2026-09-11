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
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from returns.result import Success

from cellar.application.research_organization.close_campaign import (
    CloseCampaign,
    CloseCampaignCommand,
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
    CampaignDecision,
    CampaignStatus,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.screening_assay.enums import (
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
)
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (
    SQLAlchemyCampaignRepository,
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
        self, *, workspace_id, channel, result_id, molecule_id
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
    result.decision = CampaignDecision.SELECTED  # type: ignore[misc]
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
