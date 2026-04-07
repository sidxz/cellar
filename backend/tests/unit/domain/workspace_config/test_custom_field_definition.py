"""Unit tests for CustomFieldDefinition aggregate."""

import uuid

import pytest

from chem_vault.domain.workspace_config.custom_field_definition import (
    CustomFieldDefinition,
)
from chem_vault.domain.workspace_config.enums import FieldDataType, FieldTarget


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


class TestCustomFieldDefinitionCreate:
    def test_factory(self, ws_id: uuid.UUID) -> None:
        cfd = CustomFieldDefinition.create(
            workspace_id=ws_id,
            name="tumor_model",
            label="Tumor Model",
            data_type=FieldDataType.PICKLIST,
            applies_to=FieldTarget.MOLECULE,
            pick_list_values=["Xenograft", "PDX", "Organoid"],
        )
        assert cfd.workspace_id == ws_id
        assert cfd.name == "tumor_model"
        assert cfd.label == "Tumor Model"
        assert cfd.data_type == FieldDataType.PICKLIST
        assert cfd.applies_to == FieldTarget.MOLECULE
        assert cfd.pick_list_values == ["Xenograft", "PDX", "Organoid"]
        assert cfd.vocabulary_id is None
        assert cfd.is_required is False
        assert cfd.default_value is None
        assert cfd.is_active is True
        assert cfd.display_order == 0

    def test_factory_emits_event(self, ws_id: uuid.UUID) -> None:
        cfd = CustomFieldDefinition.create(
            workspace_id=ws_id,
            name="project_code",
            label="Project Code",
            data_type=FieldDataType.TEXT,
            applies_to=FieldTarget.MOLECULE,
        )
        events = cfd.collect_events()
        assert len(events) == 1
        assert events[0].aggregate_type == "CustomFieldDefinition"

    def test_empty_name_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValueError, match="name"):
            CustomFieldDefinition.create(
                workspace_id=ws_id,
                name="",
                label="Empty",
                data_type=FieldDataType.TEXT,
                applies_to=FieldTarget.MOLECULE,
            )

    def test_empty_label_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValueError, match="label"):
            CustomFieldDefinition.create(
                workspace_id=ws_id,
                name="x",
                label="",
                data_type=FieldDataType.TEXT,
                applies_to=FieldTarget.MOLECULE,
            )

    def test_picklist_with_vocabulary_id_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            CustomFieldDefinition.create(
                workspace_id=ws_id,
                name="x",
                label="X",
                data_type=FieldDataType.PICKLIST,
                applies_to=FieldTarget.MOLECULE,
                pick_list_values=["A"],
                vocabulary_id=uuid.uuid4(),
            )

    def test_non_picklist_with_values_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValueError, match="only for picklist"):
            CustomFieldDefinition.create(
                workspace_id=ws_id,
                name="x",
                label="X",
                data_type=FieldDataType.TEXT,
                applies_to=FieldTarget.MOLECULE,
                pick_list_values=["A"],
            )

    def test_with_required_and_default(self, ws_id: uuid.UUID) -> None:
        cfd = CustomFieldDefinition.create(
            workspace_id=ws_id,
            name="priority",
            label="Priority",
            data_type=FieldDataType.NUMBER,
            applies_to=FieldTarget.BATCH,
            is_required=True,
            default_value=1,
            display_order=5,
        )
        assert cfd.is_required is True
        assert cfd.default_value == 1
        assert cfd.display_order == 5


class TestCustomFieldDefinitionUpdate:
    def _make(self, ws_id: uuid.UUID) -> CustomFieldDefinition:
        cfd = CustomFieldDefinition.create(
            workspace_id=ws_id,
            name="tumor_model",
            label="Tumor Model",
            data_type=FieldDataType.PICKLIST,
            applies_to=FieldTarget.MOLECULE,
            pick_list_values=["Xenograft", "PDX"],
        )
        cfd.clear_events()
        return cfd

    def test_update_label(self, ws_id: uuid.UUID) -> None:
        cfd = self._make(ws_id)
        cfd.update(label="Tumor Model v2")
        assert cfd.label == "Tumor Model v2"
        assert len(cfd.collect_events()) == 1

    def test_update_pick_list_values(self, ws_id: uuid.UUID) -> None:
        cfd = self._make(ws_id)
        cfd.update(pick_list_values=["Xenograft", "PDX", "Organoid"])
        assert cfd.pick_list_values == ["Xenograft", "PDX", "Organoid"]

    def test_deactivate(self, ws_id: uuid.UUID) -> None:
        cfd = self._make(ws_id)
        cfd.deactivate()
        assert cfd.is_active is False
        assert len(cfd.collect_events()) == 1

    def test_reactivate(self, ws_id: uuid.UUID) -> None:
        cfd = self._make(ws_id)
        cfd.deactivate()
        cfd.clear_events()
        cfd.activate()
        assert cfd.is_active is True
