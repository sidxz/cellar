"""List attachments for an entity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_workspace_role
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.attachment.attachment import Attachment
from cellar.domain.attachment.enums import AttachableType
from cellar.domain.attachment.repository import AttachmentRepository
from cellar.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListAttachmentsQuery(Query):
    workspace_id: uuid.UUID
    attachable_type: AttachableType
    attachable_id: uuid.UUID


class ListAttachments:
    def __init__(self, uow: UnitOfWork, repo: AttachmentRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListAttachmentsQuery, auth: AuthContext | None = None
    ) -> Result[list[Attachment], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            attachments = await self._repo.find_by_entity(
                input.workspace_id, input.attachable_type, input.attachable_id
            )
            return Success(attachments)
