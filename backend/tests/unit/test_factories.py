"""Tests for test factories — verify they produce valid domain objects."""

from __future__ import annotations

from chem_vault.domain.audit_compliance.enums import (
    AuditAction,
    AuditStatus,
    AuthMethod,
    OperationType,
)
from tests.factories.audit import (
    AuditEntryFactory,
    AuditOperationFactory,
    ElectronicSignatureFactory,
)


class TestAuditOperationFactory:
    def test_default_values(self) -> None:
        op = AuditOperationFactory()
        assert op.operation_type == OperationType.REGISTRATION
        assert op.status == AuditStatus.COMPLETED
        assert op.entity_type == "molecule"

    def test_override(self) -> None:
        op = AuditOperationFactory(operation_type=OperationType.MERGE)
        assert op.operation_type == OperationType.MERGE

    def test_unique_ids(self) -> None:
        op1 = AuditOperationFactory()
        op2 = AuditOperationFactory()
        assert op1.id != op2.id


class TestAuditEntryFactory:
    def test_default_values(self) -> None:
        entry = AuditEntryFactory()
        assert entry.action == AuditAction.CREATE
        assert entry.new_value == "CCO"

    def test_override(self) -> None:
        entry = AuditEntryFactory(field_name="status", action=AuditAction.UPDATE)
        assert entry.field_name == "status"
        assert entry.action == AuditAction.UPDATE


class TestElectronicSignatureFactory:
    def test_default_values(self) -> None:
        sig = ElectronicSignatureFactory()
        assert sig.auth_method == AuthMethod.PASSWORD
        assert sig.meaning == "I approve this assay run"
