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
