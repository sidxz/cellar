"""Unit tests for audit domain models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.audit_compliance.enums import (
    ActorType,
    AuditAction,
    AuditStatus,
    AuthMethod,
    OperationType,
)
from chem_vault.domain.audit_compliance.models import (
    AuditEntry,
    AuditOperation,
    ElectronicSignature,
)


class TestAuditOperation:
    def test_create_with_defaults(self) -> None:
        op = AuditOperation()
        assert op.id is not None
        assert op.operation_type == OperationType.DATA_ENTRY
        assert op.actor_type == ActorType.USER
        assert op.status == AuditStatus.COMPLETED
        assert op.entries == []
        assert op.signature is None

    def test_create_with_explicit_values(self) -> None:
        op_id = uuid.uuid4()
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        entity_id = uuid.uuid4()

        op = AuditOperation(
            id=op_id,
            workspace_id=ws_id,
            operation_type=OperationType.MERGE,
            reason="Disclosure resolved",
            user_id=user_id,
            actor_type=ActorType.USER,
            entity_type="molecule",
            entity_id=entity_id,
            status=AuditStatus.COMPLETED,
            ip_address="192.168.1.1",
        )

        assert op.id == op_id
        assert op.workspace_id == ws_id
        assert op.operation_type == OperationType.MERGE
        assert op.reason == "Disclosure resolved"
        assert op.entity_type == "molecule"
        assert op.ip_address == "192.168.1.1"

    def test_add_entry_sets_operation_id(self) -> None:
        op = AuditOperation()
        entry = AuditEntry(
            entity_type="molecule",
            entity_id=uuid.uuid4(),
            field_name="smiles",
            action=AuditAction.UPDATE,
            old_value="CCO",
            new_value="CCCO",
        )

        op.add_entry(entry)

        assert len(op.entries) == 1
        assert op.entries[0].operation_id == op.id

    def test_add_multiple_entries(self) -> None:
        op = AuditOperation()
        for i in range(5):
            op.add_entry(
                AuditEntry(
                    entity_type="batch",
                    entity_id=uuid.uuid4(),
                    field_name=f"field_{i}",
                    action=AuditAction.CREATE,
                    new_value=f"value_{i}",
                )
            )

        assert len(op.entries) == 5
        assert all(e.operation_id == op.id for e in op.entries)

    def test_add_signature(self) -> None:
        op = AuditOperation()
        sig = ElectronicSignature(
            user_id=uuid.uuid4(),
            meaning="I approve this assay run",
            auth_method=AuthMethod.MFA,
        )

        op.add_signature(sig)

        assert op.signature is not None
        assert op.signature.operation_id == op.id
        assert op.signature.auth_method == AuthMethod.MFA


class TestAuditEntry:
    def test_create_entry(self) -> None:
        entry = AuditEntry(
            entity_type="molecule",
            entity_id=uuid.uuid4(),
            field_name="status",
            action=AuditAction.UPDATE,
            old_value="draft",
            new_value="active",
        )
        assert entry.action == AuditAction.UPDATE
        assert entry.old_value == "draft"
        assert entry.new_value == "active"

    def test_create_entry_for_insert(self) -> None:
        entry = AuditEntry(
            entity_type="molecule",
            entity_id=uuid.uuid4(),
            field_name="smiles",
            action=AuditAction.CREATE,
            old_value=None,
            new_value="CCO",
        )
        assert entry.old_value is None


class TestElectronicSignature:
    def test_create_signature(self) -> None:
        sig = ElectronicSignature(
            user_id=uuid.uuid4(),
            meaning="I authorize this merge",
            auth_method=AuthMethod.PASSWORD,
        )
        assert sig.meaning == "I authorize this merge"
        assert sig.auth_method == AuthMethod.PASSWORD


class TestAuditEnums:
    def test_operation_type_values(self) -> None:
        assert OperationType.REGISTRATION == "registration"
        assert OperationType.MERGE == "merge"
        assert OperationType.DATA_LOCK == "data_lock"

    def test_actor_type_values(self) -> None:
        assert ActorType.USER == "user"
        assert ActorType.SYSTEM == "system"
        assert ActorType.INTEGRATION == "integration"

    def test_audit_status_values(self) -> None:
        assert AuditStatus.COMPLETED == "completed"
        assert AuditStatus.FAILED == "failed"

    def test_audit_action_values(self) -> None:
        assert AuditAction.CREATE == "create"
        assert AuditAction.UPDATE == "update"
        assert AuditAction.DELETE == "delete"

    def test_auth_method_values(self) -> None:
        assert AuthMethod.PASSWORD == "password"
        assert AuthMethod.MFA == "mfa"
        assert AuthMethod.BIOMETRIC == "biometric"
