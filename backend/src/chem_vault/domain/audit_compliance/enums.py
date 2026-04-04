"""Audit & compliance enums."""

from enum import StrEnum


class OperationType(StrEnum):
    """Types of auditable operations across all bounded contexts."""

    REGISTRATION = "registration"
    DISCLOSURE = "disclosure"
    MERGE = "merge"
    STRUCTURE_CORRECTION = "structure_correction"
    DATA_ENTRY = "data_entry"
    APPROVAL = "approval"
    REJECTION = "rejection"
    PROPERTY_EDIT = "property_edit"
    BULK_IMPORT = "bulk_import"
    BULK_DISCLOSURE = "bulk_disclosure"
    ACCESS_CHANGE = "access_change"
    DATA_LOCK = "data_lock"
    DATA_UNLOCK = "data_unlock"
    LIFECYCLE_CHANGE = "lifecycle_change"
    ROUTE_CREATION = "route_creation"
    ROUTE_UPDATE = "route_update"
    SYNTHESIS_REQUEST = "synthesis_request"
    SYNTHESIS_ASSIGNMENT = "synthesis_assignment"
    SYNTHESIS_FULFILLMENT = "synthesis_fulfillment"
    FORMULATION_CREATION = "formulation_creation"
    FORMULATION_BATCH_RELEASE = "formulation_batch_release"
    STABILITY_RECORDING = "stability_recording"
    MARKUSH_DEFINITION = "markush_definition"


class ActorType(StrEnum):
    """Who initiated the auditable operation."""

    USER = "user"
    SYSTEM = "system"
    INTEGRATION = "integration"


class AuditStatus(StrEnum):
    """Outcome of the auditable operation."""

    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class AuditAction(StrEnum):
    """Field-level change type within an AuditEntry."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class AuthMethod(StrEnum):
    """Authentication method for electronic signatures (21 CFR Part 11)."""

    PASSWORD = "password"
    MFA = "mfa"
    BIOMETRIC = "biometric"
