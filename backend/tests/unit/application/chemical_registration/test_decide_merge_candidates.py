"""Unit tests for DecideMergeCandidates (batch merge-candidate decisions)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.chemical_registration.decide_merge_candidates import (
    DecideMergeCandidates,
    DecideMergeCandidatesCommand,
    MergeDecision,
)
from cellar.domain.shared.errors import AuthorizationError, ConflictError, NotFoundError
from tests.fakes.fake_auth import FakeAuth

WS_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _auth(role: str = "editor") -> FakeAuth:
    return FakeAuth(role=role, workspace_id=WS_ID, user_id=USER_ID)


def _cmd(decisions: list[MergeDecision]) -> DecideMergeCandidatesCommand:
    return DecideMergeCandidatesCommand(
        workspace_id=WS_ID, decided_by=USER_ID, decisions=decisions
    )


def _confirm_ok(target: uuid.UUID) -> AsyncMock:
    return AsyncMock(return_value=Success(SimpleNamespace(merged_into_molecule_id=target)))


class TestDecideMergeCandidates:
    @pytest.mark.asyncio
    async def test_confirm_success_carries_merge_target(self) -> None:
        target = uuid.uuid4()
        confirm, reject = _confirm_ok(target), AsyncMock()
        uc = DecideMergeCandidates(confirm, reject)
        d_id = uuid.uuid4()

        result = await uc(
            _cmd([MergeDecision(disclosure_id=d_id, action="confirm")]), auth=_auth()
        )

        data = result.unwrap()
        assert data.confirmed_count == 1
        assert data.rejected_count == 0
        assert data.error_count == 0
        [outcome] = data.outcomes
        assert outcome.success
        assert outcome.disclosure_id == d_id
        assert outcome.merged_into_molecule_id == target
        inner_cmd = confirm.await_args.args[0]
        assert inner_cmd.workspace_id == WS_ID
        assert inner_cmd.confirmed_by == USER_ID
        reject.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reject_success_passes_reason(self) -> None:
        confirm = AsyncMock()
        reject = AsyncMock(return_value=Success(SimpleNamespace()))
        uc = DecideMergeCandidates(confirm, reject)
        d_id = uuid.uuid4()

        result = await uc(
            _cmd([MergeDecision(disclosure_id=d_id, action="reject", reason="dup")]),
            auth=_auth(),
        )

        data = result.unwrap()
        assert data.rejected_count == 1
        assert data.error_count == 0
        [outcome] = data.outcomes
        assert outcome.success
        assert outcome.merged_into_molecule_id is None
        inner_cmd = reject.await_args.args[0]
        assert inner_cmd.reason == "dup"
        assert inner_cmd.rejected_by == USER_ID
        confirm.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inner_failure_is_row_error_not_batch_failure(self) -> None:
        confirm = AsyncMock(return_value=Failure(ConflictError("already merged")))
        uc = DecideMergeCandidates(confirm, AsyncMock())

        result = await uc(
            _cmd([MergeDecision(disclosure_id=uuid.uuid4(), action="confirm")]), auth=_auth()
        )

        data = result.unwrap()  # the batch itself succeeds
        assert data.error_count == 1
        assert data.confirmed_count == 0
        [outcome] = data.outcomes
        assert not outcome.success
        assert outcome.error == "already merged"

    @pytest.mark.asyncio
    async def test_unknown_action_is_row_error(self) -> None:
        confirm, reject = AsyncMock(), AsyncMock()
        uc = DecideMergeCandidates(confirm, reject)

        result = await uc(
            _cmd([MergeDecision(disclosure_id=uuid.uuid4(), action="explode")]), auth=_auth()
        )

        data = result.unwrap()
        assert data.error_count == 1
        [outcome] = data.outcomes
        assert not outcome.success
        assert "Unknown action 'explode'" in (outcome.error or "")
        confirm.assert_not_awaited()
        reject.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mixed_batch_preserves_order_and_counts(self) -> None:
        confirm = _confirm_ok(uuid.uuid4())
        reject = AsyncMock(return_value=Success(SimpleNamespace()))
        uc = DecideMergeCandidates(confirm, reject)
        ids = [uuid.uuid4() for _ in range(3)]

        result = await uc(
            _cmd(
                [
                    MergeDecision(disclosure_id=ids[0], action="confirm"),
                    MergeDecision(disclosure_id=ids[1], action="reject"),
                    MergeDecision(disclosure_id=ids[2], action="bogus"),
                ]
            ),
            auth=_auth(),
        )

        data = result.unwrap()
        assert (data.confirmed_count, data.rejected_count, data.error_count) == (1, 1, 1)
        assert [o.disclosure_id for o in data.outcomes] == ids

    @pytest.mark.asyncio
    async def test_viewer_role_raises(self) -> None:
        uc = DecideMergeCandidates(AsyncMock(), AsyncMock())
        with pytest.raises(AuthorizationError):
            await uc(_cmd([]), auth=_auth(role="viewer"))

    @pytest.mark.asyncio
    async def test_wrong_workspace_raises_not_found(self) -> None:
        uc = DecideMergeCandidates(AsyncMock(), AsyncMock())
        with pytest.raises(NotFoundError):
            await uc(_cmd([]), auth=FakeAuth(role="editor"))  # random workspace
