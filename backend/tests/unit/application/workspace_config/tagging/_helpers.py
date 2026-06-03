"""Fakes for tagging use-case unit tests."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

from cellar.domain.shared.events import DomainEvent
from cellar.domain.workspace_config.tagging.tag import (
    AssignedTag,
    Tag,
    TagName,
)


class FakeUnitOfWork:
    """Async-context UoW that collects + clears events from tracked aggregates."""

    def __init__(self) -> None:
        self._tracked: list = []

    @property
    def is_active(self) -> bool:
        return True

    def track(self, aggregate) -> None:
        if aggregate not in self._tracked:
            self._tracked.append(aggregate)

    async def commit(self) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for agg in self._tracked:
            events.extend(agg.collect_events())
            agg.clear_events()
        return events

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


def fake_auth(*, role: str = "editor"):
    auth = AsyncMock()
    auth.user_id = uuid.uuid4()
    auth.workspace_id = uuid.uuid4()
    auth.workspace_role = role
    auth.is_admin = role in ("admin", "owner")
    rank = {"viewer": 0, "editor": 1, "admin": 2, "owner": 3}
    auth.has_role = lambda m: rank.get(role, 0) >= rank.get(m, 99)
    return auth


def make_tag(workspace_id: uuid.UUID, key: str, value: str | None, created_by: uuid.UUID) -> Tag:
    """A freshly-created Tag (carries a TagCreated event, like get_or_create on a new row)."""
    return Tag.create(
        workspace_id=workspace_id, name=TagName(key=key, value=value), created_by=created_by
    )


def make_tag_repo(*, get_or_create: Tag, find_by_id: Tag | None = None) -> AsyncMock:
    repo = AsyncMock()
    repo.get_or_create = AsyncMock(return_value=get_or_create)
    repo.find_by_id_in_workspace = AsyncMock(return_value=find_by_id)
    return repo


def make_link_provider(
    *, entity_exists: bool = True, current_tags: list[Tag] | None = None
) -> AsyncMock:
    tags = current_tags or []
    link_repo = AsyncMock()
    link_repo.entity_exists_in_workspace = AsyncMock(return_value=entity_exists)
    link_repo.add = AsyncMock()
    link_repo.remove = AsyncMock()
    link_repo.set_for_entity = AsyncMock()
    link_repo.find_tags_for_entity = AsyncMock(return_value=tags)
    link_repo.find_assigned_tags_for_entity = AsyncMock(
        return_value=[
            AssignedTag(tag=t, assigned_by=t.created_by, assigned_at=t.created_at)
            for t in tags
        ]
    )
    provider = AsyncMock()
    provider.for_type = lambda _et: link_repo
    provider.link_repo = link_repo  # exposed for assertions
    return provider
