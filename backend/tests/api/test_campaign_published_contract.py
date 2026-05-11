"""DAIKON published-contract schema validation.

JSON Schema (Draft-07) fixture captures spec §6 shape: campaign +
compound_sources (list, plural) + source_protocols snapshot +
channels (live protocol+readout refs) + results with nested measurements +
optional published_collection + optional pagination envelope.

Test seeds a closed campaign directly into the DB (bypassing the API
close endpoint, which requires real protocol/readout/run data for
channel resolution) then validates GET /api/v1/campaigns/{id}/published
against the schema fixture.

Field-name typos or shape drift in the published endpoint will break
this test — confirmed by temporarily renaming "molecule" → "mol" in
the serializer and observing a schema failure.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import jsonschema
import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

import chem_vault.infrastructure.persistence.sqlalchemy.research_organization.models  # noqa: F401
import chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.models  # noqa: F401

from chem_vault.application.research_organization.close_campaign import (
    CloseCampaign,
    CloseCampaignCommand,
)
from chem_vault.domain.research_organization.campaign import Campaign
from chem_vault.domain.research_organization.campaign_channel import CampaignChannel
from chem_vault.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from chem_vault.domain.research_organization.campaign_result import CampaignResult
from chem_vault.domain.research_organization.enums import (
    CampaignDecision,
    ChannelSourceKind,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from chem_vault.domain.research_organization.source_ref import ManualRef
from chem_vault.domain.screening_assay.enums import (
    ProtocolStatus,
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
)
from chem_vault.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (
    SQLAlchemyCampaignRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (
    SQLAlchemyCollectionRepository,
)
from chem_vault.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


# ---------------------------------------------------------------------------
# Schema fixture
# ---------------------------------------------------------------------------

_SCHEMA_PATH = Path(__file__).parent / "fixtures" / "daikon_contract.schema.json"


@pytest.fixture(scope="module")
def daikon_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text())


# ---------------------------------------------------------------------------
# DB seeding helpers (mirrors test_close_campaign integration pattern)
# ---------------------------------------------------------------------------


class _FakeResolver:
    """Returns a real measurement for any (channel, molecule) pair."""

    async def resolve(
        self, *, workspace_id: Any, channel: Any, result_id: Any, molecule_id: Any
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


class _NoOpDispatcher:
    async def dispatch_all(self, events: Any) -> None:
        pass


async def _insert_org_and_molecule(
    session_factory: async_sessionmaker[AsyncSession],
    ws_id: uuid.UUID,
    mol_id: uuid.UUID,
) -> None:
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await uow.session.execute(
            sa.text(
                "INSERT INTO organizations (id, workspace_id, name, org_type, "
                "is_active, version) "
                "VALUES (:id, :ws, 'ContractTestOrg', 'internal', true, 1) "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": ws_id, "ws": ws_id},
        )
        await uow.session.execute(
            sa.text(
                "INSERT INTO molecules (id, workspace_id, name, molecule_type, "
                "structure_status, registration_status, synthesis_status, "
                "lifecycle_stage, registration_number, originating_org_id, version) "
                "VALUES (:id, :ws, 'ContractMol', 'small_molecule', 'undisclosed', "
                "'approved', 'virtual', 'registered', :reg, :org, 1)"
            ),
            {"id": mol_id, "ws": ws_id, "reg": f"CV-{mol_id.hex[:6]}", "org": ws_id},
        )
        await uow.commit()


async def _insert_project(
    session_factory: async_sessionmaker[AsyncSession],
    ws_id: uuid.UUID,
    project_id: uuid.UUID,
) -> None:
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await uow.session.execute(
            sa.text(
                "INSERT INTO projects (id, workspace_id, name, status, created_by, version) "
                "VALUES (:id, :ws, 'ContractTestProject', 'active', :cb, 1) "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": project_id, "ws": ws_id, "cb": uuid.uuid4()},
        )
        await uow.commit()


async def _insert_protocol(
    session_factory: async_sessionmaker[AsyncSession],
    ws_id: uuid.UUID,
    protocol_id: uuid.UUID,
    readout_id: uuid.UUID,
) -> None:
    rd = ReadoutDefinition(
        id=readout_id,
        protocol_id=protocol_id,
        name="IC50",
        data_type=ReadoutDataType.NUMERIC,
        unit="uM",
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
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        await repo.save(protocol)
        await uow.commit()


async def _seed_closed_campaign(
    session_factory: async_sessionmaker[AsyncSession],
    ws_id: uuid.UUID,
    protocol_id: uuid.UUID,
    readout_id: uuid.UUID,
    project_id: uuid.UUID,
    mol_id: uuid.UUID,
    user_id: uuid.UUID,
) -> uuid.UUID:
    """Create a DRAFT campaign and close it via the CloseCampaign use case.

    Returns the campaign UUID.
    """
    campaign = Campaign.create(
        workspace_id=ws_id,
        project_id=project_id,
        name="Contract Test Campaign",
        description="Schema validation fixture",
        publishes_collection=True,
        created_by=user_id,
    )
    ch = CampaignChannel(
        campaign_id=campaign.id,
        label="IC50 (target binding)",
        protocol_id=protocol_id,
        readout_definition_id=readout_id,
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    campaign.add_channel(ch)

    result = CampaignResult(
        campaign_id=campaign.id,
        molecule_id=mol_id,
        added_from=ManualRef(),
    )
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

    # Save DRAFT
    async with AsyncUnitOfWork(session_factory) as uow_seed:
        repo = SQLAlchemyCampaignRepository(uow_seed)
        await repo.save(campaign)
        await uow_seed.commit()

    # Close via use case
    sig_id = uuid.uuid4()
    cmd = CloseCampaignCommand(
        workspace_id=ws_id,
        campaign_id=campaign.id,
        user_id=user_id,
        signature_id=sig_id,
    )

    uow_uc = AsyncUnitOfWork(session_factory)
    auth_mock = AsyncMock()
    auth_mock.user_id = user_id
    auth_mock.workspace_id = ws_id
    auth_mock.workspace_role = "editor"
    auth_mock.is_admin = False
    rank = {"viewer": 0, "editor": 1, "admin": 2}
    auth_mock.has_role = lambda min_role: rank.get("editor", 0) >= rank.get(min_role, 0)

    uc = CloseCampaign(
        uow=uow_uc,
        campaign_repo=SQLAlchemyCampaignRepository(uow_uc),
        collection_repo=SQLAlchemyCollectionRepository(uow_uc),
        protocol_repo=SQLAlchemyProtocolRepository(uow_uc),
        resolver=_FakeResolver(),
        dispatcher=_NoOpDispatcher(),  # type: ignore[arg-type]
    )
    from returns.result import Success

    out = await uc(cmd, auth=auth_mock)
    assert isinstance(out, Success), f"CloseCampaign failed: {out}"

    return campaign.id


# ---------------------------------------------------------------------------
# Contract test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_published_endpoint_matches_daikon_schema(
    client: AsyncClient,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
    daikon_schema: dict[str, Any],
) -> None:
    """GET /api/v1/campaigns/{id}/published returns a JSON document matching
    the DAIKON contract (spec §6).

    Seeds a closed campaign directly into the same workspace the API client
    authenticates against, then validates the response body against the JSON
    Schema fixture.  Any field-name typo or shape change in
    get_published_campaign.py will cause a jsonschema.ValidationError here.
    """
    mol_id = uuid.uuid4()
    protocol_id = uuid.uuid4()
    readout_id = uuid.uuid4()
    project_id = uuid.uuid4()

    # Seed all prerequisites using the same workspace_id as the FakeAuth client.
    await _insert_org_and_molecule(session_factory, workspace_id, mol_id)
    await _insert_project(session_factory, workspace_id, project_id)
    await _insert_protocol(session_factory, workspace_id, protocol_id, readout_id)

    campaign_id = await _seed_closed_campaign(
        session_factory,
        workspace_id,
        protocol_id,
        readout_id,
        project_id,
        mol_id,
        user_id,
    )

    # Hit the published endpoint via the API client (FakeAuth, same workspace).
    resp = await client.get(f"/api/v1/campaigns/{campaign_id}/published")
    assert resp.status_code == 200, f"Expected 200 but got {resp.status_code}: {resp.text}"

    body = resp.json()

    # Validate against the JSON Schema.
    jsonschema.validate(instance=body, schema=daikon_schema)

    # Spot-check key structural invariants beyond schema validation.
    assert body["campaign"]["id"] == str(campaign_id)
    assert body["campaign"]["status"] == "closed"
    # compound_sources is now a list (plural)
    assert isinstance(body["compound_sources"], list)
    assert len(body["compound_sources"]) == 1
    assert body["compound_sources"][0]["kind"] == "manual"
    assert body["compound_sources"][0]["count"] == 1
    assert len(body["channels"]) == 1
    assert body["channels"][0]["label"] == "IC50 (target binding)"
    assert len(body["results"]) == 1
    assert body["results"][0]["decision"] == "selected"
    assert len(body["results"][0]["measurements"]) == 1
    assert body["results"][0]["measurements"][0]["unit"] == "uM"
    # published_collection must be non-null because publishes_collection=True and
    # at least one SELECTED result exists.
    assert body["published_collection"] is not None
    assert body["published_collection"]["size"] == 1
    # source_protocols snapshot is populated at close time.
    assert len(body["source_protocols"]) == 1
    assert body["source_protocols"][0]["id"] == str(protocol_id)
