"""Append-only SQLAlchemy audit repository.

No update or delete — only INSERT operations are permitted.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from chem_vault.domain.audit_compliance.models import (
    AuditEntry,
    AuditOperation,
    ElectronicSignature,
)
from chem_vault.infrastructure.persistence.sqlalchemy.audit.audit_models import (
    AuditEntryModel,
    AuditOperationModel,
    ElectronicSignatureModel,
)


class SQLAlchemyAuditRepository:
    """Append-only audit repository — no update, no delete."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, operation: AuditOperation) -> None:
        """Persist an audit operation with entries and optional signature.

        Uses its own short-lived session (not shared with UoW) so that
        audit records are committed independently of business transactions.
        """
        model = self._to_operation_model(operation)
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    async def save_with_session(
        self, operation: AuditOperation, session: AsyncSession
    ) -> None:
        """Persist an audit operation into the *provided* session.

        The caller owns the transaction — no commit is issued here.  Use this
        when you want the audit write to participate in the same transaction as
        the business operation (e.g. admin hard-delete), so that a failure in
        either rolls back both.
        """
        model = self._to_operation_model(operation)
        session.add(model)

    async def _find_by_id_unscoped(self, id: uuid.UUID) -> AuditOperation | None:
        """Retrieve an audit operation by ID with NO workspace check.

        Internal — production code must use ``find_by_id_in_workspace``.
        """
        stmt = (
            select(AuditOperationModel)
            .where(AuditOperationModel.id == id)
            .options(
                selectinload(AuditOperationModel.entries),
                selectinload(AuditOperationModel.signature),
            )
        )
        async with self._session_factory() as session:
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return self._to_domain(model)

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> AuditOperation | None:
        """Retrieve an audit operation by ID, scoped to workspace."""
        stmt = (
            select(AuditOperationModel)
            .where(
                AuditOperationModel.id == id,
                AuditOperationModel.workspace_id == workspace_id,
            )
            .options(
                selectinload(AuditOperationModel.entries),
                selectinload(AuditOperationModel.signature),
            )
        )
        async with self._session_factory() as session:
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return self._to_domain(model)

    async def find_by_entity(
        self, workspace_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
    ) -> list[AuditOperation]:
        """Retrieve all audit operations for a given entity within a workspace."""
        stmt = (
            select(AuditOperationModel)
            .where(
                AuditOperationModel.workspace_id == workspace_id,
                AuditOperationModel.entity_type == entity_type,
                AuditOperationModel.entity_id == entity_id,
            )
            .options(
                selectinload(AuditOperationModel.entries),
                selectinload(AuditOperationModel.signature),
            )
            .order_by(AuditOperationModel.started_at.desc())
        )
        async with self._session_factory() as session:
            result = await session.execute(stmt)
            return [self._to_domain(m) for m in result.scalars().all()]

    async def find_all(
        self,
        workspace_id: uuid.UUID,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[AuditOperation]:
        """Retrieve audit operations with optional filters, ordered by started_at DESC."""
        stmt = (
            select(AuditOperationModel)
            .where(AuditOperationModel.workspace_id == workspace_id)
            .options(
                selectinload(AuditOperationModel.entries),
                selectinload(AuditOperationModel.signature),
            )
        )
        if entity_type is not None:
            stmt = stmt.where(AuditOperationModel.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(AuditOperationModel.entity_id == entity_id)
        if user_id is not None:
            stmt = stmt.where(AuditOperationModel.user_id == user_id)
        stmt = stmt.order_by(AuditOperationModel.started_at.desc()).limit(limit)
        async with self._session_factory() as session:
            result = await session.execute(stmt)
            return [self._to_domain(m) for m in result.scalars().all()]

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_operation_model(op: AuditOperation) -> AuditOperationModel:
        model = AuditOperationModel(
            id=op.id,
            workspace_id=op.workspace_id,
            operation_type=op.operation_type.value,
            reason=op.reason,
            user_id=op.user_id,
            actor_type=op.actor_type.value,
            correlation_id=op.correlation_id,
            entity_type=op.entity_type,
            entity_id=op.entity_id,
            status=op.status.value,
            ip_address=op.ip_address,
            user_agent=op.user_agent,
            started_at=op.started_at,
            completed_at=op.completed_at,
        )
        model.entries = [
            SQLAlchemyAuditRepository._to_entry_model(e) for e in op.entries
        ]
        if op.signature is not None:
            model.signature = SQLAlchemyAuditRepository._to_signature_model(
                op.signature
            )
        return model

    @staticmethod
    def _to_entry_model(entry: AuditEntry) -> AuditEntryModel:
        return AuditEntryModel(
            id=entry.id,
            operation_id=entry.operation_id,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            field_name=entry.field_name,
            action=entry.action.value,
            old_value=entry.old_value,
            new_value=entry.new_value,
            timestamp=entry.timestamp,
        )

    @staticmethod
    def _to_signature_model(sig: ElectronicSignature) -> ElectronicSignatureModel:
        return ElectronicSignatureModel(
            id=sig.id,
            operation_id=sig.operation_id,
            user_id=sig.user_id,
            meaning=sig.meaning,
            auth_method=sig.auth_method.value,
            signed_at=sig.signed_at,
        )

    @staticmethod
    def _to_domain(model: AuditOperationModel) -> AuditOperation:
        from chem_vault.domain.audit_compliance.enums import (
            ActorType,
            AuditAction,
            AuditStatus,
            AuthMethod,
            OperationType,
        )

        entries = [
            AuditEntry(
                id=e.id,
                operation_id=e.operation_id,
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                field_name=e.field_name,
                action=AuditAction(e.action),
                old_value=e.old_value,
                new_value=e.new_value,
                timestamp=e.timestamp,
            )
            for e in model.entries
        ]

        signature = None
        if model.signature is not None:
            s = model.signature
            signature = ElectronicSignature(
                id=s.id,
                operation_id=s.operation_id,
                user_id=s.user_id,
                meaning=s.meaning,
                auth_method=AuthMethod(s.auth_method),
                signed_at=s.signed_at,
            )

        op = AuditOperation(
            id=model.id,
            workspace_id=model.workspace_id,
            operation_type=OperationType(model.operation_type),
            reason=model.reason,
            user_id=model.user_id,
            actor_type=ActorType(model.actor_type),
            correlation_id=model.correlation_id,
            entity_type=model.entity_type,
            entity_id=model.entity_id,
            status=AuditStatus(model.status),
            ip_address=model.ip_address,
            user_agent=model.user_agent,
            started_at=model.started_at,
            completed_at=model.completed_at,
            entries=entries,
            signature=signature,
        )
        return op
