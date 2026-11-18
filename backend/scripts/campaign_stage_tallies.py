"""Print every campaign's stage tallies as JSON: {campaign_id: {stage_id: counts}}.

The before/after check for migration 104 (spec §11): run it, migrate, run it again,
and diff the two outputs; they must be identical. Campaigns load through the real
repository and are judged by ``evaluate_stages`` + ``tally_stage_counts``.

The database comes from the normal settings (``DATABASE_URL``), so override that to
point the script at another database.

Usage (from backend/):
    uv run python scripts/campaign_stage_tallies.py > before.json
"""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cellar.domain.research_organization.stage_evaluation import (
    evaluate_stages,
    tally_stage_counts,
)
from cellar.infrastructure.persistence.settings import DatabaseSettings
from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (  # noqa: E501
    SQLAlchemyCampaignRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def tallies(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, dict[str, dict[str, int]]]:
    out: dict[str, dict[str, dict[str, int]]] = {}
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCampaignRepository(uow)
        for campaign_id in (await uow.session.scalars(select(CampaignModel.id))).all():
            campaign = await repo.find_by_id(campaign_id)
            assert campaign is not None
            counts = tally_stage_counts(campaign, evaluate_stages(campaign))
            out[str(campaign_id)] = {str(stage_id): c for stage_id, c in counts.items()}
    return out


async def _main() -> None:
    engine = create_async_engine(DatabaseSettings().database_url)  # type: ignore[call-arg]
    try:
        result = await tallies(async_sessionmaker(engine, expire_on_commit=False))
    finally:
        await engine.dispose()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(_main())
