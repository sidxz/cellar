"""Unit tests for the GetTagsForEntity query."""

from __future__ import annotations

import uuid

import pytest
from returns.result import Success

from cellar.application.workspace_config.tagging.get_tags_for_entity import (
    GetTagsForEntity,
    GetTagsForEntityQuery,
)
from cellar.domain.workspace_config.tagging.tag import TaggableEntityType
from tests.unit.application.workspace_config.tagging._helpers import (
    FakeUnitOfWork,
    fake_auth,
    make_link_provider,
    make_tag,
)


class TestGetTagsForEntity:
    @pytest.mark.asyncio
    async def test_returns_entity_tags(self) -> None:
        auth = fake_auth()
        tag = make_tag(auth.workspace_id, "hit", None, auth.user_id)
        provider = make_link_provider(current_tags=[tag])
        uc = GetTagsForEntity(FakeUnitOfWork(), provider)

        query = GetTagsForEntityQuery(
            workspace_id=auth.workspace_id,
            entity_type=TaggableEntityType.MOLECULE,
            entity_id=uuid.uuid4(),
        )
        result = await uc(query, auth=auth)

        assert isinstance(result, Success)
        assigned = result.unwrap()
        assert [a.tag for a in assigned] == [tag]
