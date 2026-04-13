"""CustomFieldValidator — validates a custom_fields dict against workspace definitions."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from returns.result import Failure, Result, Success

from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.workspace_config.enums import FieldDataType, FieldTarget
from chem_vault.domain.workspace_config.repository import CustomFieldDefinitionRepository


class CustomFieldValidator:
    """Validates a ``custom_fields`` mapping against active CustomFieldDefinitions.

    Used by registration and batch use cases to enforce workspace-level field
    constraints before persisting compound data.
    """

    def __init__(self, *, repo: CustomFieldDefinitionRepository) -> None:
        self._repo = repo

    async def validate(
        self,
        custom_fields: dict[str, Any] | None,
        target: FieldTarget,
        workspace_id: uuid.UUID,
    ) -> Result[None, ValidationError]:
        """Validate *custom_fields* against definitions for *target* in *workspace_id*.

        Returns ``Success(None)`` when all checks pass, or
        ``Failure(ValidationError(...))`` with a joined error message.
        """
        definitions = await self._repo.find_by_workspace(
            workspace_id,
            applies_to=target,
            active_only=True,
        )

        # Build name → definition lookup
        name_to_def = {d.name: d for d in definitions}
        fields = custom_fields or {}
        errors: list[str] = []

        # --- unknown field check ---
        for field_name in fields:
            if field_name not in name_to_def:
                errors.append(f"Unknown custom field: '{field_name}'")

        # --- required field check ---
        for name, defn in name_to_def.items():
            if defn.is_required and name not in fields:
                errors.append(f"Required custom field missing: '{name}'")

        # --- type checks for provided fields ---
        for field_name, value in fields.items():
            defn = name_to_def.get(field_name)
            if defn is None:
                # Already flagged as unknown above
                continue

            type_error = self._check_type(field_name, value, defn.data_type, defn.pick_list_values)
            if type_error:
                errors.append(type_error)

        if errors:
            return Failure(ValidationError("; ".join(errors)))

        return Success(None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_type(
        field_name: str,
        value: Any,
        data_type: FieldDataType,
        pick_list_values: list[str] | None,
    ) -> str | None:
        """Return an error string if the value fails the type check, else None."""
        if data_type == FieldDataType.TEXT:
            if not isinstance(value, str):
                return f"Field '{field_name}' expects a text (string) value"

        elif data_type == FieldDataType.NUMBER:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return f"Field '{field_name}' expects a numeric value"

        elif data_type == FieldDataType.DATE:
            if not isinstance(value, (str, date, datetime)):
                return f"Field '{field_name}' expects a date value (str, date, or datetime)"

        elif data_type == FieldDataType.PICKLIST:
            allowed = pick_list_values or []
            if value not in allowed:
                return (
                    f"Field '{field_name}' value '{value}' is not in the allowed "
                    f"picklist values: {allowed}"
                )

        elif data_type == FieldDataType.BATCH_LINK:
            if not isinstance(value, str):
                return f"Field '{field_name}' expects a batch identifier (string)"

        return None
