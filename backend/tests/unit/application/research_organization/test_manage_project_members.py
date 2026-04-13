"""Unit tests for project member management use cases."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.research_organization.manage_project_members import (
    AddProjectMember,
    AddProjectMemberCommand,
    ListProjectMembers,
    ListProjectMembersQuery,
    RemoveProjectMember,
    RemoveProjectMemberCommand,
    UpdateProjectMemberRole,
    UpdateProjectMemberRoleCommand,
)
from chem_vault.domain.research_organization.project import Project
from chem_vault.domain.research_organization.project_membership import (
    ProjectMember,
    ProjectRole,
)
from chem_vault.domain.shared.errors import NotFoundError, ValidationError
from chem_vault.domain.shared.events import DomainEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeUnitOfWork:
    async def commit(self) -> list[DomainEvent]:
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


def _fake_auth(*, is_admin: bool = False):
    auth = AsyncMock()
    auth.user_id = uuid.uuid4()
    auth.workspace_id = uuid.uuid4()
    auth.workspace_role = "editor"
    auth.is_admin = is_admin
    auth.has_role = lambda min_role: True
    return auth


def _fake_project(ws_id: uuid.UUID) -> Project:
    return Project(workspace_id=ws_id, name="Test", created_by=uuid.uuid4())


# ---------------------------------------------------------------------------
# AddProjectMember
# ---------------------------------------------------------------------------


class TestAddProjectMember:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        auth = _fake_auth(is_admin=True)
        project = _fake_project(auth.workspace_id)

        proj_repo = AsyncMock()
        proj_repo.find_by_id = AsyncMock(return_value=project)
        proj_repo.find_by_id_in_workspace = AsyncMock(return_value=project)

        member_repo = AsyncMock()
        member_repo.get_role = AsyncMock(return_value=ProjectRole.MANAGER)
        member_repo.add_member = AsyncMock()

        dispatcher = AsyncMock()
        dispatcher.dispatch = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = AddProjectMember(FakeUnitOfWork(), proj_repo, member_repo, dispatcher)
        result = await uc(
            AddProjectMemberCommand(
                workspace_id=auth.workspace_id,
                project_id=project.id,
                user_id=uuid.uuid4(),
                role="editor",
            ),
            auth=auth,
        )
        assert isinstance(result, Success)
        member = result.unwrap()
        assert isinstance(member, ProjectMember)
        assert member.role == ProjectRole.EDITOR
        member_repo.add_member.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()
        # Verify the ProjectMemberAdded event was included
        dispatched_events = dispatcher.dispatch_all.call_args[0][0]
        assert any(
            hasattr(e, "user_id") and e.aggregate_type == "Project"
            for e in dispatched_events
        )

    @pytest.mark.asyncio
    async def test_project_not_found(self) -> None:
        auth = _fake_auth(is_admin=True)

        proj_repo = AsyncMock()
        proj_repo.find_by_id = AsyncMock(return_value=None)
        proj_repo.find_by_id_in_workspace = AsyncMock(return_value=None)

        member_repo = AsyncMock()
        dispatcher = AsyncMock()

        uc = AddProjectMember(FakeUnitOfWork(), proj_repo, member_repo, dispatcher)
        result = await uc(
            AddProjectMemberCommand(
                workspace_id=auth.workspace_id,
                project_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                role="editor",
            ),
            auth=auth,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_invalid_role(self) -> None:
        auth = _fake_auth(is_admin=True)

        proj_repo = AsyncMock()
        member_repo = AsyncMock()
        dispatcher = AsyncMock()

        uc = AddProjectMember(FakeUnitOfWork(), proj_repo, member_repo, dispatcher)
        result = await uc(
            AddProjectMemberCommand(
                workspace_id=auth.workspace_id,
                project_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                role="superadmin",  # invalid
            ),
            auth=auth,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_no_auth_still_succeeds(self) -> None:
        """System calls with no auth context should succeed (workers bypass auth)."""
        project = _fake_project(uuid.uuid4())

        proj_repo = AsyncMock()
        proj_repo.find_by_id = AsyncMock(return_value=project)
        proj_repo.find_by_id_in_workspace = AsyncMock(return_value=project)

        member_repo = AsyncMock()
        member_repo.add_member = AsyncMock()

        dispatcher = AsyncMock()
        dispatcher.dispatch = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = AddProjectMember(FakeUnitOfWork(), proj_repo, member_repo, dispatcher)
        result = await uc(
            AddProjectMemberCommand(
                workspace_id=project.workspace_id,
                project_id=project.id,
                user_id=uuid.uuid4(),
                role="viewer",
            ),
            auth=None,
        )
        assert isinstance(result, Success)


# ---------------------------------------------------------------------------
# RemoveProjectMember
# ---------------------------------------------------------------------------


class TestRemoveProjectMember:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        auth = _fake_auth(is_admin=True)
        project = _fake_project(auth.workspace_id)

        proj_repo = AsyncMock()
        proj_repo.find_by_id = AsyncMock(return_value=project)
        proj_repo.find_by_id_in_workspace = AsyncMock(return_value=project)

        member_repo = AsyncMock()
        member_repo.get_role = AsyncMock(return_value=ProjectRole.MANAGER)
        member_repo.remove_member = AsyncMock()

        dispatcher = AsyncMock()
        dispatcher.dispatch = AsyncMock()
        dispatcher.dispatch_all = AsyncMock()

        uc = RemoveProjectMember(FakeUnitOfWork(), proj_repo, member_repo, dispatcher)
        result = await uc(
            RemoveProjectMemberCommand(
                workspace_id=auth.workspace_id,
                project_id=project.id,
                user_id=uuid.uuid4(),
            ),
            auth=auth,
        )
        assert isinstance(result, Success)
        assert result.unwrap() is None
        member_repo.remove_member.assert_awaited_once()
        dispatcher.dispatch_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_project_not_found(self) -> None:
        auth = _fake_auth(is_admin=True)

        proj_repo = AsyncMock()
        proj_repo.find_by_id = AsyncMock(return_value=None)
        proj_repo.find_by_id_in_workspace = AsyncMock(return_value=None)

        member_repo = AsyncMock()
        dispatcher = AsyncMock()

        uc = RemoveProjectMember(FakeUnitOfWork(), proj_repo, member_repo, dispatcher)
        result = await uc(
            RemoveProjectMemberCommand(
                workspace_id=auth.workspace_id,
                project_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            ),
            auth=auth,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)


# ---------------------------------------------------------------------------
# UpdateProjectMemberRole
# ---------------------------------------------------------------------------


class TestUpdateProjectMemberRole:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        auth = _fake_auth(is_admin=True)
        project = _fake_project(auth.workspace_id)
        target_user_id = uuid.uuid4()

        proj_repo = AsyncMock()
        proj_repo.find_by_id = AsyncMock(return_value=project)
        proj_repo.find_by_id_in_workspace = AsyncMock(return_value=project)

        member_repo = AsyncMock()
        member_repo.get_role = AsyncMock(return_value=ProjectRole.MANAGER)
        member_repo.update_role = AsyncMock()

        uc = UpdateProjectMemberRole(FakeUnitOfWork(), proj_repo, member_repo, AsyncMock())
        result = await uc(
            UpdateProjectMemberRoleCommand(
                workspace_id=auth.workspace_id,
                project_id=project.id,
                user_id=target_user_id,
                role="viewer",
            ),
            auth=auth,
        )
        assert isinstance(result, Success)
        member = result.unwrap()
        assert member.role == ProjectRole.VIEWER
        assert member.user_id == target_user_id
        member_repo.update_role.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_user_not_member(self) -> None:
        """Returns NotFoundError when target user is not a project member."""
        auth = _fake_auth(is_admin=True)
        project = _fake_project(auth.workspace_id)

        proj_repo = AsyncMock()
        proj_repo.find_by_id = AsyncMock(return_value=project)
        proj_repo.find_by_id_in_workspace = AsyncMock(return_value=project)

        member_repo = AsyncMock()
        # get_role called twice: first for caller (admin bypass skips it), but
        # non-admin path calls it for the target; with is_admin=True the guard
        # is bypassed, so only the target membership check matters.
        member_repo.get_role = AsyncMock(return_value=None)

        uc = UpdateProjectMemberRole(FakeUnitOfWork(), proj_repo, member_repo, AsyncMock())
        result = await uc(
            UpdateProjectMemberRoleCommand(
                workspace_id=auth.workspace_id,
                project_id=project.id,
                user_id=uuid.uuid4(),
                role="editor",
            ),
            auth=auth,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_invalid_role(self) -> None:
        auth = _fake_auth(is_admin=True)

        proj_repo = AsyncMock()
        member_repo = AsyncMock()

        uc = UpdateProjectMemberRole(FakeUnitOfWork(), proj_repo, member_repo, AsyncMock())
        result = await uc(
            UpdateProjectMemberRoleCommand(
                workspace_id=auth.workspace_id,
                project_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                role="god",
            ),
            auth=auth,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)

    @pytest.mark.asyncio
    async def test_project_not_found(self) -> None:
        auth = _fake_auth(is_admin=True)

        proj_repo = AsyncMock()
        proj_repo.find_by_id = AsyncMock(return_value=None)
        proj_repo.find_by_id_in_workspace = AsyncMock(return_value=None)

        member_repo = AsyncMock()

        uc = UpdateProjectMemberRole(FakeUnitOfWork(), proj_repo, member_repo, AsyncMock())
        result = await uc(
            UpdateProjectMemberRoleCommand(
                workspace_id=auth.workspace_id,
                project_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                role="editor",
            ),
            auth=auth,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)


# ---------------------------------------------------------------------------
# ListProjectMembers
# ---------------------------------------------------------------------------


class TestListProjectMembers:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        auth = _fake_auth(is_admin=True)
        project = _fake_project(auth.workspace_id)
        members = [
            ProjectMember(
                project_id=project.id, user_id=uuid.uuid4(), role=ProjectRole.MANAGER
            ),
        ]

        proj_repo = AsyncMock()
        proj_repo.find_by_id = AsyncMock(return_value=project)
        proj_repo.find_by_id_in_workspace = AsyncMock(return_value=project)

        member_repo = AsyncMock()
        member_repo.find_members = AsyncMock(return_value=members)

        uc = ListProjectMembers(FakeUnitOfWork(), proj_repo, member_repo)
        result = await uc(
            ListProjectMembersQuery(
                workspace_id=auth.workspace_id, project_id=project.id
            )
        )
        assert isinstance(result, Success)
        assert len(result.unwrap()) == 1
        assert result.unwrap()[0].role == ProjectRole.MANAGER

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        auth = _fake_auth(is_admin=True)
        project = _fake_project(auth.workspace_id)

        proj_repo = AsyncMock()
        proj_repo.find_by_id = AsyncMock(return_value=project)
        proj_repo.find_by_id_in_workspace = AsyncMock(return_value=project)

        member_repo = AsyncMock()
        member_repo.find_members = AsyncMock(return_value=[])

        uc = ListProjectMembers(FakeUnitOfWork(), proj_repo, member_repo)
        result = await uc(
            ListProjectMembersQuery(
                workspace_id=auth.workspace_id, project_id=project.id
            )
        )
        assert isinstance(result, Success)
        assert result.unwrap() == []

    @pytest.mark.asyncio
    async def test_project_not_found(self) -> None:
        auth = _fake_auth(is_admin=True)

        proj_repo = AsyncMock()
        proj_repo.find_by_id = AsyncMock(return_value=None)
        proj_repo.find_by_id_in_workspace = AsyncMock(return_value=None)

        member_repo = AsyncMock()

        uc = ListProjectMembers(FakeUnitOfWork(), proj_repo, member_repo)
        result = await uc(
            ListProjectMembersQuery(
                workspace_id=auth.workspace_id, project_id=uuid.uuid4()
            )
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
