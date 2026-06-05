"""Workspace Config value objects."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

__all__ = [
    "FieldOverride",
]


class FieldOverride(BaseModel):
    """Frozen VO that overrides one field definition attribute within a form template."""

    model_config = ConfigDict(frozen=True)

    field_definition_id: uuid.UUID
    is_required: bool | None = None
    default_value: Any | None = None
    is_locked: bool = False
    pick_list_subset: list[str] | None = None

    @model_validator(mode="after")
    def _locked_requires_default(self) -> FieldOverride:
        if self.is_locked and self.default_value is None:
            raise ValueError(
                "A locked field override must have a default_value set; "
                "is_locked=True requires default_value to be non-None."
            )
        return self
