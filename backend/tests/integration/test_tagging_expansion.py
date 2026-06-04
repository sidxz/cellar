"""Integration tests for the four new taggable entity types (plumbing)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from cellar.domain.workspace_config.tagging.tag import TaggableEntityType
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    get_tag_link_repository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

pytestmark = pytest.mark.asyncio


NEW_TYPES = [
    TaggableEntityType.RUN,
    TaggableEntityType.CAMPAIGN,
    TaggableEntityType.BATCH,
    TaggableEntityType.PLATE,
]

NEW_LINK_TABLES = ["run_tags", "campaign_tags", "batch_tags", "registered_plate_tags"]


def test_registry_resolves_all_new_types(uow: AsyncUnitOfWork) -> None:
    for t in NEW_TYPES:
        repo = get_tag_link_repository(t, uow)
        assert repo is not None
        assert repo.entity_id_attr  # bound to a real column name


async def test_new_link_tables_exist(uow: AsyncUnitOfWork) -> None:
    async with uow:
        for table in NEW_LINK_TABLES:
            res = await uow.session.execute(
                text("SELECT to_regclass(:t)"), {"t": table}
            )
            assert res.scalar_one() is not None, f"{table} missing — migration 050 not applied"
