"""Campaign results search by compound identity: workspace-scoped, literal wildcards,
and molecule id lists longer than one IN batch."""

from __future__ import annotations

import uuid

import pytest

from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_identity import (
    SQLAlchemyCampaignIdentityReader,
)
from tests.integration import _screening_seed as seed


@pytest.mark.asyncio
async def test_matching_ids_scopes_to_workspace_and_treats_wildcards_literally(uow, workspace_id):
    ws, other_ws = workspace_id, uuid.uuid4()
    async with uow:
        s = uow.session
        org = await seed.org(s, ws)
        literal = await seed.molecule(s, ws, org, "a%_b amide")
        wildcard_only = await seed.molecule(s, ws, org, "aXYb amide")
        foreign = await seed.molecule(s, other_ws, await seed.org(s, other_ws), "a%_b amide")
        await uow.commit()

    # The hit sits past the first 1000-id batch.
    ids = [uuid.uuid4() for _ in range(1000)] + [literal, wildcard_only, foreign]
    async with uow:
        reader = SQLAlchemyCampaignIdentityReader(uow)
        assert await reader.matching_ids(ws, ids, "A%_B") == {literal}
        assert await reader.matching_ids(ws, ids, "cv-" + literal.hex[:6]) == {literal}
        assert await reader.matching_ids(ws, [], "a") == set()
