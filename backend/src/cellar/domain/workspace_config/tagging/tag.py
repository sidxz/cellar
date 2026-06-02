"""TagName value object and the taggable-entity enum for the tagging sub-domain.

A tag is a ``key`` with an OPTIONAL ``value`` (AWS-style); display casing is
preserved. Case-insensitive dedup is achieved via the ``normalized_key`` /
``normalized_value`` properties (used by the persistence-layer unique index and
``get_or_create``) — note that ``TagName`` value equality itself is on the raw
fields, not the normalized forms. The ``Tag`` aggregate is added in the next task.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator

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
