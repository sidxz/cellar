"""NamingLabel: how an ontology term reads inside protocol names (an admin override)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.protocol_naming import validate_name_text
from cellar.domain.workspace_config.events import NamingLabelCreated, NamingLabelUpdated

_MAX_SHORT_LABEL = 60


def clean_short_label(value: str) -> str:
    if not value or not value.strip():
        raise ValidationError("Short label must not be empty")
    validate_name_text(value, what="Short label")
    cleaned = " ".join(value.split())
    if len(cleaned) > _MAX_SHORT_LABEL:
        raise ValidationError(f"Short label must be at most {_MAX_SHORT_LABEL} characters")
    return cleaned


class NamingLabel(AggregateRoot):
    """Override of the computed short label for one ontology term (e.g. Mtb for M. tuberculosis).

    ``term_label`` is kept so registry targets, which carry organism as text, can match it.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        term_id: str,
        term_label: str,
        ontology_source: str,
        short_label: str,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        if not term_id or not term_id.strip():
            raise ValidationError("A short label needs the term id it overrides")
        if not term_label or not term_label.strip():
            raise ValidationError("A short label needs the term's label")
        self.workspace_id = workspace_id
        self.term_id = term_id.strip()
        self.term_label = " ".join(term_label.split())
        self.ontology_source = ontology_source.strip()
        self.short_label = clean_short_label(short_label)

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        term_id: str,
        term_label: str,
        ontology_source: str,
        short_label: str,
    ) -> NamingLabel:
        label = cls(
            workspace_id=workspace_id,
            term_id=term_id,
            term_label=term_label,
            ontology_source=ontology_source,
            short_label=short_label,
        )
        label.register_event(
            NamingLabelCreated(
                aggregate_id=label.id,
                aggregate_type="NamingLabel",
                workspace_id=workspace_id,
                term_id=label.term_id,
            )
        )
        return label

    def update(self, *, short_label: str) -> None:
        self.short_label = clean_short_label(short_label)
        self.updated_at = datetime.now(UTC)
        self.register_event(
            NamingLabelUpdated(
                aggregate_id=self.id,
                aggregate_type="NamingLabel",
                workspace_id=self.workspace_id,
                term_id=self.term_id,
                short_label=self.short_label,
            )
        )
