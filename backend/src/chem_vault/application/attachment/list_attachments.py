"""List attachments for an entity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.attachment.attachment import Attachment
from chem_vault.domain.attachment.enums import AttachableType
from chem_vault.domain.attachment.repository import AttachmentRepository
from chem_vault.domain.shared.errors import DomainError


@dataclass(frozen=True, kw_only=True)
class ListAttachmentsQuery(Query):
    attachable_type: AttachableType
    attachable_id: uuid.UUID


class ListAttachments:
    def __init__(self, uow: UnitOfWork, repo: AttachmentRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListAttachmentsQuery, auth: object | None = None
    ) -> Result[list[Attachment], DomainError]:
        async with self._uow:
            attachments = await self._repo.find_by_entity(
                input.attachable_type, input.attachable_id
            )
        return Success(attachments)
