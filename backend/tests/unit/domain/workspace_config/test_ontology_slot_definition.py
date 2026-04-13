"""Tests for OntologySlotDefinition aggregate root."""

from __future__ import annotations

import uuid

import pytest

from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.workspace_config.events import (
    OntologySlotDefinitionCreated,
    OntologySlotDefinitionUpdated,
)
from chem_vault.domain.workspace_config.ontology_slot_definition import (
    OntologySlotDefinition,
)


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


class TestOntologySlotDefinitionCreate:
    def test_create_valid(self, workspace_id: uuid.UUID):
        slot = OntologySlotDefinition.create(
            workspace_id=workspace_id,
            name="bioassay_type",
            label="Bioassay Type",
            ontology_sources=["BAO"],
        )
        assert slot.workspace_id == workspace_id
        assert slot.name == "bioassay_type"
        assert slot.label == "Bioassay Type"
        assert slot.ontology_sources == ["BAO"]
        assert slot.is_required is False
        assert slot.allow_free_text is True
        assert slot.display_order == 0
        assert slot.version == 1

    def test_create_with_all_options(self, workspace_id: uuid.UUID):
        slot = OntologySlotDefinition.create(
            workspace_id=workspace_id,
            name="cell_line",
            label="Cell Line",
            ontology_sources=["CLO", "EFO"],
            is_required=True,
            allow_free_text=False,
            display_order=5,
        )
        assert slot.is_required is True
        assert slot.allow_free_text is False
        assert slot.display_order == 5
        assert slot.ontology_sources == ["CLO", "EFO"]

    def test_create_strips_whitespace(self, workspace_id: uuid.UUID):
        slot = OntologySlotDefinition.create(
            workspace_id=workspace_id,
            name="  bioassay_type  ",
            label="  Bioassay Type  ",
            ontology_sources=["BAO"],
        )
        assert slot.name == "bioassay_type"
        assert slot.label == "Bioassay Type"

    def test_create_registers_event(self, workspace_id: uuid.UUID):
        slot = OntologySlotDefinition.create(
            workspace_id=workspace_id,
            name="bioassay_type",
            label="Bioassay Type",
            ontology_sources=["BAO"],
        )
        events = slot.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], OntologySlotDefinitionCreated)
        assert events[0].workspace_id == workspace_id
        assert events[0].name == "bioassay_type"

    def test_create_empty_name_raises(self, workspace_id: uuid.UUID):
        with pytest.raises(ValidationError, match="name must not be empty"):
            OntologySlotDefinition.create(
                workspace_id=workspace_id,
                name="",
                label="Test",
                ontology_sources=["BAO"],
            )

    def test_create_whitespace_name_raises(self, workspace_id: uuid.UUID):
        with pytest.raises(ValidationError, match="name must not be empty"):
            OntologySlotDefinition.create(
                workspace_id=workspace_id,
                name="   ",
                label="Test",
                ontology_sources=["BAO"],
            )

    def test_create_empty_label_raises(self, workspace_id: uuid.UUID):
        with pytest.raises(ValidationError, match="label must not be empty"):
            OntologySlotDefinition.create(
                workspace_id=workspace_id,
                name="test",
                label="",
                ontology_sources=["BAO"],
            )

    def test_create_empty_ontology_sources_raises(self, workspace_id: uuid.UUID):
        with pytest.raises(ValidationError, match="ontology_sources must have at least one"):
            OntologySlotDefinition.create(
                workspace_id=workspace_id,
                name="test",
                label="Test",
                ontology_sources=[],
            )


class TestOntologySlotDefinitionUpdate:
    def test_update_label(self, workspace_id: uuid.UUID):
        slot = OntologySlotDefinition.create(
            workspace_id=workspace_id,
            name="bioassay_type",
            label="Bioassay Type",
            ontology_sources=["BAO"],
        )
        slot.clear_events()
        slot.update(label="Assay Classification")
        assert slot.label == "Assay Classification"
        events = slot.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], OntologySlotDefinitionUpdated)

    def test_update_ontology_sources(self, workspace_id: uuid.UUID):
        slot = OntologySlotDefinition.create(
            workspace_id=workspace_id,
            name="bioassay_type",
            label="Bioassay Type",
            ontology_sources=["BAO"],
        )
        slot.clear_events()
        slot.update(ontology_sources=["BAO", "GO"])
        assert slot.ontology_sources == ["BAO", "GO"]

    def test_update_is_required(self, workspace_id: uuid.UUID):
        slot = OntologySlotDefinition.create(
            workspace_id=workspace_id,
            name="bioassay_type",
            label="Bioassay Type",
            ontology_sources=["BAO"],
        )
        slot.update(is_required=True)
        assert slot.is_required is True

    def test_update_allow_free_text(self, workspace_id: uuid.UUID):
        slot = OntologySlotDefinition.create(
            workspace_id=workspace_id,
            name="bioassay_type",
            label="Bioassay Type",
            ontology_sources=["BAO"],
        )
        slot.update(allow_free_text=False)
        assert slot.allow_free_text is False

    def test_update_display_order(self, workspace_id: uuid.UUID):
        slot = OntologySlotDefinition.create(
            workspace_id=workspace_id,
            name="bioassay_type",
            label="Bioassay Type",
            ontology_sources=["BAO"],
        )
        slot.update(display_order=10)
        assert slot.display_order == 10

    def test_update_empty_label_raises(self, workspace_id: uuid.UUID):
        slot = OntologySlotDefinition.create(
            workspace_id=workspace_id,
            name="bioassay_type",
            label="Bioassay Type",
            ontology_sources=["BAO"],
        )
        with pytest.raises(ValidationError, match="label must not be empty"):
            slot.update(label="")

    def test_update_empty_ontology_sources_raises(self, workspace_id: uuid.UUID):
        slot = OntologySlotDefinition.create(
            workspace_id=workspace_id,
            name="bioassay_type",
            label="Bioassay Type",
            ontology_sources=["BAO"],
        )
        with pytest.raises(ValidationError, match="ontology_sources must have at least one"):
            slot.update(ontology_sources=[])

    def test_update_no_args_still_emits_event(self, workspace_id: uuid.UUID):
        """Even a no-op update emits an event (consistent with salt_entry pattern)."""
        slot = OntologySlotDefinition.create(
            workspace_id=workspace_id,
            name="bioassay_type",
            label="Bioassay Type",
            ontology_sources=["BAO"],
        )
        slot.clear_events()
        slot.update()
        events = slot.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], OntologySlotDefinitionUpdated)
