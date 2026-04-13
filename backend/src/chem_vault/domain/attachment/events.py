"""Attachment domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from chem_vault.domain.shared.events import DomainEvent


@dataclass(frozen=True, kw_only=True)
class AttachmentUploaded(DomainEvent):
    """Raised when a file is attached to an entity."""

    workspace_id: uuid.UUID
    attachable_type: str
    attachable_id: uuid.UUID
    file_name: str
    mime_type: str
    file_size: int


@dataclass(frozen=True, kw_only=True)
class AttachmentDeleted(DomainEvent):
    """Raised when an attachment is removed."""

    workspace_id: uuid.UUID
    attachable_type: str
    attachable_id: uuid.UUID
    file_name: str
