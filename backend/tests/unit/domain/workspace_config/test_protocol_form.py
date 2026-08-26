"""Unit tests for ProtocolForm aggregate and related VOs."""

from __future__ import annotations

import uuid
from uuid import uuid4

import pytest

from cellar.domain.shared.errors import ValidationError
from cellar.domain.workspace_config.protocol_form import (
    ProtocolForm,
    ProtocolFormCondition,
    ProtocolFormCreated,
    ProtocolFormOntologyDefault,
    ProtocolFormReadout,
    ProtocolFormUpdated,
)


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid4()


def _readout(name: str = "IC50", data_type: str = "numeric") -> ProtocolFormReadout:
    return ProtocolFormReadout(name=name, data_type=data_type, unit="nM")


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# ProtocolForm — create
# ---------------------------------------------------------------------------


class TestProtocolFormCreate:
    def test_factory(self, ws_id: uuid.UUID) -> None:
        form = ProtocolForm.create(
            workspace_id=ws_id,
            name="Biochemical Assay",
            readout_templates=[_readout()],
        )
        assert form.workspace_id == ws_id
        assert form.name == "Biochemical Assay"
        assert form.description is None
        assert form.protocol_type is None
        assert form.is_default is False
        assert len(form.readout_templates) == 1
        assert form.condition_templates == []
        assert form.ontology_defaults == []
        assert form.version == 1

    def test_factory_full(self, ws_id: uuid.UUID) -> None:
        cond = ProtocolFormCondition(name="Temp", data_type="numeric", unit="C")
        onto = ProtocolFormOntologyDefault(slot_name="target", terms=[{"term_id": "T1"}])
        form = ProtocolForm.create(
            workspace_id=ws_id,
            name="Full Template",
            description="A complete template",
            protocol_type="dose_response",
            is_default=True,
            readout_templates=[_readout("EC50"), _readout("Emax")],
            condition_templates=[cond],
            ontology_defaults=[onto],
        )
        assert form.description == "A complete template"
        assert form.protocol_type == "dose_response"
        assert form.is_default is True
        assert len(form.readout_templates) == 2
        assert len(form.condition_templates) == 1
        assert len(form.ontology_defaults) == 1

    def test_empty_name_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name"):
            ProtocolForm.create(
                workspace_id=ws_id,
                name="",
                readout_templates=[_readout()],
            )

    def test_whitespace_name_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name"):
            ProtocolForm.create(
                workspace_id=ws_id,
                name="   ",
                readout_templates=[_readout()],
            )

    def test_name_is_stripped(self, ws_id: uuid.UUID) -> None:
        form = ProtocolForm.create(
            workspace_id=ws_id,
            name="  Trimmed  ",
            readout_templates=[_readout()],
        )
        assert form.name == "Trimmed"

    def test_no_readouts_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="readout"):
            ProtocolForm.create(
                workspace_id=ws_id,
                name="Bad Form",
                readout_templates=[],
            )

    def test_none_readouts_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="readout"):
            ProtocolForm.create(
                workspace_id=ws_id,
                name="Bad Form",
            )

    def test_readout_empty_name_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="readout template name"):
            ProtocolForm.create(
                workspace_id=ws_id,
                name="Form",
                readout_templates=[ProtocolFormReadout(name="", data_type="numeric")],
            )

    def test_factory_emits_created_event(self, ws_id: uuid.UUID) -> None:
        form = ProtocolForm.create(
            workspace_id=ws_id,
            name="Standard",
            readout_templates=[_readout()],
        )
        events = form.collect_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, ProtocolFormCreated)
        assert event.aggregate_id == form.id
        assert event.aggregate_type == "ProtocolForm"
        assert event.workspace_id == ws_id
        assert event.name == "Standard"

    def test_readout_templates_are_independent_copy(self, ws_id: uuid.UUID) -> None:
        src = [_readout()]
        form = ProtocolForm.create(
            workspace_id=ws_id,
            name="F",
            readout_templates=src,
        )
        src.clear()
        assert len(form.readout_templates) == 1


# ---------------------------------------------------------------------------
# ProtocolForm — update
# ---------------------------------------------------------------------------


class TestProtocolFormUpdate:
    def _make(self, ws_id: uuid.UUID) -> ProtocolForm:
        form = ProtocolForm.create(
            workspace_id=ws_id,
            name="Original",
            readout_templates=[_readout()],
        )
        form.clear_events()
        return form

    def test_rename(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        form.update(name="Renamed")
        assert form.name == "Renamed"
        events = form.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], ProtocolFormUpdated)

    def test_update_description(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        form.update(description="New desc")
        assert form.description == "New desc"

    def test_update_protocol_type(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        form.update(protocol_type="single_point")
        assert form.protocol_type == "single_point"

    def test_update_readouts(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        new_readout = _readout("EC50")
        form.update(readout_templates=[new_readout])
        assert len(form.readout_templates) == 1
        assert form.readout_templates[0].name == "EC50"

    def test_update_readouts_empty_raises(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        with pytest.raises(ValidationError, match="readout"):
            form.update(readout_templates=[])

    def test_update_readout_empty_name_raises(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        with pytest.raises(ValidationError, match="readout template name"):
            form.update(readout_templates=[ProtocolFormReadout(name="", data_type="text")])

    def test_update_conditions(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        cond = ProtocolFormCondition(name="pH", data_type="numeric")
        form.update(condition_templates=[cond])
        assert len(form.condition_templates) == 1

    def test_update_ontology_defaults(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        onto = ProtocolFormOntologyDefault(slot_name="assay_type", terms=[{"id": "1"}])
        form.update(ontology_defaults=[onto])
        assert len(form.ontology_defaults) == 1

    def test_update_empty_name_raises(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        with pytest.raises(ValidationError, match="name"):
            form.update(name="")

    def test_update_emits_event(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        form.update(name="New Name")
        events = form.collect_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, ProtocolFormUpdated)
        assert event.workspace_id == ws_id

    def test_update_no_args_is_noop_with_event(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        original_name = form.name
        form.update()
        assert form.name == original_name
        assert len(form.collect_events()) == 1

    def test_set_default_true(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        form.set_default(True)
        assert form.is_default is True

    def test_set_default_false(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        form.set_default(True)
        form.set_default(False)
        assert form.is_default is False

    def test_is_default_via_update(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        form.update(is_default=True)
        assert form.is_default is True
