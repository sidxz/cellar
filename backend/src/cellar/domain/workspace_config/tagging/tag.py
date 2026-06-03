"""Tag aggregate, TagName value object, and the taggable-entity enum for the tagging sub-domain.

A tag is a ``key`` with an OPTIONAL ``value`` (AWS-style); display casing is
preserved. Case-insensitive dedup is achieved via the ``normalized_key`` /
``normalized_value`` properties (used by the persistence-layer unique index and
``get_or_create``) — note that ``TagName`` value equality itself is on the raw
fields, not the normalized forms.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator

from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.workspace_config.tagging.events import TagCreated, TagRenamed

_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_KEY_LEN = 128
_MAX_VALUE_LEN = 256


class TaggableEntityType(str, Enum):
    """Entity types that can carry tags (one link table each)."""

    MOLECULE = "Molecule"
    PROTOCOL = "Protocol"
    PROJECT = "Project"
    COLLECTION = "Collection"


class TagName(BaseModel):
    """Immutable (key, optional value) with case-insensitive normalization.

    - ``key`` is required and non-empty after trim (<= 128 chars).
    - ``value`` is optional (<= 256 chars); an all-whitespace value becomes ``None``.
    - Control characters are rejected in both.
    """

    model_config = ConfigDict(frozen=True)

    key: str
    value: str | None = None

    @field_validator("key")
    @classmethod
    def _validate_key(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Tag key must not be empty")
        if len(v) > _MAX_KEY_LEN:
            raise ValueError(f"Tag key must be at most {_MAX_KEY_LEN} characters")
        if _CONTROL_RE.search(v):
            raise ValueError("Tag key must not contain control characters")
        return v

    @field_validator("value")
    @classmethod
    def _validate_value(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if v == "":
            return None
        if len(v) > _MAX_VALUE_LEN:
            raise ValueError(f"Tag value must be at most {_MAX_VALUE_LEN} characters")
        if _CONTROL_RE.search(v):
            raise ValueError("Tag value must not contain control characters")
        return v

    @property
    def normalized_key(self) -> str:
        return self.key.casefold()

    @property
    def normalized_value(self) -> str | None:
        return self.value.casefold() if self.value is not None else None


class Tag(AggregateRoot):
    """Workspace-scoped, free-form (key, optional value) tag with provenance.

    Dedup/identity is by normalized (key, value) within a workspace — enforced
    by a unique index at the persistence layer. The display casing is preserved.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: TagName,
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self._name = name
        self.created_by = created_by

    @property
    def name(self) -> TagName:
        return self._name

    @property
    def key(self) -> str:
        return self._name.key

    @property
    def value(self) -> str | None:
        return self._name.value

    @property
    def normalized_key(self) -> str:
        return self._name.normalized_key

    @property
    def normalized_value(self) -> str | None:
        return self._name.normalized_value

    @classmethod
    def create(
        cls, *, workspace_id: uuid.UUID, name: TagName, created_by: uuid.UUID
    ) -> Tag:
        tag = cls(workspace_id=workspace_id, name=name, created_by=created_by)
        tag.register_event(
            TagCreated(
                aggregate_id=tag.id,
                aggregate_type="Tag",
                workspace_id=workspace_id,
                key=name.key,
                value=name.value,
            )
        )
        return tag

    def rename(self, new: TagName) -> None:
        if new == self._name:
            return
        self._name = new
        self.updated_at = datetime.now(UTC)
        self.register_event(
            TagRenamed(
                aggregate_id=self.id,
                aggregate_type="Tag",
                workspace_id=self.workspace_id,
                key=new.key,
                value=new.value,
            )
        )


@dataclass(frozen=True, kw_only=True)
class AssignedTag:
    """A :class:`Tag` as applied to one entity, with assignment provenance.

    Read model for the per-entity tag list: ``assigned_by`` / ``assigned_at``
    capture who linked the tag to this entity and when — distinct from the
    tag's own ``created_by`` / ``created_at`` (when the tag itself was first
    created in the workspace).
    """

    tag: Tag
    assigned_by: uuid.UUID
    assigned_at: datetime
