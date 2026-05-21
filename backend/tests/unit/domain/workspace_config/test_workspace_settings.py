"""Tests for WorkspaceSettings aggregate."""

import uuid

import pytest

from cellar.domain.workspace_config.events import WorkspaceSettingsUpdated
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings


class TestWorkspaceSettingsCreate:
    def test_create_default(self) -> None:
        ws_id = uuid.uuid4()
        settings = WorkspaceSettings.create_default(workspace_id=ws_id)
        assert settings.id == ws_id
        assert settings.workspace_id == ws_id
        assert settings.registration_rules == {}
        assert settings.custom_field_definitions == []
        assert settings.default_molecule_type is None
        assert settings.audit_reason_policy is None
        assert settings.signature_required_for == []
        assert settings.audit_retention_days is None
        assert settings.formulation_number_scheme is None
        assert settings.version == 1

    def test_explicit_values(self) -> None:
        ws_id = uuid.uuid4()
        settings = WorkspaceSettings(
            id=ws_id,
            registration_rules={"numbering": "CV-{seq}"},
            default_molecule_type="small_molecule",
            audit_retention_days=365,
        )
        assert settings.registration_rules == {"numbering": "CV-{seq}"}
        assert settings.default_molecule_type == "small_molecule"
        assert settings.audit_retention_days == 365


class TestWorkspaceSettingsUpdate:
    def test_partial_update(self) -> None:
        settings = WorkspaceSettings.create_default(workspace_id=uuid.uuid4())
        settings.update(
            registration_rules={"numbering": "MOL-{seq}"},
            audit_retention_days=90,
        )
        assert settings.registration_rules == {"numbering": "MOL-{seq}"}
        assert settings.audit_retention_days == 90
        assert settings.custom_field_definitions == []  # unchanged

    def test_update_emits_event(self) -> None:
        settings = WorkspaceSettings.create_default(workspace_id=uuid.uuid4())
        settings.update(default_molecule_type="biologic")
        events = settings.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkspaceSettingsUpdated)

    def test_update_signature_required_for(self) -> None:
        settings = WorkspaceSettings.create_default(workspace_id=uuid.uuid4())
        settings.update(signature_required_for=["registration", "disclosure"])
        assert settings.signature_required_for == ["registration", "disclosure"]

    def test_update_to_none(self) -> None:
        settings = WorkspaceSettings(
            id=uuid.uuid4(), audit_retention_days=365
        )
        settings.update(audit_retention_days=None)
        assert settings.audit_retention_days is None


class TestCreateBatchOnDuplicate:
    def test_defaults_to_false_when_key_missing(self) -> None:
        ws = WorkspaceSettings.create_default(workspace_id=uuid.uuid4())
        assert ws.create_batch_on_duplicate is False

    def test_reads_from_registration_rules(self) -> None:
        ws = WorkspaceSettings(
            id=uuid.uuid4(),
            registration_rules={"create_batch_on_duplicate": True},
        )
        assert ws.create_batch_on_duplicate is True

    def test_falsey_when_explicitly_false(self) -> None:
        ws = WorkspaceSettings(
            id=uuid.uuid4(),
            registration_rules={"create_batch_on_duplicate": False, "foo": True},
        )
        assert ws.create_batch_on_duplicate is False


def _make(rules: dict | None = None) -> WorkspaceSettings:
    return WorkspaceSettings(id=uuid.uuid4(), registration_rules=rules)


class TestRegistrationNumberPrefix:
    def test_default_is_cc_dash(self) -> None:
        s = _make()
        assert s.registration_number_prefix == "CC-"

    def test_override_via_registration_rules(self) -> None:
        s = _make({"registration_number_prefix": "LAB-"})
        assert s.registration_number_prefix == "LAB-"

    def test_falsy_value_falls_back_to_default(self) -> None:
        # Empty string / None / missing key → default
        s = _make({"registration_number_prefix": ""})
        assert s.registration_number_prefix == "CC-"


class TestRegistrationNumberWidth:
    def test_default_is_six(self) -> None:
        s = _make()
        assert s.registration_number_width == 6

    def test_override_via_registration_rules(self) -> None:
        s = _make({"registration_number_width": 8})
        assert s.registration_number_width == 8

    def test_non_int_falls_back_to_default(self) -> None:
        s = _make({"registration_number_width": "abc"})
        assert s.registration_number_width == 6


class TestUpdateValidation:
    def test_rejects_prefix_lowercase(self) -> None:
        s = _make()
        with pytest.raises(ValueError, match="registration_number_prefix"):
            s.update(registration_rules={"registration_number_prefix": "cc-"})

    def test_rejects_prefix_without_dash(self) -> None:
        s = _make()
        with pytest.raises(ValueError, match="registration_number_prefix"):
            s.update(registration_rules={"registration_number_prefix": "CC"})

    def test_rejects_prefix_too_short(self) -> None:
        s = _make()
        with pytest.raises(ValueError, match="registration_number_prefix"):
            s.update(registration_rules={"registration_number_prefix": "C-"})

    def test_rejects_prefix_too_long(self) -> None:
        s = _make()
        with pytest.raises(ValueError, match="registration_number_prefix"):
            s.update(registration_rules={"registration_number_prefix": "TOOLONGPREFIX-"})

    def test_accepts_valid_prefix(self) -> None:
        s = _make()
        s.update(registration_rules={"registration_number_prefix": "MTBLEAD-"})
        assert s.registration_number_prefix == "MTBLEAD-"

    def test_rejects_width_below_four(self) -> None:
        s = _make()
        with pytest.raises(ValueError, match="registration_number_width"):
            s.update(registration_rules={"registration_number_width": 3})

    def test_rejects_width_above_eight(self) -> None:
        s = _make()
        with pytest.raises(ValueError, match="registration_number_width"):
            s.update(registration_rules={"registration_number_width": 9})

    def test_accepts_valid_width(self) -> None:
        s = _make()
        s.update(registration_rules={"registration_number_width": 7})
        assert s.registration_number_width == 7

    def test_preserves_other_registration_rules_on_update(self) -> None:
        s = _make({"create_batch_on_duplicate": True})
        s.update(registration_rules={
            "create_batch_on_duplicate": True,
            "registration_number_prefix": "CC-",
        })
        assert s.create_batch_on_duplicate is True
        assert s.registration_number_prefix == "CC-"
