"""Inventory context enums."""

from enum import StrEnum


class BatchSource(StrEnum):
    """How a batch was obtained."""

    SYNTHESIZED = "synthesized"
    PURCHASED = "purchased"
    DONATED = "donated"
    NATURAL_EXTRACT = "natural_extract"
    EXTERNAL_REFERENCE = "external_reference"


class ContainerType(StrEnum):
    """Physical container type for a sample."""

    VIAL = "vial"
    TUBE = "tube"
    PLATE_WELL = "plate_well"
    AMPULE = "ampule"
    BAG = "bag"


class SampleStatus(StrEnum):
    """Current lifecycle status of a sample."""

    AVAILABLE = "available"
    DEPLETED = "depleted"
    EXPIRED = "expired"
    QUARANTINED = "quarantined"
    DISPOSED = "disposed"


class StorageLocationType(StrEnum):
    """Physical storage hierarchy level."""

    SITE = "site"
    BUILDING = "building"
    ROOM = "room"
    FREEZER = "freezer"
    REFRIGERATOR = "refrigerator"
    SHELF = "shelf"
    RACK = "rack"
    BOX = "box"
    DRAWER = "drawer"


class RequestPriority(StrEnum):
    """Priority level for sample/synthesis requests."""

    ROUTINE = "routine"
    URGENT = "urgent"
    CRITICAL = "critical"


class SampleRequestStatus(StrEnum):
    """Lifecycle status of a sample request."""

    SUBMITTED = "submitted"
    APPROVED = "approved"
    PREPARING = "preparing"
    FULFILLED = "fulfilled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ShipmentStatus(StrEnum):
    """Lifecycle status of a shipment."""

    PREPARING = "preparing"
    SHIPPED = "shipped"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    RETURNED = "returned"


class SynthesisRequestStatus(StrEnum):
    """10-state lifecycle of a synthesis request."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SYNTHESIS_COMPLETE = "synthesis_complete"
    FULFILLED = "fulfilled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    FAILED = "failed"


class FeasibilityStatus(StrEnum):
    """Chemist's feasibility assessment."""

    FEASIBLE = "feasible"
    CHALLENGING = "challenging"
    INFEASIBLE = "infeasible"
    ALTERNATIVE_PROPOSED = "alternative_proposed"


# Valid parent types for each location type
VALID_PARENT_TYPES: dict[StorageLocationType, set[StorageLocationType | None]] = {
    StorageLocationType.SITE: {None},
    StorageLocationType.BUILDING: {StorageLocationType.SITE},
    StorageLocationType.ROOM: {StorageLocationType.BUILDING},
    StorageLocationType.FREEZER: {StorageLocationType.ROOM},
    StorageLocationType.REFRIGERATOR: {StorageLocationType.ROOM},
    StorageLocationType.SHELF: {StorageLocationType.FREEZER, StorageLocationType.REFRIGERATOR},
    StorageLocationType.RACK: {StorageLocationType.SHELF},
    StorageLocationType.BOX: {
        StorageLocationType.SHELF,
        StorageLocationType.RACK,
        StorageLocationType.DRAWER,
    },
    StorageLocationType.DRAWER: {StorageLocationType.SHELF, StorageLocationType.RACK},
}


class CddPlateImportStatus(StrEnum):
    """Status of a CDD vault plate import operation."""

    PENDING = "pending"
    DISCOVERING = "discovering"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class PlateType(StrEnum):
    """Type/role of a registered plate."""

    COMPOUND_STORAGE = "compound_storage"
    MOTHER = "mother"
    DAUGHTER = "daughter"
    ARCHIVE = "archive"
    ASSAY = "assay"
    DOSE_RESPONSE = "dose_response"
    REPLICATE = "replicate"
    CONTROL = "control"
    CHERRY_PICK = "cherry_pick"
    DILUTION = "dilution"
    REFORMATTED = "reformatted"
    POOLED = "pooled"


class PlateStatus(StrEnum):
    """Lifecycle status of a registered plate."""

    REGISTERED = "registered"
    IN_USE = "in_use"
    STORED = "stored"
    DEPLETED = "depleted"
    DISPOSED = "disposed"


# Valid plate status transitions
VALID_PLATE_TRANSITIONS: dict[PlateStatus, set[PlateStatus]] = {
    PlateStatus.REGISTERED: {PlateStatus.IN_USE, PlateStatus.STORED, PlateStatus.DISPOSED},
    PlateStatus.IN_USE: {PlateStatus.STORED, PlateStatus.DEPLETED},
    PlateStatus.STORED: {PlateStatus.IN_USE, PlateStatus.DEPLETED, PlateStatus.DISPOSED},
    PlateStatus.DEPLETED: {PlateStatus.DISPOSED},
    PlateStatus.DISPOSED: set(),
}


class LoanConfirmationMode(StrEnum):
    """How a plate loan handoff is confirmed, per org policy."""

    KIOSK_SCAN = "kiosk_scan"
    ADMIN_CONFIRM = "admin_confirm"
    NONE = "none"


class LoanStatus(StrEnum):
    """Lifecycle status of a plate loan."""

    OPEN = "open"
    CLOSED = "closed"


class LoanItemStatus(StrEnum):
    """Status of a plate within a loan."""

    REQUESTED = "requested"
    APPROVED = "approved"
    CHECKED_OUT = "checked_out"
    RETURN_PENDING = "return_pending"
    RETURNED = "returned"
    DENIED = "denied"
    CANCELLED = "cancelled"


ACTIVE_LOAN_ITEM_STATUSES: frozenset[LoanItemStatus] = frozenset(
    {
        LoanItemStatus.REQUESTED,
        LoanItemStatus.APPROVED,
        LoanItemStatus.CHECKED_OUT,
        LoanItemStatus.RETURN_PENDING,
    }
)

# target -> allowed sources (approve-all/deny-all etc. filter by these)
VALID_LOAN_ITEM_TRANSITIONS: dict[LoanItemStatus, frozenset[LoanItemStatus]] = {
    LoanItemStatus.APPROVED: frozenset({LoanItemStatus.REQUESTED}),
    LoanItemStatus.DENIED: frozenset({LoanItemStatus.REQUESTED}),
    LoanItemStatus.CHECKED_OUT: frozenset({LoanItemStatus.APPROVED}),
    LoanItemStatus.RETURN_PENDING: frozenset({LoanItemStatus.CHECKED_OUT}),
    LoanItemStatus.RETURNED: frozenset({LoanItemStatus.RETURN_PENDING}),
    LoanItemStatus.CANCELLED: frozenset(
        {LoanItemStatus.REQUESTED, LoanItemStatus.APPROVED}
    ),
}


class CommentTarget(StrEnum):
    """What a plate-tracking comment is attached to (spec 2026-08-25 §7)."""

    PLATE_LOAN = "plate_loan"
    PLATE_GROUP = "plate_group"
    PLATE = "plate"
