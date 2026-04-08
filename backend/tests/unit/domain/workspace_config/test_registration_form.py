"""Unit tests for RegistrationForm aggregate and FieldOverride VO."""

import uuid
from uuid import uuid4

import pytest

from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.workspace_config.registration_form import (
    FieldOverride,
    RegistrationForm,
    RegistrationFormCreated,
    RegistrationFormUpdated,
)
from chem_vault.domain.workspace_config.enums import FieldTarget


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid4()


class TestFieldOverride:
    def test_basic_construction(self) -> None:
        fid = uuid4()
        fo = FieldOverride(field_definition_id=fid)
        assert fo.field_definition_id == fid
        assert fo.is_required is None
        assert fo.default_value is None
        assert fo.is_locked is False
        assert fo.pick_list_subset is None

    def test_full_construction(self) -> None:
        fid = uuid4()
        fo = FieldOverride(
            field_definition_id=fid,
            is_required=True,
            default_value="High",
            is_locked=True,
            pick_list_subset=["High", "Medium"],
        )
        assert fo.is_required is True
        assert fo.default_value == "High"
        assert fo.is_locked is True
        assert fo.pick_list_subset == ["High", "Medium"]

    def test_frozen(self) -> None:
        fo = FieldOverride(field_definition_id=uuid4())
        with pytest.raises(Exception):
            fo.is_required = True  # type: ignore[misc]

    def test_locked_without_default_raises(self) -> None:
        with pytest.raises(ValueError, match="locked"):
            FieldOverride(field_definition_id=uuid4(), is_locked=True, default_value=None)

    def test_locked_with_default_ok(self) -> None:
        fo = FieldOverride(field_definition_id=uuid4(), is_locked=True, default_value="X")
        assert fo.is_locked is True
        assert fo.default_value == "X"

    def test_not_locked_without_default_ok(self) -> None:
        fo = FieldOverride(field_definition_id=uuid4(), is_locked=False, default_value=None)
        assert fo.is_locked is False


class TestRegistrationFormCreate:
    def test_factory(self, ws_id: uuid.UUID) -> None:
        form = RegistrationForm.create(
            workspace_id=ws_id,
            name="Standard Registration",
            applies_to=FieldTarget.MOLECULE,
        )
        assert form.workspace_id == ws_id
        assert form.name == "Standard Registration"
        assert form.applies_to == FieldTarget.MOLECULE
        assert form.is_default is False
        assert form.field_overrides == []
        assert form.version == 1

    def test_factory_with_is_default(self, ws_id: uuid.UUID) -> None:
        form = RegistrationForm.create(
            workspace_id=ws_id,
            name="Default Form",
            applies_to=FieldTarget.BATCH,
            is_default=True,
        )
        assert form.is_default is True
        assert form.applies_to == FieldTarget.BATCH

    def test_factory_with_overrides(self, ws_id: uuid.UUID) -> None:
        override = FieldOverride(field_definition_id=uuid4(), is_required=True, default_value="X")
        form = RegistrationForm.create(
            workspace_id=ws_id,
            name="CRO Form",
            applies_to=FieldTarget.MOLECULE,
            field_overrides=[override],
        )
        assert len(form.field_overrides) == 1
        assert form.field_overrides[0].is_required is True

    def test_empty_name_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name"):
            RegistrationForm.create(
                workspace_id=ws_id,
                name="",
                applies_to=FieldTarget.MOLECULE,
            )

    def test_whitespace_name_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name"):
            RegistrationForm.create(
                workspace_id=ws_id,
                name="   ",
                applies_to=FieldTarget.MOLECULE,
            )

    def test_name_is_stripped(self, ws_id: uuid.UUID) -> None:
        form = RegistrationForm.create(
            workspace_id=ws_id,
            name="  Trimmed  ",
            applies_to=FieldTarget.MOLECULE,
        )
        assert form.name == "Trimmed"

    def test_factory_emits_created_event(self, ws_id: uuid.UUID) -> None:
        form = RegistrationForm.create(
            workspace_id=ws_id,
            name="Standard",
            applies_to=FieldTarget.MOLECULE,
        )
        events = form.collect_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, RegistrationFormCreated)
        assert event.aggregate_id == form.id
        assert event.aggregate_type == "RegistrationForm"
        assert event.workspace_id == ws_id
        assert event.name == "Standard"
        assert event.applies_to == FieldTarget.MOLECULE.value

    def test_locked_override_requires_default(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValueError, match="locked"):
            FieldOverride(field_definition_id=uuid4(), is_locked=True, default_value=None)


class TestRegistrationFormUpdate:
    def _make(self, ws_id: uuid.UUID) -> RegistrationForm:
        form = RegistrationForm.create(
            workspace_id=ws_id,
            name="Original Name",
            applies_to=FieldTarget.MOLECULE,
        )
        form.clear_events()
        return form

    def test_rename(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        form.update(name="Renamed Form")
        assert form.name == "Renamed Form"
        events = form.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], RegistrationFormUpdated)

    def test_update_overrides(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        new_override = FieldOverride(field_definition_id=uuid4(), is_required=False)
        form.update(field_overrides=[new_override])
        assert len(form.field_overrides) == 1
        assert form.field_overrides[0] is new_override

    def test_update_emits_event(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        form.update(name="New Name")
        events = form.collect_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, RegistrationFormUpdated)
        assert event.workspace_id == ws_id

    def test_update_empty_name_raises(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        with pytest.raises(ValidationError, match="name"):
            form.update(name="")

    def test_update_no_args_is_noop(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        form.clear_events()
        original_name = form.name
        form.update()
        # Name unchanged, but event is still registered
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

    def test_overrides_are_independent_copy(self, ws_id: uuid.UUID) -> None:
        """Mutation of the source list does not affect the stored field_overrides."""
        src = [FieldOverride(field_definition_id=uuid4())]
        form = RegistrationForm.create(
            workspace_id=ws_id,
            name="F",
            applies_to=FieldTarget.MOLECULE,
            field_overrides=src,
        )
        src.clear()
        assert len(form.field_overrides) == 1
