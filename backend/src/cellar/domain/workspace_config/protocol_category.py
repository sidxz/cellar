"""ProtocolCategory: a protocol category and the pattern its protocol names follow."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.protocol_naming import (
    DEFAULT_CATEGORY_PATTERNS,
    generic_pattern,
    validate_name_text,
    validate_pattern,
)
from cellar.domain.workspace_config.events import ProtocolCategoryCreated, ProtocolCategoryUpdated

_MAX_LABEL_LENGTH = 100


def _clean_label(label: str) -> str:
    if not label or not label.strip():
        raise ValidationError("Category label must not be empty")
    validate_name_text(label, what="Category label")
    cleaned = " ".join(label.split())
    if len(cleaned) > _MAX_LABEL_LENGTH:
        raise ValidationError(f"Category label must be at most {_MAX_LABEL_LENGTH} characters")
    return cleaned


class ProtocolCategory(AggregateRoot):
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        label: str,
        name_pattern: str,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.label = _clean_label(label)
        validate_pattern(name_pattern)
        self.name_pattern = name_pattern.strip()

    @classmethod
    def create(
        cls, *, workspace_id: uuid.UUID, label: str, name_pattern: str | None = None
    ) -> ProtocolCategory:
        cleaned = _clean_label(label)
        pattern = (
            name_pattern or DEFAULT_CATEGORY_PATTERNS.get(cleaned) or generic_pattern(cleaned)
        )
        category = cls(workspace_id=workspace_id, label=cleaned, name_pattern=pattern)
        category.register_event(
            ProtocolCategoryCreated(
                aggregate_id=category.id,
                aggregate_type="ProtocolCategory",
                workspace_id=workspace_id,
                label=cleaned,
            )
        )
        return category

    @property
    def default_pattern(self) -> str:
        return DEFAULT_CATEGORY_PATTERNS.get(self.label) or generic_pattern(self.label)

    def update(self, *, label: str | None = None, name_pattern: str | None = None) -> None:
        if label is not None:
            self.label = _clean_label(label)
        if name_pattern is not None:
            validate_pattern(name_pattern)
            self.name_pattern = name_pattern.strip()
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ProtocolCategoryUpdated(
                aggregate_id=self.id,
                aggregate_type="ProtocolCategory",
                workspace_id=self.workspace_id,
                label=self.label,
                name_pattern=self.name_pattern,
            )
        )
