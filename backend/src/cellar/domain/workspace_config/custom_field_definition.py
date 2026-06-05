"""CustomFieldDefinition aggregate — domain model for workspace-scoped custom fields."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError
from cellar.domain.workspace_config.enums import FieldDataType, FieldTarget
from cellar.domain.workspace_config.events import (
    CustomFieldDefinitionCreated,
    CustomFieldDefinitionDeactivated,
    CustomFieldDefinitionUpdated,
)

__all__ = ["CustomFieldDefinition"]

# Sentinel for "not provided" in update()
UNSET = object()


class CustomFieldDefinition(AggregateRoot):
    """Aggregate root for a workspace-scoped custom field schema definition.

    A CustomFieldDefinition describes a single extensible attribute that can be
    attached to molecules, batches, or samples. It controls the field's data type,
    display metadata, picklist values (or controlled-vocabulary link), and
    required/default behaviour.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        label: str,
        data_type: FieldDataType,
        applies_to: FieldTarget,
        is_required: bool = False,
        default_value: Any | None = None,
        display_order: int = 0,
        pick_list_values: list[str] | None = None,
        vocabulary_id: uuid.UUID | None = None,
        is_active: bool = True,
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
        self.label = label
        self.data_type = FieldDataType(data_type)
        self.applies_to = FieldTarget(applies_to)
        self.is_required = is_required
        self.default_value = default_value
        self.display_order = display_order
        self.pick_list_values = list(pick_list_values) if pick_list_values else None
        self.vocabulary_id = vocabulary_id
        self.is_active = is_active

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        label: str,
        data_type: FieldDataType,
        applies_to: FieldTarget,
        is_required: bool = False,
        default_value: Any | None = None,
        display_order: int = 0,
        pick_list_values: list[str] | None = None,
        vocabulary_id: uuid.UUID | None = None,
    ) -> CustomFieldDefinition:
        """Create and validate a new CustomFieldDefinition."""
        if not name or not name.strip():
            raise ValidationError("name must not be empty")
        if not label or not label.strip():
            raise ValidationError("label must not be empty")

        cls._validate_picklist_config(data_type, pick_list_values, vocabulary_id)

        cfd = cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            name=name.strip(),
            label=label.strip(),
            data_type=data_type,
            applies_to=applies_to,
            is_required=is_required,
            default_value=default_value,
            display_order=display_order,
            pick_list_values=pick_list_values,
            vocabulary_id=vocabulary_id,
        )
        cfd.register_event(
            CustomFieldDefinitionCreated(
                aggregate_id=cfd.id,
                aggregate_type="CustomFieldDefinition",
                workspace_id=workspace_id,
                name=name.strip(),
                applies_to=applies_to.value,
            )
        )
        return cfd

    # ------------------------------------------------------------------
    # Invariant helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_picklist_config(
        data_type: FieldDataType,
        pick_list_values: list[str] | None,
        vocabulary_id: uuid.UUID | None,
    ) -> None:
        if data_type != FieldDataType.PICKLIST:
            if pick_list_values or vocabulary_id:
                raise ValidationError("pick_list_values/vocabulary_id only for picklist type")
            return
        if pick_list_values and vocabulary_id:
            raise ValidationError("pick_list_values and vocabulary_id are mutually exclusive")

    # ------------------------------------------------------------------
    # Mutation commands
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        label: str | object = UNSET,
        is_required: bool | object = UNSET,
        default_value: Any | object = UNSET,
        display_order: int | object = UNSET,
        pick_list_values: list[str] | None | object = UNSET,
        vocabulary_id: uuid.UUID | None | object = UNSET,
    ) -> None:
        """Partial update — only provided fields are changed."""
        if label is not UNSET:
            if not label or not str(label).strip():
                raise ValidationError("label must not be empty")
            self.label = str(label).strip()
        if is_required is not UNSET:
            self.is_required = bool(is_required)
        if default_value is not UNSET:
            self.default_value = default_value
        if display_order is not UNSET:
            self.display_order = int(display_order)  # type: ignore[arg-type]
        if pick_list_values is not UNSET:
            self.pick_list_values = (
                list(pick_list_values) if pick_list_values else None  # type: ignore[arg-type]
            )
        if vocabulary_id is not UNSET:
            self.vocabulary_id = vocabulary_id  # type: ignore[assignment]

        # Re-validate picklist invariant if any picklist-related field changed
        if pick_list_values is not UNSET or vocabulary_id is not UNSET:
            self._validate_picklist_config(
                self.data_type, self.pick_list_values, self.vocabulary_id
            )

        self.updated_at = datetime.now(UTC)
        self.register_event(
            CustomFieldDefinitionUpdated(
                aggregate_id=self.id,
                aggregate_type="CustomFieldDefinition",
                workspace_id=self.workspace_id,
            )
        )

    def deactivate(self) -> None:
        """Mark this field definition as inactive (soft-delete)."""
        self.is_active = False
        self.updated_at = datetime.now(UTC)
        self.register_event(
            CustomFieldDefinitionDeactivated(
                aggregate_id=self.id,
                aggregate_type="CustomFieldDefinition",
                workspace_id=self.workspace_id,
            )
        )

    def activate(self) -> None:
        """Re-enable a previously deactivated field definition."""
        self.is_active = True
        self.updated_at = datetime.now(UTC)
        self.register_event(
            CustomFieldDefinitionUpdated(
                aggregate_id=self.id,
                aggregate_type="CustomFieldDefinition",
                workspace_id=self.workspace_id,
            )
        )
