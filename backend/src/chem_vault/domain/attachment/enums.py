"""Attachment-specific enums."""

from enum import StrEnum


class AttachableType(StrEnum):
    """Entity types that can have file attachments."""

    MOLECULE = "molecule"
    BATCH = "batch"
    PROTOCOL = "protocol"
    RUN = "run"
    ELN_ENTRY = "eln_entry"
