"""Workspace configuration enums."""

from enum import StrEnum

__all__ = ["FieldDataType", "FieldTarget", "OrganizationType"]


class OrganizationType(StrEnum):
    """Classification of organizations participating in compound lifecycle."""

    INTERNAL = "internal"
    PHARMA_PARTNER = "pharma_partner"
    CRO = "cro"
    ACADEMIC = "academic"
    VENDOR = "vendor"
    GOVERNMENT = "government"


class FieldDataType(StrEnum):
    """Supported data types for custom field definitions."""

    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    PICKLIST = "picklist"
    FILE = "file"
    BATCH_LINK = "batch_link"


class FieldTarget(StrEnum):
    """Entity types that a custom field definition can be attached to."""

    MOLECULE = "molecule"
    BATCH = "batch"
    SAMPLE = "sample"
