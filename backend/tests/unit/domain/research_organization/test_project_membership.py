"""Unit tests for project membership domain types."""

import uuid

import pytest

from cellar.domain.research_organization.project_membership import (
    ProjectMember,
    ProjectRole,
)


class TestProjectRole:

    def test_hierarchy(self) -> None:
        assert ProjectRole.VIEWER.level < ProjectRole.EDITOR.level
        assert ProjectRole.EDITOR.level < ProjectRole.MANAGER.level

    def test_has_at_least(self) -> None:
        assert ProjectRole.MANAGER.has_at_least(ProjectRole.VIEWER)
        assert ProjectRole.MANAGER.has_at_least(ProjectRole.MANAGER)
        assert ProjectRole.EDITOR.has_at_least(ProjectRole.VIEWER)
        assert not ProjectRole.VIEWER.has_at_least(ProjectRole.EDITOR)


class TestProjectMember:

    def test_frozen(self) -> None:
        m = ProjectMember(
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            role=ProjectRole.VIEWER,
        )
        with pytest.raises(AttributeError):
            m.role = ProjectRole.MANAGER  # type: ignore[misc]
