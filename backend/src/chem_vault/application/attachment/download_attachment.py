"""Download an attachment's file data."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.shared.query import Query
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.attachment.attachment import Attachment
from chem_vault.domain.attachment.repository import AttachmentRepository
from chem_vault.domain.attachment.storage import StorageClient
from chem_vault.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class DownloadAttachmentQuery(Query):
    attachment_id: uuid.UUID


class DownloadAttachment:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: AttachmentRepository,
        storage: StorageClient,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._storage = storage

    async def __call__(
        self, input: DownloadAttachmentQuery, auth: object | None = None
    ) -> Result[tuple[Attachment, bytes], DomainError]:
        async with self._uow:
            attachment = await self._repo.find_by_id(input.attachment_id)
            if attachment is None:
                return Failure(
                    NotFoundError("Attachment", str(input.attachment_id))
                )

        data = await self._storage.download(attachment.storage_key)
        return Success((attachment, data))
