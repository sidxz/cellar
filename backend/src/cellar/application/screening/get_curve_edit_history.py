"""Query the audit trail of point-exclusion edits for a dose-response curve.

Returns ``CURVE_POINT_EXCLUSION`` (and any other) audit operations recorded
against a ``DoseResponseCurve`` entity, newest-first. Feeds the FE's
edit-history popover on the DR chart edit panel.

The audit repository manages its own session (append-only), so this query
has no UoW dependency — mirrors ``ListAuditOperations`` in
``application/audit/query_audit.py``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.shared.query import Query
from cellar.domain.audit_compliance.models import AuditOperation
from cellar.domain.audit_compliance.repository import AuditRepository
from cellar.domain.shared.errors import DomainError

# The entity_type string written by RefitDoseResponseCurve when it records a
# CURVE_POINT_EXCLUSION operation. Kept here as a constant so the query side
# and the write side agree on the literal.
_DOSE_RESPONSE_CURVE_ENTITY_TYPE = "DoseResponseCurve"


@dataclass(frozen=True, kw_only=True)
class GetCurveEditHistoryQuery(Query):
    workspace_id: uuid.UUID
    curve_id: uuid.UUID


@dataclass(frozen=True)
class CurveEditHistoryEntry:
    field_name: str
    old_value: str | None
    new_value: str | None


@dataclass(frozen=True)
class CurveEditHistoryEvent:
    id: uuid.UUID
    operation_type: str
    user_id: uuid.UUID | None
    timestamp: datetime
    reason: str | None
    entries: list[CurveEditHistoryEntry]


@dataclass(frozen=True)
class GetCurveEditHistoryResult:
    events: list[CurveEditHistoryEvent]


class GetCurveEditHistory:
    """Return audit events for a single dose-response curve, newest-first."""

    def __init__(self, audit_repository: AuditRepository) -> None:
        self._audit = audit_repository

    async def __call__(
        self,
        input: GetCurveEditHistoryQuery,
        auth: AuthContext | None = None,
    ) -> Result[GetCurveEditHistoryResult, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        ops = await self._audit.find_by_entity(
            input.workspace_id,
            _DOSE_RESPONSE_CURVE_ENTITY_TYPE,
            input.curve_id,
        )
        # Defensive sort — the SQLAlchemy repo already orders by started_at
        # DESC, but in-memory fakes and alternate impls may not.
        ops_sorted = sorted(ops, key=_event_timestamp, reverse=True)
        events = [_to_event(op) for op in ops_sorted]
        return Success(GetCurveEditHistoryResult(events=events))


def _event_timestamp(op: AuditOperation) -> datetime:
    """Pick the most representative timestamp for ordering.

    Audit ops always have ``started_at``; ``completed_at`` is filled at
    write-time but kept optional in the domain dataclass.
    """
    return op.completed_at or op.started_at


def _to_event(op: AuditOperation) -> CurveEditHistoryEvent:
    operation_type = (
        op.operation_type.value if hasattr(op.operation_type, "value") else str(op.operation_type)
    )
    return CurveEditHistoryEvent(
        id=op.id,
        operation_type=operation_type,
        user_id=op.user_id,
        timestamp=_event_timestamp(op),
        reason=op.reason,
        entries=[
            CurveEditHistoryEntry(
                field_name=entry.field_name,
                old_value=entry.old_value,
                new_value=entry.new_value,
            )
            for entry in (op.entries or [])
        ],
    )
