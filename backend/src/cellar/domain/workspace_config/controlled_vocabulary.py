"""ControlledVocabulary aggregate — workspace-level standardized picklists."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ConflictError, ValidationError
from cellar.domain.workspace_config.events import VocabularyCreated, VocabularyUpdated


class ControlledVocabulary(AggregateRoot):
    """Workspace-scoped standardized picklist for consistent data entry.

    Invariants:
    - Vocabulary names are unique within a workspace (enforced at repo/app layer).
    - Terms must be non-empty strings.
    - Removing a term from a locked vocabulary requires admin check (app layer).
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        terms: list[str] | None = None,
        is_locked: bool = False,
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        if not name or not name.strip():
            raise ValidationError("Vocabulary name must not be empty")
        self.workspace_id = workspace_id
        self.name = name.strip()
        self.terms = list(terms) if terms else []
        self._validate_terms(self.terms)
        self.is_locked = is_locked
        self.created_by = created_by

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        terms: list[str] | None = None,
        created_by: uuid.UUID,
    ) -> ControlledVocabulary:
        vocab = cls(
            workspace_id=workspace_id,
            name=name,
            terms=terms,
            created_by=created_by,
        )
        vocab.register_event(
            VocabularyCreated(
                aggregate_id=vocab.id,
                aggregate_type="ControlledVocabulary",
                workspace_id=workspace_id,
                name=vocab.name,
            )
        )
        return vocab

    def rename(self, new_name: str) -> None:
        if not new_name or not new_name.strip():
            raise ValidationError("Vocabulary name must not be empty")
        self.name = new_name.strip()
        self.updated_at = datetime.now(UTC)
        self._emit_updated()

    def set_terms(self, terms: list[str]) -> None:
        """Replace the entire terms list."""
        self._validate_terms(terms)
        self.terms = list(terms)
        self.updated_at = datetime.now(UTC)
        self._emit_updated()

    def add_term(self, term: str) -> None:
        if not term or not term.strip():
            raise ValidationError("Term must not be empty")
        term = term.strip()
        if term in self.terms:
            raise ConflictError(f"Term '{term}' already exists in vocabulary '{self.name}'")
        self.terms.append(term)
        self.updated_at = datetime.now(UTC)
        self._emit_updated()

    def remove_term(self, term: str) -> None:
        if term not in self.terms:
            raise ValidationError(f"Term '{term}' not found in vocabulary '{self.name}'")
        self.terms.remove(term)
        self.updated_at = datetime.now(UTC)
        self._emit_updated()

    def lock(self) -> None:
        self.is_locked = True
        self.updated_at = datetime.now(UTC)
        self._emit_updated()

    def unlock(self) -> None:
        self.is_locked = False
        self.updated_at = datetime.now(UTC)
        self._emit_updated()

    def _emit_updated(self) -> None:
        self.register_event(
            VocabularyUpdated(
                aggregate_id=self.id,
                aggregate_type="ControlledVocabulary",
                workspace_id=self.workspace_id,
                name=self.name,
            )
        )

    @staticmethod
    def _validate_terms(terms: list[str]) -> None:
        for t in terms:
            if not t or not t.strip():
                raise ValidationError("All terms must be non-empty strings")
        if len(terms) != len(set(terms)):
            raise ValidationError("Terms must be unique within a vocabulary")
