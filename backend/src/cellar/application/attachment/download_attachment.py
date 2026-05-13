"""Download an attachment's file data."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.attachment.storage import StorageClient
from cellar.application.auth import AuthContext, require_same_workspace
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.attachment.attachment import Attachment
from cellar.domain.attachment.repository import AttachmentRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class DownloadAttachmentQuery(Query):
    workspace_id: uuid.UUID
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
        self, input: DownloadAttachmentQuery, auth: AuthContext | None = None
    ) -> Result[tuple[Attachment, bytes], DomainError]:
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            attachment = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.attachment_id
            )
            if attachment is None:
                return Failure(NotFoundError("Attachment", str(input.attachment_id)))

        try:
            data = await self._storage.download(attachment.storage_key)
        except OSError:
            return Failure(NotFoundError("Attachment", str(input.attachment_id)))
        return Success((attachment, data))
