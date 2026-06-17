"""Delete a file attachment."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from returns.result import Failure, Result, Success

from cellar.application.attachment.storage import StorageClient
from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.attachment.repository import AttachmentRepository
from cellar.domain.shared.errors import DomainError, NotFoundError

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class DeleteAttachmentCommand(Command):
    workspace_id: uuid.UUID
    attachment_id: uuid.UUID


class DeleteAttachment:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: AttachmentRepository,
        storage: StorageClient,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._storage = storage
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeleteAttachmentCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            attachment = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.attachment_id
            )
            if attachment is None:
                return Failure(NotFoundError("Attachment", str(input.attachment_id)))

            try:
                await self._storage.delete(attachment.storage_key)
            except OSError:
                logger.warning(
                    "attachment.blob_delete_failed",
                    storage_key=attachment.storage_key,
                    exc_info=True,
                )

            attachment.delete()
            await self._repo.delete(attachment)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)

        return Success(None)
