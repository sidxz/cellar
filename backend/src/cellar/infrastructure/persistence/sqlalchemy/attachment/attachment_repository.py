"""SQLAlchemy repository for Attachment aggregate."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.attachment.attachment import Attachment
from cellar.domain.attachment.enums import AttachableType
from cellar.infrastructure.persistence.sqlalchemy.attachment.attachment_model import (
    AttachmentModel,
)
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)


class SQLAlchemyAttachmentRepository(SQLAlchemyRepository[Attachment, AttachmentModel]):
    model_class = AttachmentModel

    def _to_domain(self, model: AttachmentModel) -> Attachment:
        return Attachment(
            id=model.id,
            workspace_id=model.workspace_id,
            file_name=model.file_name,
            mime_type=model.mime_type,
            file_size=model.file_size,
            storage_key=model.storage_key,
            attachable_type=AttachableType(model.attachable_type),
            attachable_id=model.attachable_id,
            uploaded_by=model.uploaded_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: Attachment) -> AttachmentModel:
        return AttachmentModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            file_name=aggregate.file_name,
            mime_type=aggregate.mime_type,
            file_size=aggregate.file_size,
            storage_key=aggregate.storage_key,
            attachable_type=aggregate.attachable_type.value,
            attachable_id=aggregate.attachable_id,
            uploaded_by=aggregate.uploaded_by,
            version=aggregate.version,
        )

    def _update_model(self, model: AttachmentModel, aggregate: Attachment) -> None:
        model.attachable_id = aggregate.attachable_id
        model.updated_at = aggregate.updated_at

    async def delete(self, attachment: Attachment) -> None:
        """Hard-delete an attachment record (workspace-scoped)."""
        model = await self._session.get(AttachmentModel, attachment.id)
        if model is not None and model.workspace_id == attachment.workspace_id:
            await self._session.delete(model)

    async def find_by_entity(
        self, workspace_id: uuid.UUID, attachable_type: AttachableType, attachable_id: uuid.UUID
    ) -> list[Attachment]:
        """List all attachments for a given entity."""
        stmt = (
            select(AttachmentModel)
            .where(
                AttachmentModel.workspace_id == workspace_id,
                AttachmentModel.attachable_type == attachable_type.value,
                AttachmentModel.attachable_id == attachable_id,
            )
            .order_by(AttachmentModel.created_at)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars()]
