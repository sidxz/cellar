"""RegistrationForm aggregate — workspace-scoped form template for molecule/batch registration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.events import DomainEvent
from chem_vault.domain.workspace_config.enums import FieldTarget

__all__ = [
    "FieldOverride",
    "RegistrationForm",
    "RegistrationFormCreated",
    "RegistrationFormUpdated",
]

# Sentinel for "not provided" in update()
UNSET = object()


# ---------------------------------------------------------------------------
# Domain Events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegistrationFormCreated(DomainEvent):
    workspace_id: uuid.UUID
    name: str
    applies_to: str


@dataclass(frozen=True)
class RegistrationFormUpdated(DomainEvent):
    workspace_id: uuid.UUID


# ---------------------------------------------------------------------------
# Value Object
# ---------------------------------------------------------------------------


class FieldOverride(BaseModel):
    """Frozen VO that overrides one field definition attribute within a form template."""

    model_config = ConfigDict(frozen=True)

    field_definition_id: uuid.UUID
    is_required: bool | None = None
    default_value: Any | None = None
    is_locked: bool = False
    pick_list_subset: list[str] | None = None

    @model_validator(mode="after")
    def _locked_requires_default(self) -> "FieldOverride":
        if self.is_locked and self.default_value is None:
            raise ValueError(
                "A locked field override must have a default_value set; "
                "is_locked=True requires default_value to be non-None."
            )
        return self


# ---------------------------------------------------------------------------
# Aggregate Root
# ---------------------------------------------------------------------------


class RegistrationForm(AggregateRoot):
    """Aggregate root for a workspace-scoped registration form template.

    A RegistrationForm describes the set of field overrides that are active
    when registering an entity of a given type (molecule or batch) in a
    particular workspace.  At most one form per ``applies_to`` per workspace
    may be flagged as ``is_default``.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID,
        workspace_id: uuid.UUID,
        name: str,
        applies_to: FieldTarget,
        is_default: bool = False,
        field_overrides: list[FieldOverride] | None = None,
        version: int = 1,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(
            id=id,
            version=version,
            created_at=created_at,
            updated_at=updated_at,
        )
        self.workspace_id = workspace_id
        self.name = name
        self.applies_to = FieldTarget(applies_to)
        self.is_default = is_default
        self.field_overrides: list[FieldOverride] = list(field_overrides) if field_overrides else []

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        applies_to: FieldTarget,
        is_default: bool = False,
        field_overrides: list[FieldOverride] | None = None,
    ) -> "RegistrationForm":
        """Create and validate a new RegistrationForm."""
        if not name or not name.strip():
            raise ValueError("name must not be empty")

        form = cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            name=name.strip(),
            applies_to=applies_to,
            is_default=is_default,
            field_overrides=field_overrides,
        )
        form.register_event(
            RegistrationFormCreated(
                aggregate_id=form.id,
                aggregate_type="RegistrationForm",
                workspace_id=workspace_id,
                name=name.strip(),
                applies_to=applies_to.value,
            )
        )
        return form

    # ------------------------------------------------------------------
    # Mutation commands
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        name: str | object = UNSET,
        field_overrides: list[FieldOverride] | None | object = UNSET,
    ) -> None:
        """Partial update — only provided fields are changed."""
        if name is not UNSET:
            if not name or not str(name).strip():
                raise ValueError("name must not be empty")
            self.name = str(name).strip()

        if field_overrides is not UNSET:
            self.field_overrides = list(field_overrides) if field_overrides else []  # type: ignore[arg-type]

        self.updated_at = datetime.now(timezone.utc)
        self.register_event(
            RegistrationFormUpdated(
                aggregate_id=self.id,
                aggregate_type="RegistrationForm",
                workspace_id=self.workspace_id,
            )
        )

    def set_default(self, is_default: bool) -> None:
        """Set or unset this form as the workspace default for its applies_to type."""
        self.is_default = is_default
        self.updated_at = datetime.now(timezone.utc)
