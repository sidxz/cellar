"""Unit tests for project membership domain types."""

import uuid

import pytest

from cellar.domain.research_organization.project_membership import (
    ProjectMember,
    ProjectRole,
)


class TestProjectRole:
    def test_values(self) -> None:
        assert ProjectRole.VIEWER == "viewer"
        assert ProjectRole.EDITOR == "editor"
        assert ProjectRole.MANAGER == "manager"

    def test_hierarchy(self) -> None:
        assert ProjectRole.VIEWER.level < ProjectRole.EDITOR.level
        assert ProjectRole.EDITOR.level < ProjectRole.MANAGER.level

    def test_has_at_least(self) -> None:
        assert ProjectRole.MANAGER.has_at_least(ProjectRole.VIEWER)
        assert ProjectRole.MANAGER.has_at_least(ProjectRole.MANAGER)
        assert ProjectRole.EDITOR.has_at_least(ProjectRole.VIEWER)
        assert not ProjectRole.VIEWER.has_at_least(ProjectRole.EDITOR)


class TestProjectMember:
    def test_create(self) -> None:
        pid = uuid.uuid4()
        uid = uuid.uuid4()
        m = ProjectMember(project_id=pid, user_id=uid, role=ProjectRole.EDITOR)
        assert m.project_id == pid
        assert m.user_id == uid
        assert m.role == ProjectRole.EDITOR

    def test_frozen(self) -> None:
        m = ProjectMember(
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            role=ProjectRole.VIEWER,
        )
        with pytest.raises(AttributeError):
            m.role = ProjectRole.MANAGER  # type: ignore[misc]
