"""Attachment dependency aliases."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.attachment.delete_attachment import DeleteAttachment
from cellar.application.attachment.download_attachment import DownloadAttachment
from cellar.application.attachment.list_attachments import ListAttachments
from cellar.application.attachment.upload_attachment import UploadAttachment

from ._core import _get_use_case

__all__ = [
    "DeleteAttachmentDep",
    "DownloadAttachmentDep",
    "ListAttachmentsDep",
    "UploadAttachmentDep",
]

UploadAttachmentDep = Annotated[UploadAttachment, Depends(_get_use_case(UploadAttachment))]
DeleteAttachmentDep = Annotated[DeleteAttachment, Depends(_get_use_case(DeleteAttachment))]
ListAttachmentsDep = Annotated[ListAttachments, Depends(_get_use_case(ListAttachments))]
DownloadAttachmentDep = Annotated[DownloadAttachment, Depends(_get_use_case(DownloadAttachment))]
