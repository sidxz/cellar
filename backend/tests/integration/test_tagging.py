"""Integration tests for tagging persistence (tag registry + links + backfill)."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from cellar.domain.workspace_config.tagging.events import TagCreated
from cellar.domain.workspace_config.tagging.tag import TagName
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_repository import (
    SQLAlchemyTagRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class TestTagRepository:
    async def test_get_or_create_inserts_and_emits_event(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            tag = await repo.get_or_create(ws_id, TagName(key="Project", value="Alpha"), user_id)
            events = await uow.commit()
        assert tag.key == "Project"
        assert tag.value == "Alpha"
        assert any(isinstance(e, TagCreated) for e in events)

    async def test_get_or_create_dedups_case_insensitively(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            first = await repo.get_or_create(ws_id, TagName(key="Env", value="Prod"), user_id)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            second = await repo.get_or_create(ws_id, TagName(key="env", value="prod"), user_id)
            events = await uow.commit()
        assert first.id == second.id  # same registry row
        assert not [e for e in events if isinstance(e, TagCreated)]  # no second create

    async def test_valueless_tags_dedup(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            a = await repo.get_or_create(ws_id, TagName(key="favorite"), user_id)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            b = await repo.get_or_create(ws_id, TagName(key="FAVORITE"), user_id)
            await uow.commit()
        assert a.id == b.id

    async def test_same_name_distinct_across_workspaces(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_a, ws_b, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            ta = await repo.get_or_create(ws_a, TagName(key="shared"), user_id)
            tb = await repo.get_or_create(ws_b, TagName(key="shared"), user_id)
            await uow.commit()
        assert ta.id != tb.id

    async def test_search_substring_and_created_by(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        alice, bob = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            await repo.get_or_create(ws_id, TagName(key="kinase"), alice)
            await repo.get_or_create(ws_id, TagName(key="kinetics"), bob)
            await repo.get_or_create(ws_id, TagName(key="solubility"), alice)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            kin = await repo.search(ws_id, q="kin")
            mine = await repo.search(ws_id, created_by=alice)
        assert {t.key for t in kin} == {"kinase", "kinetics"}
        assert {t.key for t in mine} == {"kinase", "solubility"}

    async def test_find_by_id_in_workspace_scoping(self, uow: AsyncUnitOfWork) -> None:
        ws_id, other_ws, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            tag = await repo.get_or_create(ws_id, TagName(key="x"), user_id)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            assert await repo.find_by_id_in_workspace(ws_id, tag.id) is not None
            assert await repo.find_by_id_in_workspace(other_ws, tag.id) is None
