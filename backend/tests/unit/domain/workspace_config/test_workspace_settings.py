"""Tests for WorkspaceSettings aggregate."""

import uuid

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
