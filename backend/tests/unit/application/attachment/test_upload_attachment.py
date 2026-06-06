"""Unit tests for UploadAttachment use case."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Failure, Success

from cellar.application.attachment.upload_attachment import (
    UploadAttachment,
    UploadAttachmentCommand,
)
from cellar.domain.attachment.enums import AttachableType
from cellar.domain.shared.errors import ValidationError

WS = uuid.uuid4()
MOL = uuid.uuid4()
USER = uuid.uuid4()


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


def _cmd(**overrides):
    defaults = dict(
        workspace_id=WS,
        attachable_type=AttachableType.MOLECULE,
        attachable_id=MOL,
        uploaded_by=USER,
        file_name="spectrum.pdf",
        mime_type="application/pdf",
        file_data=b"fake pdf content",
    )
    defaults.update(overrides)
    return UploadAttachmentCommand(**defaults)


def _auth():
    """Auth context scoped to the same workspace the command targets."""
    a = MagicMock()
    a.workspace_id = WS
    return a


class TestUploadAttachment:
    async def test_success(self, deps):
        uow, repo, storage, dispatcher = deps
        uc = UploadAttachment(uow, repo, storage, dispatcher)
        result = await uc(_cmd(), auth=_auth())
        assert isinstance(result, Success)
        att = result.unwrap()
        assert att.file_name == "spectrum.pdf"
        storage.upload.assert_called_once()
        repo.save.assert_called_once()

    async def test_blocked_extension(self, deps):
        uow, repo, storage, dispatcher = deps
        uc = UploadAttachment(uow, repo, storage, dispatcher)
        result = await uc(_cmd(file_name="malware.exe"), auth=_auth())
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    async def test_oversized_file(self, deps):
        uow, repo, storage, dispatcher = deps
        uc = UploadAttachment(uow, repo, storage, dispatcher)
        big_data = b"x" * (104_857_601)
        result = await uc(_cmd(file_data=big_data), auth=_auth())
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)
