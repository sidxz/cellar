"""Tests for ControlledVocabulary aggregate."""

import uuid

import pytest

from cellar.domain.shared.errors import ConflictError, ValidationError
from cellar.domain.workspace_config.controlled_vocabulary import ControlledVocabulary
from cellar.domain.workspace_config.events import VocabularyCreated, VocabularyUpdated


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


class TestControlledVocabularyCreate:
    def test_factory(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        vocab = ControlledVocabulary.create(
            workspace_id=ws_id,
            name="Species",
            terms=["Human", "Mouse", "Rat"],
            created_by=user_id,
        )
        assert vocab.workspace_id == ws_id
        assert vocab.name == "Species"
        assert vocab.terms == ["Human", "Mouse", "Rat"]
        assert vocab.is_locked is False
        assert vocab.created_by == user_id

    def test_factory_emits_event(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        vocab = ControlledVocabulary.create(
            workspace_id=ws_id, name="Assay Type", created_by=user_id
        )
        events = vocab.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], VocabularyCreated)
        assert events[0].name == "Assay Type"

    def test_empty_name_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            ControlledVocabulary.create(workspace_id=ws_id, name="", created_by=user_id)

    def test_name_stripped(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        vocab = ControlledVocabulary.create(
            workspace_id=ws_id, name="  Route  ", created_by=user_id
        )
        assert vocab.name == "Route"


    def test_duplicate_terms_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="unique"):
            ControlledVocabulary.create(
                workspace_id=ws_id,
                name="Bad List",
                terms=["A", "B", "A"],
                created_by=user_id,
            )

    def test_empty_term_string_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="non-empty"):
            ControlledVocabulary.create(
                workspace_id=ws_id,
                name="Bad",
                terms=["OK", ""],
                created_by=user_id,
            )


class TestControlledVocabularyTerms:
    def test_add_term(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        vocab = ControlledVocabulary.create(
            workspace_id=ws_id, name="Species", terms=["Human"], created_by=user_id
        )
        vocab.clear_events()
        vocab.add_term("Mouse")
        assert vocab.terms == ["Human", "Mouse"]
        assert len(vocab.collect_events()) == 1
        assert isinstance(vocab.collect_events()[0], VocabularyUpdated)

    def test_add_duplicate_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        vocab = ControlledVocabulary.create(
            workspace_id=ws_id, name="Species", terms=["Human"], created_by=user_id
        )
        with pytest.raises(ConflictError, match="already exists"):
            vocab.add_term("Human")

    def test_add_empty_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        vocab = ControlledVocabulary.create(
            workspace_id=ws_id, name="Species", created_by=user_id
        )
        with pytest.raises(ValidationError, match="not be empty"):
            vocab.add_term("")

    def test_remove_term(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        vocab = ControlledVocabulary.create(
            workspace_id=ws_id, name="Species", terms=["Human", "Mouse"], created_by=user_id
        )
        vocab.remove_term("Mouse")
        assert vocab.terms == ["Human"]

    def test_remove_missing_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        vocab = ControlledVocabulary.create(
            workspace_id=ws_id, name="Species", terms=["Human"], created_by=user_id
        )
        with pytest.raises(ValidationError, match="not found"):
            vocab.remove_term("Dog")

    def test_set_terms(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        vocab = ControlledVocabulary.create(
            workspace_id=ws_id, name="Species", terms=["Human"], created_by=user_id
        )
        vocab.set_terms(["Rat", "Zebrafish"])
        assert vocab.terms == ["Rat", "Zebrafish"]


class TestControlledVocabularyRename:
    def test_rename(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        vocab = ControlledVocabulary.create(
            workspace_id=ws_id, name="Old", created_by=user_id
        )
        vocab.rename("New Name")
        assert vocab.name == "New Name"

    def test_rename_empty_raises(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        vocab = ControlledVocabulary.create(
            workspace_id=ws_id, name="Old", created_by=user_id
        )
        with pytest.raises(ValidationError, match="name must not be empty"):
            vocab.rename("")


class TestControlledVocabularyLocking:
    def test_lock_and_unlock(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        vocab = ControlledVocabulary.create(
            workspace_id=ws_id, name="Species", created_by=user_id
        )
        assert vocab.is_locked is False
        vocab.lock()
        assert vocab.is_locked is True
        vocab.unlock()
        assert vocab.is_locked is False
