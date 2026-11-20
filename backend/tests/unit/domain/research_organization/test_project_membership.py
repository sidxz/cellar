"""Unit tests for project membership domain types."""

from cellar.domain.research_organization.project_membership import ProjectRole


class TestProjectRole:
    def test_hierarchy(self) -> None:
        assert ProjectRole.VIEWER.level < ProjectRole.EDITOR.level
        assert ProjectRole.EDITOR.level < ProjectRole.MANAGER.level

    def test_has_at_least(self) -> None:
        assert ProjectRole.MANAGER.has_at_least(ProjectRole.VIEWER)
        assert ProjectRole.MANAGER.has_at_least(ProjectRole.MANAGER)
        assert ProjectRole.EDITOR.has_at_least(ProjectRole.VIEWER)
        assert not ProjectRole.VIEWER.has_at_least(ProjectRole.EDITOR)
