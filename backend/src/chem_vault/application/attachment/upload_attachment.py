"""Upload a file attachment to an entity."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.attachment.attachment import Attachment
from chem_vault.domain.attachment.enums import AttachableType
from chem_vault.domain.attachment.repository import AttachmentRepository
from chem_vault.application.attachment.storage import StorageClient
from chem_vault.domain.shared.errors import DomainError, ValidationError
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol
from chem_vault.domain.attachment.validation import validate_extension, validate_file_size


@dataclass(frozen=True, kw_only=True)
class UploadAttachmentCommand(Command):
    workspace_id: uuid.UUID
    attachable_type: AttachableType
    attachable_id: uuid.UUID
    uploaded_by: uuid.UUID
    file_name: str
    mime_type: str
    file_data: bytes


class UploadAttachment:
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
        self, input: UploadAttachmentCommand, auth: AuthContext | None = None
    ) -> Result[Attachment, DomainError]:
        require_editor(auth)

        try:
            validate_extension(input.file_name)
            validate_file_size(len(input.file_data))
        except ValidationError as e:
            return Failure(e)

        attachment_id = uuid.uuid4()
        # Strip directory components to prevent path traversal (e.g. "../../etc/passwd")
        safe_name = PurePosixPath(input.file_name).name
        if not safe_name:
            return Failure(ValidationError("Invalid file name"))
        storage_key = (
            f"{input.workspace_id}/{input.attachable_type.value}"
            f"/{input.attachable_id}/{attachment_id}_{safe_name}"
        )

        attachment = Attachment.create(
            id=attachment_id,
            workspace_id=input.workspace_id,
            file_name=input.file_name,
            mime_type=input.mime_type,
            file_size=len(input.file_data),
            storage_key=storage_key,
            attachable_type=input.attachable_type,
            attachable_id=input.attachable_id,
            uploaded_by=input.uploaded_by,
        )

        try:
            await self._storage.upload(storage_key, input.file_data)
        except OSError:
            return Failure(ValidationError("Failed to upload file to storage"))

        async with self._uow:
            await self._repo.save(attachment)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)

        return Success(attachment)
