"""Unit tests for audit domain models."""

from __future__ import annotations

import uuid

from cellar.domain.audit_compliance.enums import (
    AuditAction,
    AuthMethod,
)
from cellar.domain.audit_compliance.models import (
    AuditEntry,
    AuditOperation,
    ElectronicSignature,
)


class TestAuditOperation:


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

