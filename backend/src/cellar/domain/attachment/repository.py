"""Attachment repository protocol."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from cellar.domain.attachment.attachment import Attachment
from cellar.domain.attachment.enums import AttachableType


@runtime_checkable
class AttachmentRepository(Protocol):
    """Repository interface for Attachment aggregate."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> Attachment | None: ...
    async def save(self, attachment: Attachment) -> None: ...
    async def delete(self, attachment: Attachment) -> None: ...
    async def find_by_entity(
        self, workspace_id: uuid.UUID, attachable_type: AttachableType, attachable_id: uuid.UUID
    ) -> list[Attachment]: ...
