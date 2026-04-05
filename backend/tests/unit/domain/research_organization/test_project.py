"""Tests for Project aggregate."""

import uuid

import pytest

from chem_vault.domain.research_organization.events import ProjectArchived, ProjectCreated
from chem_vault.domain.research_organization.project import Project, ProjectStatus
from chem_vault.domain.shared.errors import ValidationError


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


class TestProjectCreate:
    def test_factory_sets_fields(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project = Project.create(
            workspace_id=ws_id,
            name="Kinase Inhibitors",
            description="Research on kinase targets",
            created_by=user_id,
        )
        assert project.workspace_id == ws_id
        assert project.name == "Kinase Inhibitors"
        assert project.description == "Research on kinase targets"
        assert project.status == ProjectStatus.ACTIVE
        assert project.created_by == user_id
        assert project.archived_by is None
        assert project.archived_at is None
        assert project.version == 1

    def test_factory_emits_created_event(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project = Project.create(
            workspace_id=ws_id, name="Alpha", created_by=user_id
        )
        events = project.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], ProjectCreated)
        assert events[0].aggregate_id == project.id
        assert events[0].workspace_id == ws_id
        assert events[0].name == "Alpha"

    def test_name_is_stripped(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project = Project.create(
            workspace_id=ws_id, name="  Trimmed  ", created_by=user_id
        )
        assert project.name == "Trimmed"

    def test_empty_name_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            Project.create(workspace_id=ws_id, name="", created_by=user_id)

    def test_blank_name_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            Project.create(workspace_id=ws_id, name="   ", created_by=user_id)

    def test_optional_fields_default_none(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project = Project.create(workspace_id=ws_id, name="Minimal", created_by=user_id)
        assert project.description is None


class TestProjectUpdate:
    def test_update_name(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project = Project.create(
            workspace_id=ws_id, name="Old Name", created_by=user_id
        )
        project.clear_events()
        project.update(name="New Name")
        assert project.name == "New Name"

    def test_update_description(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project = Project.create(
            workspace_id=ws_id, name="P1", description="Old", created_by=user_id
        )
        project.update(description="New desc")
        assert project.description == "New desc"

    def test_update_description_to_none(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project = Project.create(
            workspace_id=ws_id, name="P1", description="Some desc", created_by=user_id
        )
        project.update(description=None)
        assert project.description is None

    def test_update_empty_name_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project = Project.create(
            workspace_id=ws_id, name="P1", created_by=user_id
        )
        with pytest.raises(ValidationError, match="name must not be empty"):
            project.update(name="")

    def test_update_on_archived_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project = Project.create(
            workspace_id=ws_id, name="P1", created_by=user_id
        )
        project.archive(archived_by=user_id)
        with pytest.raises(ValidationError, match="Cannot modify an archived project"):
            project.update(name="New")


class TestProjectArchive:
    def test_archive_sets_status(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project = Project.create(
            workspace_id=ws_id, name="P1", created_by=user_id
        )
        project.clear_events()
        project.archive(archived_by=user_id)
        assert project.status == ProjectStatus.ARCHIVED
        assert project.archived_by == user_id
        assert project.archived_at is not None

    def test_archive_emits_event(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project = Project.create(
            workspace_id=ws_id, name="P1", created_by=user_id
        )
        project.clear_events()
        project.archive(archived_by=user_id)
        events = project.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], ProjectArchived)
        assert events[0].aggregate_id == project.id
        assert events[0].archived_by == user_id

    def test_archive_twice_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project = Project.create(
            workspace_id=ws_id, name="P1", created_by=user_id
        )
        project.archive(archived_by=user_id)
        with pytest.raises(ValidationError, match="already archived"):
            project.archive(archived_by=user_id)
