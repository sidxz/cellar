"""ProjectAccess + link_molecules_to_projects: the shared rule every
"put compounds in a project" entry point goes through."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from cellar.application.research_organization.project_links import (
    ProjectAccess,
    link_molecules_to_projects,
)
from cellar.domain.research_organization.project import Project
from cellar.domain.research_organization.project_membership import ProjectRole
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ValidationError
from tests.fakes.fake_auth import FakeAuth

WS = uuid.uuid4()


def _access(project: Project | None, role: ProjectRole | None) -> ProjectAccess:
    projects = AsyncMock()
    projects.find_by_id_in_workspace = AsyncMock(return_value=project)
    members = AsyncMock()
    members.get_role = AsyncMock(return_value=role)
    return ProjectAccess(projects, members)


def _project(name: str = "Kinase") -> Project:
    return Project.create(workspace_id=WS, name=name, created_by=uuid.uuid4())


async def test_project_editor_may_link() -> None:
    auth = FakeAuth(role="editor", workspace_id=WS)
    access = _access(_project(), ProjectRole.EDITOR)
    assert await access.check_editable(WS, [uuid.uuid4()], auth) is None


async def test_unknown_project_is_not_found() -> None:
    auth = FakeAuth(role="editor", workspace_id=WS)
    err = await _access(None, None).check_editable(WS, [uuid.uuid4()], auth)
    assert isinstance(err, NotFoundError)


async def test_archived_project_is_rejected() -> None:
    project = _project("Old program")
    project.archive(archived_by=uuid.uuid4())
    auth = FakeAuth(role="admin", workspace_id=WS)
    err = await _access(project, None).check_editable(WS, [project.id], auth)
    assert isinstance(err, ValidationError)
    assert "Old program" in err.message


async def test_non_member_editor_is_forbidden_and_named() -> None:
    auth = FakeAuth(role="editor", workspace_id=WS)
    err = await _access(_project("GPCR"), None).check_editable(WS, [uuid.uuid4()], auth)
    assert isinstance(err, AuthorizationError)
    assert "GPCR" in err.message


async def test_viewer_role_is_forbidden() -> None:
    auth = FakeAuth(role="editor", workspace_id=WS)
    access = _access(_project(), ProjectRole.VIEWER)
    err = await access.check_editable(WS, [uuid.uuid4()], auth)
    assert isinstance(err, AuthorizationError)


async def test_admin_bypasses_membership() -> None:
    auth = FakeAuth(role="admin", workspace_id=WS)
    assert await _access(_project(), None).check_editable(WS, [uuid.uuid4()], auth) is None


async def test_repeated_project_ids_link_once() -> None:
    project_id, mol = uuid.uuid4(), uuid.uuid4()
    repo = AsyncMock()
    repo.add_to_project_many = AsyncMock(return_value=[mol])

    events = await link_molecules_to_projects(repo, WS, [project_id, project_id], [mol])

    repo.add_to_project_many.assert_awaited_once_with(WS, project_id, [mol])
    assert [(e.project_id, e.entity_id, e.entity_type) for e in events] == [
        (project_id, mol, "molecule")
    ]
