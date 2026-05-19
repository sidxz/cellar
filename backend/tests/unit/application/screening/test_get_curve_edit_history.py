"""Unit tests for the GetCurveEditHistory use case.

Verifies:
- ``find_by_entity`` is called with ``entity_type="DoseResponseCurve"`` and
  the curve_id (i.e. other entities' audit ops can't leak in).
- Events are sorted newest-first regardless of repo return order.
- Entries are projected into the read-side dataclass shape.
- ``require_workspace_role(auth, "viewer")`` gates access.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from returns.result import Success

from cellar.application.screening.get_curve_edit_history import (
    GetCurveEditHistory,
    GetCurveEditHistoryQuery,
)
from cellar.domain.audit_compliance.enums import (
    ActorType,
    AuditAction,
    AuditStatus,
    OperationType,
)
from cellar.domain.audit_compliance.models import AuditEntry, AuditOperation
from cellar.domain.shared.errors import AuthorizationError
from tests.fakes.fake_auth import FakeAuth


class FakeAuditRepository:
    """Minimal in-memory repository — only ``find_by_entity`` is exercised."""

    def __init__(self) -> None:
        self.saved: list[AuditOperation] = []
        self.calls: list[tuple[uuid.UUID, str, uuid.UUID]] = []

    def seed(self, *ops: AuditOperation) -> None:
        self.saved.extend(ops)

    async def save(self, operation: AuditOperation) -> None:  # pragma: no cover
        self.saved.append(operation)

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> AuditOperation | None:  # pragma: no cover
        return next(
            (op for op in self.saved if op.id == id and op.workspace_id == workspace_id),
            None,
        )

    async def find_by_entity(
        self, workspace_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID
    ) -> list[AuditOperation]:
        self.calls.append((workspace_id, entity_type, entity_id))
        return [
            op
            for op in self.saved
            if op.workspace_id == workspace_id
            and op.entity_type == entity_type
            and op.entity_id == entity_id
        ]

    async def find_all(self, *args: object, **kwargs: object) -> list[AuditOperation]:  # pragma: no cover
        return list(self.saved)


def _audit_op(
    *,
    workspace_id: uuid.UUID,
    entity_id: uuid.UUID,
    entity_type: str = "DoseResponseCurve",
    started_at: datetime,
    completed_at: datetime | None = None,
    reason: str | None = None,
    operation_type: OperationType = OperationType.CURVE_POINT_EXCLUSION,
    user_id: uuid.UUID | None = None,
    entries: list[AuditEntry] | None = None,
) -> AuditOperation:
    op = AuditOperation(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        operation_type=operation_type,
        reason=reason,
        user_id=user_id or uuid.uuid4(),
        actor_type=ActorType.USER,
        entity_type=entity_type,
        entity_id=entity_id,
        status=AuditStatus.COMPLETED,
        started_at=started_at,
        completed_at=completed_at if completed_at is not None else started_at,
    )
    for entry in entries or []:
        op.add_entry(entry)
    return op


def _entry(
    *,
    entity_id: uuid.UUID,
    field_name: str = "excluded_points",
    old_value: str | None = None,
    new_value: str | None = None,
) -> AuditEntry:
    return AuditEntry(
        entity_type="DoseResponseCurve",
        entity_id=entity_id,
        field_name=field_name,
        action=AuditAction.UPDATE,
        old_value=old_value,
        new_value=new_value,
    )


WS = uuid.uuid4()
CURVE_ID = uuid.uuid4()
OTHER_CURVE_ID = uuid.uuid4()


@pytest.mark.asyncio
class TestGetCurveEditHistory:
    async def test_returns_events_sorted_newest_first(self) -> None:
        repo = FakeAuditRepository()
        t0 = datetime(2026, 5, 1, 12, tzinfo=UTC)
        t1 = datetime(2026, 5, 15, 12, tzinfo=UTC)
        t2 = datetime(2026, 5, 10, 12, tzinfo=UTC)
        # Seed deliberately out of order to confirm the use case re-sorts.
        repo.seed(
            _audit_op(
                workspace_id=WS, entity_id=CURVE_ID, started_at=t0, reason="r1"
            ),
            _audit_op(
                workspace_id=WS, entity_id=CURVE_ID, started_at=t1, reason="r2"
            ),
            _audit_op(
                workspace_id=WS, entity_id=CURVE_ID, started_at=t2, reason="r3"
            ),
        )
        uc = GetCurveEditHistory(audit_repository=repo)
        auth = FakeAuth(role="viewer", workspace_id=WS)

        result = await uc(
            GetCurveEditHistoryQuery(workspace_id=WS, curve_id=CURVE_ID),
            auth=auth,
        )

        assert isinstance(result, Success)
        events = result.unwrap().events
        assert [e.reason for e in events] == ["r2", "r3", "r1"]
        # Caller passed entity_type="DoseResponseCurve" + curve_id.
        assert repo.calls == [(WS, "DoseResponseCurve", CURVE_ID)]

    async def test_filters_out_other_entity_audit_ops(self) -> None:
        repo = FakeAuditRepository()
        now = datetime(2026, 5, 19, tzinfo=UTC)
        repo.seed(
            _audit_op(workspace_id=WS, entity_id=CURVE_ID, started_at=now, reason="keep"),
            # Same workspace, same curve_id-shaped uuid — but DIFFERENT entity_type.
            _audit_op(
                workspace_id=WS,
                entity_id=CURVE_ID,
                entity_type="Run",
                started_at=now,
                reason="drop-by-entity-type",
            ),
            # Same workspace, different curve.
            _audit_op(
                workspace_id=WS,
                entity_id=OTHER_CURVE_ID,
                started_at=now,
                reason="drop-by-entity-id",
            ),
        )
        uc = GetCurveEditHistory(audit_repository=repo)
        auth = FakeAuth(role="viewer", workspace_id=WS)

        result = await uc(
            GetCurveEditHistoryQuery(workspace_id=WS, curve_id=CURVE_ID),
            auth=auth,
        )

        assert isinstance(result, Success)
        events = result.unwrap().events
        assert len(events) == 1
        assert events[0].reason == "keep"

    async def test_projects_entries_into_read_side_shape(self) -> None:
        repo = FakeAuditRepository()
        now = datetime(2026, 5, 19, tzinfo=UTC)
        repo.seed(
            _audit_op(
                workspace_id=WS,
                entity_id=CURVE_ID,
                started_at=now,
                reason="outlier: lid dropped on plate",
                entries=[
                    _entry(
                        entity_id=CURVE_ID,
                        field_name="excluded_points",
                        old_value="[]",
                        new_value='[{"idx": 3, "reason": "outlier"}]',
                    ),
                ],
            ),
        )
        uc = GetCurveEditHistory(audit_repository=repo)
        auth = FakeAuth(role="viewer", workspace_id=WS)

        result = await uc(
            GetCurveEditHistoryQuery(workspace_id=WS, curve_id=CURVE_ID),
            auth=auth,
        )

        assert isinstance(result, Success)
        events = result.unwrap().events
        assert len(events) == 1
        event = events[0]
        assert event.operation_type == "curve_point_exclusion"
        assert event.reason == "outlier: lid dropped on plate"
        assert len(event.entries) == 1
        assert event.entries[0].field_name == "excluded_points"
        assert event.entries[0].old_value == "[]"
        assert event.entries[0].new_value == '[{"idx": 3, "reason": "outlier"}]'

    async def test_empty_history_returns_empty_events_list(self) -> None:
        repo = FakeAuditRepository()
        uc = GetCurveEditHistory(audit_repository=repo)
        auth = FakeAuth(role="viewer", workspace_id=WS)

        result = await uc(
            GetCurveEditHistoryQuery(workspace_id=WS, curve_id=CURVE_ID),
            auth=auth,
        )

        assert isinstance(result, Success)
        assert result.unwrap().events == []

    async def test_rejects_auth_below_viewer_role(self) -> None:
        """Mirrors the gate used by the audit/screening read use cases:
        when an auth context is present but lacks the viewer role,
        ``require_workspace_role`` raises ``AuthorizationError``.
        """
        repo = FakeAuditRepository()
        uc = GetCurveEditHistory(audit_repository=repo)
        # role="none" is below viewer per the role hierarchy in FakeAuth.
        below_viewer = FakeAuth(role="none", workspace_id=WS)

        with pytest.raises(AuthorizationError):
            await uc(
                GetCurveEditHistoryQuery(workspace_id=WS, curve_id=CURVE_ID),
                auth=below_viewer,
            )

    async def test_system_call_bypass(self) -> None:
        """``auth=None`` is the worker/system bypass convention — must succeed."""
        repo = FakeAuditRepository()
        uc = GetCurveEditHistory(audit_repository=repo)

        result = await uc(
            GetCurveEditHistoryQuery(workspace_id=WS, curve_id=CURVE_ID),
            auth=None,
        )

        assert isinstance(result, Success)
        assert result.unwrap().events == []
