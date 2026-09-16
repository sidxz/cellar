"""Tests for SavedSearch aggregate."""

import uuid
from datetime import UTC, datetime

import pytest

from cellar.domain.research_organization.events import SavedSearchCreated
from cellar.domain.research_organization.saved_search import (
    SavedSearch,
    SearchVisibility,
)
from cellar.domain.shared.errors import ValidationError


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
            columns={"visible": ["name", "smiles", "mw"]},
            visibility=SearchVisibility.PRIVATE,
            created_by=user_id,
        )
        assert search.workspace_id == ws_id
        assert search.name == "Benzene analogs"
        assert search.query == sample_query
        assert search.columns == {"visible": ["name", "smiles", "mw"]}
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
            columns={"visible": ["a", "b"]},
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

    def test_update_description(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id, name="S1", query=sample_query, created_by=user_id
        )
        search.update(description="Updated description")
        assert search.description == "Updated description"

    def test_update_description_to_none(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id,
            name="S1",
            query=sample_query,
            created_by=user_id,
            description="Has a description",
        )
        search.update(description=None)
        assert search.description is None

    def test_update_without_description_preserves_existing(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id,
            name="S1",
            query=sample_query,
            created_by=user_id,
            description="Original",
        )
        search.update(name="S2")
        assert search.description == "Original"


class TestSavedSearchRecordExecution:
    def test_record_execution_sets_fields(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id, name="S1", query=sample_query, created_by=user_id
        )
        before = datetime.now(UTC)
        search.record_execution(result_count=42)
        after = datetime.now(UTC)
        assert search.result_count == 42
        assert search.last_run_at is not None
        assert before <= search.last_run_at <= after

    def test_record_execution_updates_updated_at(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id, name="S1", query=sample_query, created_by=user_id
        )
        old_updated = search.updated_at
        search.record_execution(result_count=10)
        assert search.updated_at is not None
        if old_updated is not None:
            assert search.updated_at >= old_updated

    def test_record_execution_overwrites_previous(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id, name="S1", query=sample_query, created_by=user_id
        )
        search.record_execution(result_count=5)
        first_run = search.last_run_at
        search.record_execution(result_count=99)
        assert search.result_count == 99
        assert search.last_run_at is not None
        assert first_run is not None
        assert search.last_run_at >= first_run

    def test_record_execution_zero_results(
        self, ws_id: uuid.UUID, user_id: uuid.UUID, sample_query: dict
    ) -> None:
        search = SavedSearch.create(
            workspace_id=ws_id, name="S1", query=sample_query, created_by=user_id
        )
        search.record_execution(result_count=0)
        assert search.result_count == 0
        assert search.last_run_at is not None
