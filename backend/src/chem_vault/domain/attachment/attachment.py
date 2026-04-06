"""Attachment aggregate root."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.attachment.enums import AttachableType
from chem_vault.domain.attachment.events import AttachmentDeleted, AttachmentUploaded
from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError


class Attachment(AggregateRoot):
    """A file attached to a domain entity (molecule, batch, protocol, run)."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        file_name: str,
        mime_type: str,
        file_size: int,
        storage_key: str,
        attachable_type: AttachableType,
        attachable_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        if not file_name or not file_name.strip():
            raise ValidationError("file_name must be non-empty")
        if not mime_type or not mime_type.strip():
            raise ValidationError("mime_type must be non-empty")
        if file_size <= 0:
            raise ValidationError("file_size must be greater than zero")

        self.workspace_id = workspace_id
        self.file_name = file_name.strip()
        self.mime_type = mime_type.strip()
        self.file_size = file_size
        self.storage_key = storage_key
        self.attachable_type = attachable_type
        self.attachable_id = attachable_id
        self.uploaded_by = uploaded_by

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        file_name: str,
        mime_type: str,
        file_size: int,
        storage_key: str,
        attachable_type: AttachableType,
        attachable_id: uuid.UUID,
        uploaded_by: uuid.UUID,
    ) -> Attachment:
        """Factory method — creates attachment and registers domain event."""
        attachment = cls(
            workspace_id=workspace_id,
            file_name=file_name,
            mime_type=mime_type,
            file_size=file_size,
            storage_key=storage_key,
            attachable_type=attachable_type,
            attachable_id=attachable_id,
            uploaded_by=uploaded_by,
        )
        attachment.register_event(
            AttachmentUploaded(
                aggregate_id=attachment.id,
                aggregate_type="Attachment",
                workspace_id=workspace_id,
                attachable_type=attachable_type.value,
                attachable_id=attachable_id,
                file_name=attachment.file_name,
                mime_type=attachment.mime_type,
                file_size=file_size,
            )
        )
        return attachment

    def delete(self) -> None:
        """Mark for deletion and register domain event."""
        self.register_event(
            AttachmentDeleted(
                aggregate_id=self.id,
                aggregate_type="Attachment",
                workspace_id=self.workspace_id,
                attachable_type=self.attachable_type.value,
                attachable_id=self.attachable_id,
                file_name=self.file_name,
            )
        )

    def repoint(self, target_id: uuid.UUID) -> None:
        """Re-point to a different entity (used during molecule merge)."""
        self.attachable_id = target_id
        self.updated_at = datetime.now(UTC)
