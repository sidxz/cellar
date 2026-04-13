"""RegistrationForm aggregate — workspace-scoped form template for molecule/batch registration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.workspace_config.enums import FieldTarget
from chem_vault.domain.workspace_config.events import (
    RegistrationFormCreated,
    RegistrationFormUpdated,
)
from chem_vault.domain.workspace_config.value_objects import FieldOverride

__all__ = [
    "FieldOverride",
    "RegistrationForm",
    "RegistrationFormCreated",
    "RegistrationFormUpdated",
]

# Sentinel for "not provided" in update()
UNSET = object()


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
            raise ValidationError("name must not be empty")

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
                raise ValidationError("name must not be empty")
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
        self.register_event(
            RegistrationFormUpdated(
                aggregate_id=self.id,
                aggregate_type="RegistrationForm",
                workspace_id=self.workspace_id,
            )
        )
