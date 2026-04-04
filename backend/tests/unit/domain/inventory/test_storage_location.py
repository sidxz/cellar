"""Tests for StorageLocation entity — hierarchy, type validation."""

import uuid

import pytest

from chem_vault.domain.inventory.enums import StorageLocationType
from chem_vault.domain.inventory.storage_location import StorageLocation
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.shared.value_objects import Barcode


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


class TestStorageLocationCreation:
    def test_create_top_level_site(self, workspace_id: uuid.UUID) -> None:
        loc = StorageLocation.create(
            workspace_id=workspace_id,
            name="Main Campus",
            type=StorageLocationType.SITE,
        )
        assert loc.name == "Main Campus"
        assert loc.type == StorageLocationType.SITE
        assert loc.parent_id is None

    def test_create_with_barcode(self, workspace_id: uuid.UUID) -> None:
        loc = StorageLocation.create(
            workspace_id=workspace_id,
            name="Freezer A",
            type=StorageLocationType.FREEZER,
            parent_id=uuid.uuid4(),
            parent_type=StorageLocationType.ROOM,
            barcode=Barcode(value="FRZ-001"),
        )
        assert loc.barcode is not None
        assert loc.barcode.value == "FRZ-001"

    def test_create_with_grid_dimensions(self, workspace_id: uuid.UUID) -> None:
        loc = StorageLocation.create(
            workspace_id=workspace_id,
            name="Box 14",
            type=StorageLocationType.BOX,
            parent_id=uuid.uuid4(),
            parent_type=StorageLocationType.SHELF,
            rows=8,
            columns=12,
            capacity=96,
        )
        assert loc.rows == 8
        assert loc.columns == 12
        assert loc.capacity == 96

    def test_name_is_stripped(self, workspace_id: uuid.UUID) -> None:
        loc = StorageLocation.create(
            workspace_id=workspace_id,
            name="  Main Campus  ",
            type=StorageLocationType.SITE,
        )
        assert loc.name == "Main Campus"

    def test_empty_name_raises(self, workspace_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            StorageLocation.create(
                workspace_id=workspace_id,
                name="",
                type=StorageLocationType.SITE,
            )

    def test_whitespace_name_raises(self, workspace_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            StorageLocation.create(
                workspace_id=workspace_id,
                name="   ",
                type=StorageLocationType.SITE,
            )

    def test_zero_capacity_raises(self, workspace_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="Capacity must be > 0"):
            StorageLocation.create(
                workspace_id=workspace_id,
                name="Box",
                type=StorageLocationType.BOX,
                parent_id=uuid.uuid4(),
                parent_type=StorageLocationType.SHELF,
                capacity=0,
            )

    def test_negative_rows_raises(self, workspace_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="Rows must be > 0"):
            StorageLocation.create(
                workspace_id=workspace_id,
                name="Box",
                type=StorageLocationType.BOX,
                parent_id=uuid.uuid4(),
                parent_type=StorageLocationType.SHELF,
                rows=-1,
            )


class TestStorageLocationHierarchy:
    def test_site_requires_no_parent(self, workspace_id: uuid.UUID) -> None:
        loc = StorageLocation.create(
            workspace_id=workspace_id,
            name="Site",
            type=StorageLocationType.SITE,
        )
        assert loc.parent_id is None

    def test_building_requires_site_parent(self, workspace_id: uuid.UUID) -> None:
        loc = StorageLocation.create(
            workspace_id=workspace_id,
            name="Building A",
            type=StorageLocationType.BUILDING,
            parent_id=uuid.uuid4(),
            parent_type=StorageLocationType.SITE,
        )
        assert loc.parent_id is not None

    def test_room_requires_building_parent(self, workspace_id: uuid.UUID) -> None:
        loc = StorageLocation.create(
            workspace_id=workspace_id,
            name="Room 101",
            type=StorageLocationType.ROOM,
            parent_id=uuid.uuid4(),
            parent_type=StorageLocationType.BUILDING,
        )
        assert loc.type == StorageLocationType.ROOM

    def test_freezer_requires_room_parent(self, workspace_id: uuid.UUID) -> None:
        loc = StorageLocation.create(
            workspace_id=workspace_id,
            name="Freezer -80",
            type=StorageLocationType.FREEZER,
            parent_id=uuid.uuid4(),
            parent_type=StorageLocationType.ROOM,
        )
        assert loc.type == StorageLocationType.FREEZER

    def test_shelf_can_have_freezer_parent(self, workspace_id: uuid.UUID) -> None:
        loc = StorageLocation.create(
            workspace_id=workspace_id,
            name="Shelf 1",
            type=StorageLocationType.SHELF,
            parent_id=uuid.uuid4(),
            parent_type=StorageLocationType.FREEZER,
        )
        assert loc.type == StorageLocationType.SHELF

    def test_shelf_can_have_refrigerator_parent(self, workspace_id: uuid.UUID) -> None:
        StorageLocation.create(
            workspace_id=workspace_id,
            name="Shelf 1",
            type=StorageLocationType.SHELF,
            parent_id=uuid.uuid4(),
            parent_type=StorageLocationType.REFRIGERATOR,
        )

    def test_building_without_parent_raises(self, workspace_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="requires a parent"):
            StorageLocation.create(
                workspace_id=workspace_id,
                name="Building",
                type=StorageLocationType.BUILDING,
            )

    def test_freezer_with_building_parent_raises(self, workspace_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="cannot have parent"):
            StorageLocation.create(
                workspace_id=workspace_id,
                name="Freezer",
                type=StorageLocationType.FREEZER,
                parent_id=uuid.uuid4(),
                parent_type=StorageLocationType.BUILDING,
            )

    def test_shelf_with_room_parent_raises(self, workspace_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="cannot have parent"):
            StorageLocation.create(
                workspace_id=workspace_id,
                name="Shelf",
                type=StorageLocationType.SHELF,
                parent_id=uuid.uuid4(),
                parent_type=StorageLocationType.ROOM,
            )

    def test_box_can_have_shelf_parent(self, workspace_id: uuid.UUID) -> None:
        StorageLocation.create(
            workspace_id=workspace_id,
            name="Box 1",
            type=StorageLocationType.BOX,
            parent_id=uuid.uuid4(),
            parent_type=StorageLocationType.SHELF,
        )

    def test_box_can_have_rack_parent(self, workspace_id: uuid.UUID) -> None:
        StorageLocation.create(
            workspace_id=workspace_id,
            name="Box 1",
            type=StorageLocationType.BOX,
            parent_id=uuid.uuid4(),
            parent_type=StorageLocationType.RACK,
        )

    def test_box_can_have_drawer_parent(self, workspace_id: uuid.UUID) -> None:
        StorageLocation.create(
            workspace_id=workspace_id,
            name="Box 1",
            type=StorageLocationType.BOX,
            parent_id=uuid.uuid4(),
            parent_type=StorageLocationType.DRAWER,
        )

    def test_site_with_parent_raises(self, workspace_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="cannot have parent"):
            StorageLocation.create(
                workspace_id=workspace_id,
                name="Site",
                type=StorageLocationType.SITE,
                parent_id=uuid.uuid4(),
                parent_type=StorageLocationType.BUILDING,
            )
