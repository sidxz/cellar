"""Delete a file attachment."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.attachment.repository import AttachmentRepository
from chem_vault.domain.attachment.storage import StorageClient
from chem_vault.domain.shared.errors import DomainError, NotFoundError
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class DeleteAttachmentCommand(Command):
    attachment_id: uuid.UUID


class DeleteAttachment:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: AttachmentRepository,
        storage: StorageClient,
        dispatcher: EventDispatcher,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._storage = storage
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeleteAttachmentCommand, auth: object | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)

        async with self._uow:
            attachment = await self._repo.find_by_id(input.attachment_id)
            if attachment is None:
                return Failure(
                    NotFoundError("Attachment", str(input.attachment_id))
                )

            try:
                await self._storage.delete(attachment.storage_key)
            except Exception:
                logger.warning(
                    "Failed to delete blob %s", attachment.storage_key, exc_info=True
                )

            attachment.delete()
            await self._repo.delete(attachment)
            events = await self._uow.commit()
            await self._dispatcher.dispatch_all(events)

        return Success(None)
