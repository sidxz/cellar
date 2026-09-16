"""Comment repository round-trip + ordering against real Postgres."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.inventory.comment import Comment
from cellar.domain.inventory.enums import CommentTarget
from cellar.infrastructure.persistence.sqlalchemy.inventory.comment_repository import (
    SQLAlchemyCommentRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@pytest.mark.integration
async def test_round_trip_and_newest_first(session_factory) -> None:
    ws = uuid.uuid4()
    target = uuid.uuid4()
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCommentRepository(uow)
        for i in range(3):
            await repo.save(
                Comment.create(
                    workspace_id=ws,
                    target_type=CommentTarget.PLATE_GROUP,
                    target_id=target,
                    body=f"note {i}",
                    author_id=None,
                    author_name="Legacy",
                )
            )
        await uow.commit()
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCommentRepository(uow)
        rows = await repo.list_for_target(ws, CommentTarget.PLATE_GROUP, target)
    assert [c.body for c in rows] == ["note 2", "note 1", "note 0"]
    assert rows[0].author_id is None and rows[0].author_name == "Legacy"
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyCommentRepository(uow)
        assert await repo.list_for_loan(ws, uuid.uuid4()) == []
