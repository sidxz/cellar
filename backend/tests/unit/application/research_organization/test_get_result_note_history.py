"""Unit tests for GetResultNoteHistory: a row's note versions, newest first."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.research_organization.get_result_note_history import (
    GetResultNoteHistory,
    GetResultNoteHistoryQuery,
)
from cellar.domain.audit_compliance.enums import AuditAction, OperationType
from cellar.domain.audit_compliance.models import AuditEntry, AuditOperation
from cellar.domain.research_organization.campaign_result import ResultNote
from cellar.domain.shared.errors import NotFoundError
from tests.unit.application.research_organization._helpers import FakeUnitOfWork, fake_auth

_RID = uuid.uuid4()
_T1 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
_T2 = datetime(2026, 11, 21, 14, 3, tzinfo=UTC)


def _op(
    old: str | None,
    new: str | None,
    user: uuid.UUID,
    at: datetime,
    op_type: OperationType = OperationType.NOTE_EDIT,
) -> AuditOperation:
    return AuditOperation(
        operation_type=op_type,
        user_id=user,
        entity_type="CampaignResult",
        entity_id=_RID,
        started_at=at,
        entries=[
            AuditEntry(
                entity_type="CampaignResult",
                entity_id=_RID,
                field_name="notes",
                action=AuditAction.UPDATE,
                old_value=old,
                new_value=new,
            )
        ],
    )


async def _history(
    current: ResultNote | None, ops: list[AuditOperation], *, role: str = "editor"
) -> tuple[object, AsyncMock]:
    auth = fake_auth(role=role)
    campaign_repo = AsyncMock()
    campaign_repo.find_result_note = AsyncMock(return_value=current)
    audit_repo = AsyncMock()
    audit_repo.find_by_entity = AsyncMock(return_value=ops)
    uc = GetResultNoteHistory(
        uow=FakeUnitOfWork(), campaign_repo=campaign_repo, audit_repository=audit_repo
    )
    query = GetResultNoteHistoryQuery(
        workspace_id=auth.workspace_id, campaign_id=uuid.uuid4(), result_id=_RID
    )
    return await uc(query, auth=auth), audit_repo


@pytest.mark.asyncio
async def test_versions_newest_first_with_current_first() -> None:
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    # Given oldest first on purpose: the query sorts.
    ops = [_op(None, "a", u1, _T1), _op("a", "b", u2, _T2)]
    out, audit_repo = await _history(ResultNote("b", u2, _T2), ops)
    assert out == Success([ResultNote("b", u2, _T2), ResultNote("a", u1, _T1)])
    audit_repo.find_by_entity.assert_awaited_once()
    assert audit_repo.find_by_entity.await_args.args[1:] == ("CampaignResult", _RID)


@pytest.mark.asyncio
async def test_legacy_note_is_the_oldest_version() -> None:
    u = uuid.uuid4()
    out, _ = await _history(ResultNote("new", u, _T2), [_op("legacy", "new", u, _T2)])
    assert out == Success([ResultNote("new", u, _T2), ResultNote("legacy", None, None)])


@pytest.mark.asyncio
async def test_untracked_legacy_note_alone() -> None:
    out, _ = await _history(ResultNote("legacy", None, None), [])
    assert out == Success([ResultNote("legacy", None, None)])


@pytest.mark.asyncio
async def test_cleared_note_is_a_version() -> None:
    u = uuid.uuid4()
    out, _ = await _history(ResultNote(None, u, _T2), [_op("a", None, u, _T2)])
    assert isinstance(out, Success)
    assert out.unwrap()[0] == ResultNote(None, u, _T2)


@pytest.mark.asyncio
async def test_never_noted_row_is_empty() -> None:
    out, _ = await _history(ResultNote(None, None, None), [])
    assert out == Success([])


@pytest.mark.asyncio
async def test_unknown_result_is_not_found() -> None:
    out, audit_repo = await _history(None, [])
    assert isinstance(out, Failure)
    assert isinstance(out.failure(), NotFoundError)
    audit_repo.find_by_entity.assert_not_awaited()


@pytest.mark.asyncio
async def test_viewer_may_read() -> None:
    out, _ = await _history(ResultNote("x", None, None), [], role="viewer")
    assert out == Success([ResultNote("x", None, None)])


@pytest.mark.asyncio
async def test_other_operation_types_ignored() -> None:
    u = uuid.uuid4()
    ops = [
        _op("a", "b", u, _T2),
        _op("zzz", "yyy", u, _T1, op_type=OperationType.ADMIN_HARD_DELETE),
    ]
    out, _ = await _history(ResultNote("b", u, _T2), ops)
    assert out == Success([ResultNote("b", u, _T2), ResultNote("a", None, None)])
