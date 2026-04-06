"""Attachment API — upload, list, download, delete file attachments."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from chem_vault.application.attachment.delete_attachment import DeleteAttachmentCommand
from chem_vault.application.attachment.download_attachment import DownloadAttachmentQuery
from chem_vault.application.attachment.list_attachments import ListAttachmentsQuery
from chem_vault.application.attachment.upload_attachment import UploadAttachmentCommand
from chem_vault.domain.attachment.attachment import Attachment
from chem_vault.domain.attachment.enums import AttachableType
from chem_vault.interface.dependencies import (
    AuthDep,
    DeleteAttachmentDep,
    DownloadAttachmentDep,
    ListAttachmentsDep,
    UploadAttachmentDep,
)
from chem_vault.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1", tags=["attachments"])


class AttachmentResponse(BaseModel):
    id: uuid.UUID
    file_name: str
    mime_type: str
    file_size: int
    attachable_type: str
    attachable_id: uuid.UUID
    uploaded_by: uuid.UUID
    created_at: str

    @classmethod
    def from_domain(cls, att: Attachment) -> AttachmentResponse:
        return cls(
            id=att.id,
            file_name=att.file_name,
            mime_type=att.mime_type,
            file_size=att.file_size,
            attachable_type=att.attachable_type.value,
            attachable_id=att.attachable_id,
            uploaded_by=att.uploaded_by,
            created_at=att.created_at.isoformat(),
        )


@router.post(
    "/{entity_type}/{entity_id}/attachments",
    response_model=AttachmentResponse,
    status_code=201,
)
async def upload_attachment(
    entity_type: AttachableType,
    entity_id: uuid.UUID,
    file: UploadFile = File(...),
    *,
    auth: AuthDep,
    use_case: UploadAttachmentDep,
) -> AttachmentResponse:
    file_data = await file.read()
    command = UploadAttachmentCommand(
        workspace_id=auth.workspace_id,
        attachable_type=entity_type,
        attachable_id=entity_id,
        uploaded_by=auth.user_id,
        file_name=file.filename or "unnamed",
        mime_type=file.content_type or "application/octet-stream",
        file_data=file_data,
    )
    attachment = result_to_response(await use_case(command, auth=auth))
    return AttachmentResponse.from_domain(attachment)


@router.get(
    "/{entity_type}/{entity_id}/attachments",
    response_model=list[AttachmentResponse],
)
async def list_attachments(
    entity_type: AttachableType,
    entity_id: uuid.UUID,
    auth: AuthDep,
    use_case: ListAttachmentsDep,
) -> list[AttachmentResponse]:
    query = ListAttachmentsQuery(
        attachable_type=entity_type,
        attachable_id=entity_id,
    )
    attachments = result_to_response(await use_case(query, auth=auth))
    return [AttachmentResponse.from_domain(a) for a in attachments]


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: uuid.UUID,
    auth: AuthDep,
    use_case: DownloadAttachmentDep,
) -> Response:
    query = DownloadAttachmentQuery(attachment_id=attachment_id)
    attachment, data = result_to_response(await use_case(query, auth=auth))
    return Response(
        content=data,
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{attachment.file_name}"',
        },
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: uuid.UUID,
    auth: AuthDep,
    use_case: DeleteAttachmentDep,
) -> None:
    command = DeleteAttachmentCommand(attachment_id=attachment_id)
    result_to_response(await use_case(command, auth=auth))
