"""Inventory context enums."""

from enum import StrEnum


class BatchSource(StrEnum):
    """How a batch was obtained."""

    SYNTHESIZED = "synthesized"
    PURCHASED = "purchased"
    DONATED = "donated"
    NATURAL_EXTRACT = "natural_extract"


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
    StorageLocationType.BOX: {StorageLocationType.SHELF, StorageLocationType.RACK, StorageLocationType.DRAWER},
    StorageLocationType.DRAWER: {StorageLocationType.SHELF, StorageLocationType.RACK},
}
