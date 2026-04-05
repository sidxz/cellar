"""Tests for SavedSearch aggregate."""

import uuid

import pytest

from chem_vault.domain.research_organization.events import SavedSearchCreated
from chem_vault.domain.research_organization.saved_search import (
    SavedSearch,
    SearchVisibility,
)
from chem_vault.domain.shared.errors import ValidationError


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_query() -> dict:
    return {"type": "similarity", "smiles": "c1ccccc1", "threshold": 0.7}


class TestSavedSearchCreate:
    def test_factory_sets_fields(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id,
            name="Benzene analogs",
            query=sample_query,
            columns=["name", "smiles", "mw"],
            visibility=SearchVisibility.PRIVATE,
            created_by=user_id,
        )
        assert search.workspace_id == ws_id
        assert search.name == "Benzene analogs"
        assert search.query == sample_query
        assert search.columns == ["name", "smiles", "mw"]
        assert search.visibility == SearchVisibility.PRIVATE
        assert search.project_id is None
        assert search.created_by == user_id
        assert search.version == 1

    def test_factory_emits_created_event(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id,
            name="My Search",
            query=sample_query,
            created_by=user_id,
        )
        events = search.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], SavedSearchCreated)
        assert events[0].aggregate_id == search.id
        assert events[0].workspace_id == ws_id
        assert events[0].name == "My Search"

    def test_name_is_stripped(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id, name="  Padded  ", query=sample_query, created_by=user_id
        )
        assert search.name == "Padded"

    def test_empty_name_raises(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            SavedSearch.create(
                workspace_id=ws_id, name="", query=sample_query, created_by=user_id
            )

    def test_blank_name_raises(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            SavedSearch.create(
                workspace_id=ws_id, name="   ", query=sample_query, created_by=user_id
            )

    def test_query_is_copied(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        original = {"smiles": "CCO"}
        search = SavedSearch.create(
            workspace_id=ws_id, name="Copy test", query=original, created_by=user_id
        )
        original["smiles"] = "MUTATED"
        assert search.query["smiles"] == "CCO"

    def test_columns_default_none(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id, name="No cols", query=sample_query, created_by=user_id
        )
        assert search.columns is None


class TestSavedSearchVisibility:
    def test_project_visibility_requires_project_id(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        with pytest.raises(ValidationError, match="PROJECT visibility requires a project_id"):
            SavedSearch.create(
                workspace_id=ws_id,
                name="Bad",
                query=sample_query,
                visibility=SearchVisibility.PROJECT,
                project_id=None,
                created_by=user_id,
            )

    def test_project_visibility_with_project_id_ok(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        pid = uuid.uuid4()
        search = SavedSearch.create(
            workspace_id=ws_id,
            name="Project search",
            query=sample_query,
            visibility=SearchVisibility.PROJECT,
            project_id=pid,
            created_by=user_id,
        )
        assert search.visibility == SearchVisibility.PROJECT
        assert search.project_id == pid

    def test_private_visibility_without_project_id_ok(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id,
            name="Private",
            query=sample_query,
            visibility=SearchVisibility.PRIVATE,
            created_by=user_id,
        )
        assert search.visibility == SearchVisibility.PRIVATE


class TestSavedSearchUpdate:
    def test_update_name(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id, name="Old", query=sample_query, created_by=user_id
        )
        search.update(name="New")
        assert search.name == "New"

    def test_update_query(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id, name="S1", query=sample_query, created_by=user_id
        )
        new_query = {"type": "substructure", "smiles": "c1ccncc1"}
        search.update(query=new_query)
        assert search.query == new_query

    def test_update_columns_to_none(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id,
            name="S1",
            query=sample_query,
            columns=["a", "b"],
            created_by=user_id,
        )
        search.update(columns=None)
        assert search.columns is None

    def test_update_empty_name_raises(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id, name="S1", query=sample_query, created_by=user_id
        )
        with pytest.raises(ValidationError, match="name must not be empty"):
            search.update(name="")

    def test_update_to_project_visibility_without_project_id_raises(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id, name="S1", query=sample_query, created_by=user_id
        )
        with pytest.raises(ValidationError, match="PROJECT visibility requires a project_id"):
            search.update(visibility=SearchVisibility.PROJECT)

    def test_update_to_project_visibility_with_project_id_ok(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id, name="S1", query=sample_query, created_by=user_id
        )
        pid = uuid.uuid4()
        search.update(visibility=SearchVisibility.PROJECT, project_id=pid)
        assert search.visibility == SearchVisibility.PROJECT
        assert search.project_id == pid
