"""File attachment bindings."""

from __future__ import annotations

from lagom import Container
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.attachment.delete_attachment import DeleteAttachment
from cellar.application.attachment.download_attachment import DownloadAttachment
from cellar.application.attachment.list_attachments import ListAttachments
from cellar.application.attachment.upload_attachment import UploadAttachment
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.persistence.sqlalchemy.attachment.attachment_repository import (
    SQLAlchemyAttachmentRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.storage.fsspec_client import FsspecStorageClient


def register_attachment(container: Container) -> None:
    def _attach_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(
                uow,
                SQLAlchemyAttachmentRepository(uow),
                c[FsspecStorageClient],
                c[EventDispatcher],
            )

        return _f

    def _attach_query_with_storage(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyAttachmentRepository(uow), c[FsspecStorageClient])

        return _f

    def _attach_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyAttachmentRepository(uow))

        return _f

    container.define(UploadAttachment, _attach_cmd(UploadAttachment))
    container.define(DeleteAttachment, _attach_cmd(DeleteAttachment))
    container.define(ListAttachments, _attach_query(ListAttachments))
    container.define(DownloadAttachment, _attach_query_with_storage(DownloadAttachment))
