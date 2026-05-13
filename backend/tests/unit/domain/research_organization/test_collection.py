"""Tests for Collection aggregate."""

import uuid

import pytest

from cellar.domain.research_organization.collection import Collection
from cellar.domain.research_organization.events import CollectionCreated
from cellar.domain.shared.errors import ValidationError


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


class TestCollectionCreate:
    def test_factory_sets_fields(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        project_id = uuid.uuid4()
        org_id = uuid.uuid4()
        collection = Collection.create(
            workspace_id=ws_id,
            name="Hit Compounds",
            description="Confirmed hits from HTS",
            project_id=project_id,
            owned_by_org_id=org_id,
            created_by=user_id,
        )
        assert collection.workspace_id == ws_id
        assert collection.name == "Hit Compounds"
        assert collection.description == "Confirmed hits from HTS"
        assert collection.project_id == project_id
        assert collection.owned_by_org_id == org_id
        assert collection.created_by == user_id
        assert collection.molecule_count == 0
        assert collection.version == 1

    def test_factory_emits_created_event(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        collection = Collection.create(
            workspace_id=ws_id, name="Leads", created_by=user_id
        )
        events = collection.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], CollectionCreated)
        assert events[0].aggregate_id == collection.id
        assert events[0].workspace_id == ws_id
        assert events[0].name == "Leads"

    def test_name_is_stripped(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        collection = Collection.create(
            workspace_id=ws_id, name="  Spaced  ", created_by=user_id
        )
        assert collection.name == "Spaced"

    def test_empty_name_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            Collection.create(workspace_id=ws_id, name="", created_by=user_id)

    def test_blank_name_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            Collection.create(workspace_id=ws_id, name="   ", created_by=user_id)

    def test_optional_fields_default_none(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        collection = Collection.create(
            workspace_id=ws_id, name="Minimal", created_by=user_id
        )
        assert collection.description is None
        assert collection.project_id is None
        assert collection.owned_by_org_id is None


class TestCollectionUpdate:
    def test_update_name(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        collection = Collection.create(
            workspace_id=ws_id, name="Old Name", created_by=user_id
        )
        collection.update(name="New Name")
        assert collection.name == "New Name"

    def test_update_description(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        collection = Collection.create(
            workspace_id=ws_id, name="C1", created_by=user_id
        )
        collection.update(description="Now described")
        assert collection.description == "Now described"

    def test_update_description_to_none(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        collection = Collection.create(
            workspace_id=ws_id, name="C1", description="Old", created_by=user_id
        )
        collection.update(description=None)
        assert collection.description is None

    def test_update_project_id(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        collection = Collection.create(
            workspace_id=ws_id, name="C1", created_by=user_id
        )
        pid = uuid.uuid4()
        collection.update(project_id=pid)
        assert collection.project_id == pid

    def test_update_project_id_to_none(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        pid = uuid.uuid4()
        collection = Collection.create(
            workspace_id=ws_id, name="C1", project_id=pid, created_by=user_id
        )
        collection.update(project_id=None)
        assert collection.project_id is None

    def test_update_owned_by_org_id(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        collection = Collection.create(
            workspace_id=ws_id, name="C1", created_by=user_id
        )
        org_id = uuid.uuid4()
        collection.update(owned_by_org_id=org_id)
        assert collection.owned_by_org_id == org_id

    def test_update_empty_name_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        collection = Collection.create(
            workspace_id=ws_id, name="C1", created_by=user_id
        )
        with pytest.raises(ValidationError, match="name must not be empty"):
            collection.update(name="")

    def test_update_blank_name_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        collection = Collection.create(
            workspace_id=ws_id, name="C1", created_by=user_id
        )
        with pytest.raises(ValidationError, match="name must not be empty"):
            collection.update(name="   ")
