"""Unit tests for the audit recording service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from chem_vault.application.audit.audit_recording_service import (
    AuditRecordingService,
    _infer_operation_type,
)
from chem_vault.domain.audit_compliance.enums import (
    ActorType,
    AuditAction,
    AuditStatus,
    OperationType,
)
from chem_vault.domain.audit_compliance.models import AuditEntry, AuditOperation
from chem_vault.domain.shared.events import DomainEvent


# --- Fakes ---


class FakeAuditRepository:
    """In-memory audit repository for testing."""

    def __init__(self) -> None:
        self.saved: list[AuditOperation] = []

    async def save(self, operation: AuditOperation) -> None:
        self.saved.append(operation)

    async def find_by_id(self, id: uuid.UUID) -> AuditOperation | None:
        return next((op for op in self.saved if op.id == id), None)

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> AuditOperation | None:
        # AuditOperation is append-only; just delegate to find_by_id
        return await self.find_by_id(id)

    async def find_by_entity(
        self, workspace_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
    ) -> list[AuditOperation]:
        return [
            op
            for op in self.saved
            if op.workspace_id == workspace_id
            and op.entity_type == entity_type
            and op.entity_id == entity_id
        ]


@dataclass(frozen=True, kw_only=True)
class FakeRegisteredEvent(DomainEvent):
    workspace_id: uuid.UUID = uuid.UUID(int=0)
    user_id: uuid.UUID = uuid.UUID(int=0)


@dataclass(frozen=True, kw_only=True)
class FakeMergedEvent(DomainEvent):
    workspace_id: uuid.UUID = uuid.UUID(int=0)
    user_id: uuid.UUID = uuid.UUID(int=0)


# --- Tests ---


class TestAuditRecordingService:
    @pytest.fixture
    def repo(self) -> FakeAuditRepository:
        return FakeAuditRepository()

    @pytest.fixture
    def service(self, repo: FakeAuditRepository) -> AuditRecordingService:
        return AuditRecordingService(repo)

    async def test_record_creates_operation(
        self, service: AuditRecordingService, repo: FakeAuditRepository
    ) -> None:
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()
        entity_id = uuid.uuid4()

        entries = [
            AuditEntry(
                entity_type="molecule",
                entity_id=entity_id,
                field_name="smiles",
                action=AuditAction.CREATE,
                new_value="CCO",
            ),
        ]

        result = await service.record(
            workspace_id=ws_id,
            operation_type=OperationType.REGISTRATION,
            entity_type="molecule",
            entity_id=entity_id,
            user_id=user_id,
            entries=entries,
        )

        assert len(repo.saved) == 1
        op = repo.saved[0]
        assert op.operation_type == OperationType.REGISTRATION
        assert op.entity_type == "molecule"
        assert op.entity_id == entity_id
        assert op.user_id == user_id
        assert op.workspace_id == ws_id
        assert op.status == AuditStatus.COMPLETED
        assert len(op.entries) == 1
        assert op.entries[0].operation_id == op.id
        assert result.id == op.id

    async def test_record_with_reason_and_ip(
        self, service: AuditRecordingService, repo: FakeAuditRepository
    ) -> None:
        result = await service.record(
            workspace_id=uuid.uuid4(),
            operation_type=OperationType.STRUCTURE_CORRECTION,
            entity_type="molecule",
            entity_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            entries=[],
            reason="Wrong stereochemistry",
            ip_address="10.0.0.1",
            user_agent="Mozilla/5.0",
        )

        assert result.reason == "Wrong stereochemistry"
        assert result.ip_address == "10.0.0.1"
        assert result.user_agent == "Mozilla/5.0"

    async def test_handle_event_creates_audit_operation(
        self, service: AuditRecordingService, repo: FakeAuditRepository
    ) -> None:
        agg_id = uuid.uuid4()
        ws_id = uuid.uuid4()
        user_id = uuid.uuid4()

        event = FakeRegisteredEvent(
            aggregate_id=agg_id,
            aggregate_type="molecule",
            workspace_id=ws_id,
            user_id=user_id,
        )

        await service.handle_event(event)

        assert len(repo.saved) == 1
        op = repo.saved[0]
        assert op.entity_type == "molecule"
        assert op.entity_id == agg_id
        assert op.workspace_id == ws_id
        assert op.actor_type == ActorType.SYSTEM
        assert len(op.entries) == 1
        assert op.entries[0].new_value == "FakeRegisteredEvent"


class TestInferOperationType:
    def test_registered_event(self) -> None:
        event = FakeRegisteredEvent(
            aggregate_id=uuid.uuid4(), aggregate_type="molecule"
        )
        assert _infer_operation_type(event) == OperationType.REGISTRATION

    def test_merged_event(self) -> None:
        event = FakeMergedEvent(
            aggregate_id=uuid.uuid4(), aggregate_type="molecule"
        )
        assert _infer_operation_type(event) == OperationType.MERGE

    def test_unknown_event_defaults_to_data_entry(self) -> None:
        event = DomainEvent(
            aggregate_id=uuid.uuid4(), aggregate_type="unknown", workspace_id=uuid.uuid4()
        )
        assert _infer_operation_type(event) == OperationType.DATA_ENTRY
