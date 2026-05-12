"""Integration smoke for the SQL ChannelResolutionQuery.

Deep verification of the join is exercised indirectly by the
close-campaign integration tests in Phase 5 (which seed real
curves/runs/protocols and round-trip through this query). This module
only confirms the class is wireable and returns an empty list when no
data matches.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.mark.asyncio
async def test_empty_candidates_for_unknown_molecule(session_factory):
    from cellar.domain.research_organization.campaign_channel import (
        CampaignChannel,
    )
    from cellar.domain.research_organization.enums import (
        ChannelSourceKind,
        QualifierHandling,
        SelectionRule,
    )
    from cellar.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query import (
        SQLAlchemyChannelResolutionQuery,
    )

    query = SQLAlchemyChannelResolutionQuery(session_factory)
    channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="IC50",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.DOSE_RESPONSE_CURVE,
        selection_rule=SelectionRule.LATEST_APPROVED_RUN,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    candidates = await query.fetch_candidates(
        workspace_id=uuid.uuid4(),
        channel=channel,
        molecule_id=uuid.uuid4(),
    )
    assert candidates == []


@pytest.mark.asyncio
async def test_empty_candidates_for_readout_source(session_factory):
    """Same smoke for the READOUT_DATA branch of the query."""
    from cellar.domain.research_organization.campaign_channel import (
        CampaignChannel,
    )
    from cellar.domain.research_organization.enums import (
        ChannelSourceKind,
        QualifierHandling,
        SelectionRule,
    )
    from cellar.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query import (
        SQLAlchemyChannelResolutionQuery,
    )

    query = SQLAlchemyChannelResolutionQuery(session_factory)
    channel = CampaignChannel(
        campaign_id=uuid.uuid4(),
        label="% inhibition",
        protocol_id=uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        source_kind=ChannelSourceKind.READOUT_DATA,
        selection_rule=SelectionRule.MEAN_ACROSS_RUNS,
        qualifier_handling=QualifierHandling.INCLUDE_QUALIFIED,
        display_order=0,
    )
    candidates = await query.fetch_candidates(
        workspace_id=uuid.uuid4(),
        channel=channel,
        molecule_id=uuid.uuid4(),
    )
    assert candidates == []
