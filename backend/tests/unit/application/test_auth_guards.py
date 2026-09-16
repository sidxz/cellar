"""Tests for application-layer auth guards and FakeAuth."""

from __future__ import annotations

import uuid

import pytest

from cellar.application.auth import (
    LOAN_APPROVE_ACTION,
    require_admin,
    require_editor,
    require_loan_authority,
    require_same_user,
    require_same_workspace,
    require_workspace_role,
)
from cellar.domain.shared.errors import AuthorizationError, NotFoundError
from tests.fakes.fake_auth import FakeAuth



class TestRequireWorkspaceRole:
    def test_none_auth_passes(self) -> None:
        require_workspace_role(None, "admin")

    def test_sufficient_role_passes(self) -> None:
        require_workspace_role(FakeAuth(role="admin"), "editor")

    def test_exact_role_passes(self) -> None:
        require_workspace_role(FakeAuth(role="editor"), "editor")

    def test_insufficient_role_raises(self) -> None:
        with pytest.raises(AuthorizationError, match="editor"):
            require_workspace_role(FakeAuth(role="viewer"), "editor")


class TestRequireEditor:
    def test_editor_passes(self) -> None:
        require_editor(FakeAuth(role="editor"))

    def test_viewer_raises(self) -> None:
        with pytest.raises(AuthorizationError):
            require_editor(FakeAuth(role="viewer"))


class TestRequireAdmin:
    def test_admin_passes(self) -> None:
        require_admin(FakeAuth(role="admin"))

    def test_editor_raises(self) -> None:
        with pytest.raises(AuthorizationError):
            require_admin(FakeAuth(role="editor"))


class TestRequireSameWorkspace:
    def test_none_auth_passes(self) -> None:
        require_same_workspace(None, uuid.uuid4())

    def test_none_workspace_raises(self) -> None:
        with pytest.raises(AuthorizationError):
            require_same_workspace(FakeAuth(), None)

    def test_matching_workspace_passes(self) -> None:
        wid = uuid.uuid4()
        require_same_workspace(FakeAuth(workspace_id=wid), wid)

    def test_different_workspace_raises_not_found(self) -> None:
        wid = uuid.uuid4()
        other_wid = uuid.uuid4()
        with pytest.raises(NotFoundError):
            require_same_workspace(FakeAuth(workspace_id=wid), other_wid)


class TestRequireSameUser:
    def test_none_auth_passes(self) -> None:
        require_same_user(None, uuid.uuid4())

    def test_matching_user_passes(self) -> None:
        uid = uuid.uuid4()
        require_same_user(FakeAuth(user_id=uid), uid)

    def test_different_user_raises(self) -> None:
        uid = uuid.uuid4()
        other_uid = uuid.uuid4()
        with pytest.raises(AuthorizationError):
            require_same_user(FakeAuth(user_id=uid), other_uid)


class TestRequireLoanAuthority:
    async def test_none_auth_forbidden(self) -> None:
        with pytest.raises(AuthorizationError):
            await require_loan_authority(None, uuid.uuid4())

    async def test_admin_bypasses_org_and_action(self) -> None:
        auth = FakeAuth(role="admin", org_id=uuid.uuid4(), granted_actions=set())
        await require_loan_authority(auth, uuid.uuid4())  # no raise

    async def test_owner_org_member_with_action_passes(self) -> None:
        org = uuid.uuid4()
        auth = FakeAuth(role="editor", org_id=org, granted_actions={LOAN_APPROVE_ACTION})
        await require_loan_authority(auth, org)

    async def test_owner_org_member_without_action_forbidden(self) -> None:
        org = uuid.uuid4()
        auth = FakeAuth(role="editor", org_id=org, granted_actions=set())
        with pytest.raises(AuthorizationError):
            await require_loan_authority(auth, org)

    async def test_foreign_org_member_forbidden_even_with_action(self) -> None:
        auth = FakeAuth(role="editor", org_id=uuid.uuid4(), granted_actions={LOAN_APPROVE_ACTION})
        with pytest.raises(AuthorizationError):
            await require_loan_authority(auth, uuid.uuid4())

    async def test_viewer_forbidden(self) -> None:
        org = uuid.uuid4()
        auth = FakeAuth(role="viewer", org_id=org, granted_actions={LOAN_APPROVE_ACTION})
        with pytest.raises(AuthorizationError):
            await require_loan_authority(auth, org)
