"""Unit tests for Attachment aggregate root."""

import uuid

import pytest

from cellar.domain.attachment.attachment import Attachment
from cellar.domain.attachment.enums import AttachableType
from cellar.domain.attachment.events import AttachmentDeleted, AttachmentUploaded
from cellar.domain.shared.errors import ValidationError


WS = uuid.uuid4()
MOL = uuid.uuid4()
USER = uuid.uuid4()


def _make(**overrides):
    defaults = dict(
        workspace_id=WS,
        file_name="spectrum.pdf",
        mime_type="application/pdf",
        file_size=1024,
        storage_key=f"{WS}/molecule/{MOL}/{uuid.uuid4()}_spectrum.pdf",
        attachable_type=AttachableType.MOLECULE,
        attachable_id=MOL,
        uploaded_by=USER,
    )
    defaults.update(overrides)
    return defaults


class TestCreate:
    def test_create_registers_event(self):
        att = Attachment.create(**_make())
        events = att.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], AttachmentUploaded)
        assert events[0].file_name == "spectrum.pdf"
        assert events[0].mime_type == "application/pdf"
        assert events[0].file_size == 1024

    def test_create_strips_file_name(self):
        att = Attachment.create(**_make(file_name="  report.pdf  "))
        assert att.file_name == "report.pdf"

    def test_create_empty_file_name_raises(self):
        with pytest.raises(ValidationError, match="file_name"):
            Attachment.create(**_make(file_name=""))

    def test_create_whitespace_file_name_raises(self):
        with pytest.raises(ValidationError, match="file_name"):
            Attachment.create(**_make(file_name="   "))

    def test_create_empty_mime_type_raises(self):
        with pytest.raises(ValidationError, match="mime_type"):
            Attachment.create(**_make(mime_type=""))

    def test_create_zero_file_size_raises(self):
        with pytest.raises(ValidationError, match="file_size"):
            Attachment.create(**_make(file_size=0))

    def test_create_negative_file_size_raises(self):
        with pytest.raises(ValidationError, match="file_size"):
            Attachment.create(**_make(file_size=-1))


class TestDelete:
    def test_delete_registers_event(self):
        att = Attachment.create(**_make())
        att.clear_events()
        att.delete()
        events = att.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], AttachmentDeleted)
        assert events[0].file_name == "spectrum.pdf"


class TestRepoint:
    def test_repoint_updates_attachable_id(self):
        att = Attachment.create(**_make())
        new_target = uuid.uuid4()
        att.repoint(new_target)
        assert att.attachable_id == new_target
