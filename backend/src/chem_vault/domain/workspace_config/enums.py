"""Workspace configuration enums."""

from enum import StrEnum


class OrganizationType(StrEnum):
    """Classification of organizations participating in compound lifecycle."""

    INTERNAL = "internal"
    PHARMA_PARTNER = "pharma_partner"
    CRO = "cro"
    ACADEMIC = "academic"
    VENDOR = "vendor"
    GOVERNMENT = "government"
