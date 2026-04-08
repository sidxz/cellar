"""Integration tests for audit persistence — append-only tables, migration, REVOKE."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
from chem_vault.infrastructure.persistence.sqlalchemy.audit.audit_repository import (
    SQLAlchemyAuditRepository,
)


@pytest.fixture
def audit_repo(db_session: AsyncSession) -> SQLAlchemyAuditRepository:
    return SQLAlchemyAuditRepository(db_session)


def _make_operation(
    *,
    workspace_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
) -> AuditOperation:
    """Build a test audit operation with one entry."""
    ws = workspace_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    eid = entity_id or uuid.uuid4()
    op = AuditOperation(
        workspace_id=ws,
        operation_type=OperationType.REGISTRATION,
        user_id=uid,
        entity_type="molecule",
        entity_id=eid,
        status=AuditStatus.COMPLETED,
    )
    op.add_entry(
        AuditEntry(
            entity_type="molecule",
            entity_id=eid,
            field_name="smiles",
            action=AuditAction.CREATE,
            new_value="CCO",
        )
    )
    return op


class TestAuditRepositoryIntegration:
    async def test_save_and_find_by_id(
        self, audit_repo: SQLAlchemyAuditRepository, db_session: AsyncSession
    ) -> None:
        op = _make_operation()
        await audit_repo.save(op)
        await db_session.flush()

        loaded = await audit_repo.find_by_id(op.id)
        assert loaded is not None
        assert loaded.id == op.id
        assert loaded.operation_type == OperationType.REGISTRATION
        assert len(loaded.entries) == 1
        assert loaded.entries[0].field_name == "smiles"

    async def test_save_with_signature(
        self, audit_repo: SQLAlchemyAuditRepository, db_session: AsyncSession
    ) -> None:
        op = _make_operation()
        op.add_signature(
            ElectronicSignature(
                user_id=uuid.uuid4(),
                meaning="I approve this",
                auth_method=AuthMethod.MFA,
            )
        )
        await audit_repo.save(op)
        await db_session.flush()

        loaded = await audit_repo.find_by_id(op.id)
        assert loaded is not None
        assert loaded.signature is not None
        assert loaded.signature.auth_method == AuthMethod.MFA

    async def test_find_by_entity(
        self, audit_repo: SQLAlchemyAuditRepository, db_session: AsyncSession
    ) -> None:
        ws_id = uuid.uuid4()
        entity_id = uuid.uuid4()

        op1 = _make_operation(workspace_id=ws_id, entity_id=entity_id)
        op2 = _make_operation(workspace_id=ws_id, entity_id=entity_id)
        op_other = _make_operation(workspace_id=ws_id)  # different entity

        await audit_repo.save(op1)
        await audit_repo.save(op2)
        await audit_repo.save(op_other)
        await db_session.flush()

        results = await audit_repo.find_by_entity(ws_id, "molecule", entity_id)
        assert len(results) == 2
        result_ids = {r.id for r in results}
        assert op1.id in result_ids
        assert op2.id in result_ids

    async def test_find_by_id_not_found(
        self, audit_repo: SQLAlchemyAuditRepository
    ) -> None:
        result = await audit_repo.find_by_id(uuid.uuid4())
        assert result is None

    async def test_multiple_entries(
        self, audit_repo: SQLAlchemyAuditRepository, db_session: AsyncSession
    ) -> None:
        op = AuditOperation(
            workspace_id=uuid.uuid4(),
            operation_type=OperationType.MERGE,
            user_id=uuid.uuid4(),
            entity_type="molecule",
            entity_id=uuid.uuid4(),
            reason="Disclosure resolved",
        )
        for i in range(5):
            op.add_entry(
                AuditEntry(
                    entity_type="batch",
                    entity_id=uuid.uuid4(),
                    field_name="molecule_id",
                    action=AuditAction.UPDATE,
                    old_value=str(uuid.uuid4()),
                    new_value=str(uuid.uuid4()),
                )
            )
        await audit_repo.save(op)
        await db_session.flush()

        loaded = await audit_repo.find_by_id(op.id)
        assert loaded is not None
        assert len(loaded.entries) == 5


class TestAuditAppendOnly:
    """Verify that audit tables reject UPDATE and DELETE at the DB level."""

    async def test_update_audit_operation_denied(
        self, audit_repo: SQLAlchemyAuditRepository, db_session: AsyncSession
    ) -> None:
        op = _make_operation()
        await audit_repo.save(op)
        await db_session.flush()

        # Attempt raw UPDATE — should fail due to REVOKE
        with pytest.raises(Exception):  # noqa: B017
            await db_session.execute(
                text(
                    "UPDATE audit_operations SET reason = 'hacked' WHERE id = :id"
                ),
                {"id": str(op.id)},
            )

    async def test_delete_audit_operation_denied(
        self, audit_repo: SQLAlchemyAuditRepository, db_session: AsyncSession
    ) -> None:
        op = _make_operation()
        await audit_repo.save(op)
        await db_session.flush()

        # Attempt raw DELETE — should fail due to REVOKE
        with pytest.raises(Exception):  # noqa: B017
            await db_session.execute(
                text("DELETE FROM audit_operations WHERE id = :id"),
                {"id": str(op.id)},
            )

    async def test_delete_audit_entry_denied(
        self, audit_repo: SQLAlchemyAuditRepository, db_session: AsyncSession
    ) -> None:
        op = _make_operation()
        await audit_repo.save(op)
        await db_session.flush()

        entry_id = op.entries[0].id
        with pytest.raises(Exception):  # noqa: B017
            await db_session.execute(
                text("DELETE FROM audit_entries WHERE id = :id"),
                {"id": str(entry_id)},
            )
