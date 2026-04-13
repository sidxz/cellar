"""Unit tests for DeleteAttachment use case."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.attachment.delete_attachment import (
    DeleteAttachment,
    DeleteAttachmentCommand,
)
from chem_vault.domain.attachment.attachment import Attachment
from chem_vault.domain.attachment.enums import AttachableType
from chem_vault.domain.shared.errors import NotFoundError


WS = uuid.uuid4()
MOL = uuid.uuid4()
USER = uuid.uuid4()


def _make_attachment():
    return Attachment(
        workspace_id=WS,
        file_name="report.pdf",
        mime_type="application/pdf",
        file_size=512,
        storage_key=f"{WS}/molecule/{MOL}/abc_report.pdf",
        attachable_type=AttachableType.MOLECULE,
        attachable_id=MOL,
        uploaded_by=USER,
    )


@pytest.fixture
def deps():
    uow = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.commit = AsyncMock(return_value=[])
    repo = AsyncMock()
    storage = AsyncMock()
    dispatcher = AsyncMock()
    return uow, repo, storage, dispatcher


class TestDeleteAttachment:
    async def test_success(self, deps):
        uow, repo, storage, dispatcher = deps
        att = _make_attachment()
        repo.find_by_id_in_workspace = AsyncMock(return_value=att)
        uc = DeleteAttachment(uow, repo, storage, dispatcher)
        auth = MagicMock()
        auth.workspace_id = WS
        result = await uc(DeleteAttachmentCommand(workspace_id=WS, attachment_id=att.id), auth=auth)
        assert isinstance(result, Success)
        storage.delete.assert_called_once_with(att.storage_key)
        repo.delete.assert_called_once()

    async def test_not_found(self, deps):
        uow, repo, storage, dispatcher = deps
        repo.find_by_id_in_workspace = AsyncMock(return_value=None)
        uc = DeleteAttachment(uow, repo, storage, dispatcher)
        auth = MagicMock()
        auth.workspace_id = WS
        result = await uc(
            DeleteAttachmentCommand(workspace_id=WS, attachment_id=uuid.uuid4()), auth=auth
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
