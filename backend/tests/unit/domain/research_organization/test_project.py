"""Tests for Project aggregate."""

import uuid

import pytest

from cellar.domain.research_organization.events import (
    ProjectArchived,
    ProjectCreated,
    ProjectOwnerChanged,
)
from cellar.domain.research_organization.project import Project, ProjectStatus
from cellar.domain.shared.errors import ValidationError


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


class TestProjectCreate:
    def test_factory_defaults(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project = Project.create(
            workspace_id=ws_id,
            name="Kinase Inhibitors",
            description="Research on kinase targets",
            created_by=user_id,
        )
        assert project.status == ProjectStatus.ACTIVE
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


class TestProjectUpdate:
    def test_update_name(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project = Project.create(
            workspace_id=ws_id, name="Old Name", created_by=user_id
        )
        project.clear_events()
        project.update(name="New Name")
        assert project.name == "New Name"

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


class TestProjectOwner:
    def test_owner_change_records_old_and_new(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        old, new = uuid.uuid4(), uuid.uuid4()
        p = Project.create(
            workspace_id=ws_id, name="TB", created_by=user_id, created_by_org_id=old
        )
        assert p.owner_org_id == old
        p.clear_events()
        p.change_owner(new)
        (event,) = p.collect_events()
        assert isinstance(event, ProjectOwnerChanged)
        assert event.audit_changes() == [("owner_org_id", str(old), str(new))]

    def test_archived_project_owner_change_refused(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        p = Project.create(workspace_id=ws_id, name="TB", created_by=user_id)
        p.archive(archived_by=user_id)
        with pytest.raises(ValidationError):
            p.change_owner(uuid.uuid4())
