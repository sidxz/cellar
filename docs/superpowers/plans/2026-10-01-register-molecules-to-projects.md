# Register Molecules to Projects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let chemists put compounds into projects in bulk — a bulk "add to project" endpoint and an optional project choice at single and bulk registration — so project chips on `/search` stop reading 0.

**Architecture:** One application module (`project_links.py`) owns the access rule (`ProjectAccess.check_editable`) and the write (`link_molecules_to_projects` → `MoleculeRepository.add_to_project_many`, one `INSERT … SELECT … ON CONFLICT DO NOTHING RETURNING`). The bulk endpoint, `RegisterMolecule` and `StartBulkRegistration` all go through it. `RegisterMolecule` links the surviving compound inside its own unit of work; a new merge side effect re-points project links so confirmed merges keep them. `project_ids` rides the bulk path exactly like `create_batch_on_duplicate`.

**Tech Stack:** Python 3.13 · FastAPI · SQLAlchemy 2 async (asyncpg) · Temporal · pytest (+ testcontainers) · Next.js 16 / React 19 · TanStack Query · zustand · vitest · orval.

**Spec:** `docs/superpowers/specs/2026-10-01-register-molecules-to-projects-design.md`

## Global Constraints

- Backend tests touching the DB: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest …` from `backend/`.
- Backend lint: `uv run ruff check src tests/<touched files>` and `uv run ruff format` (line length 99).
- Frontend: `pnpm exec tsc --noEmit -p .`, `pnpm exec vitest run <paths>`, `pnpm lint` (check the exit code, not piped output) from `frontend/`.
- Commit with explicit pathspecs only: `git commit -m "…" -- <paths>` (the working tree carries unrelated user edits to `.gitignore`, `Makefile`, `frontend/next-env.d.ts`, `frontend/AGENTS.md` — never stage them).
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never add a `Claude-Session:` trailer.
- All API changes are additive (new endpoint, optional fields). Do not change existing response shapes (daikon consumes the API live).
- Frontend types for backend DTOs come from orval (`pnpm generate:api` with the backend on :8000); after regenerating, revert every file whose only change is the `OpenAPI spec version` line.
- The Temporal worker does not hot-reload: restart it with `make dev-worker` before trying a bulk upload in the dev app.

## Review Focus

- **Same project picked twice / repeated ids** → linked once, no error, one audit event per new link (Task 1 test).
- **Compound from another workspace referenced by UUID** → never linked (Task 1 repository test).
- **Pasting compounds already in the project** → counted in `already_present`, no new audit events (Task 2 test).
- **Registration that ends in an identifier conflict** → error, nothing registered, nothing linked (Task 4 test).
- **Merge where the survivor is already in the project** → no primary-key violation; survivor keeps one link (Task 3 test).

---

## File Map

| File | Responsibility |
|---|---|
| `backend/src/cellar/application/research_organization/project_links.py` (new) | `ProjectAccess.check_editable`, `link_molecules_to_projects` |
| `backend/src/cellar/domain/chemical_registration/repository.py` | `MoleculeRepository.add_to_project_many` protocol method |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py` | `add_to_project_many` SQL; `add_to_project` delegates |
| `backend/src/cellar/application/research_organization/manage_molecule_projects.py` | `AddMoleculesToProject` replaces `AddMoleculeToProject` |
| `backend/src/cellar/interface/routes/projects.py` | `POST /projects/{id}/molecules` (bulk); single route delegates |
| `backend/src/cellar/interface/dependencies/_research_organization.py`, `backend/src/cellar/infrastructure/di/_research_organization.py` | wiring |
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/molecule_project_merge_side_effect.py` (new) | re-point `molecule_projects` on merge |
| `backend/src/cellar/infrastructure/di/_chemical_registration.py` | register side effect; `RegisterMolecule` + `StartBulkRegistration` wiring |
| `backend/src/cellar/application/chemical_registration/register_molecule.py` | `project_ids` on the command; check + link |
| `backend/src/cellar/interface/routes/molecules.py` | `RegisterMoleculeBody.project_ids` |
| `backend/src/cellar/interface/routes/bulk_registration.py`, `application/chemical_registration/start_bulk_registration.py`, `application/chemical_registration/bulk_registration_orchestrator.py`, `infrastructure/temporal/orchestrators/bulk_registration.py`, `infrastructure/temporal/workflows/bulk_registration.py`, `infrastructure/temporal/activities/dtos.py`, `infrastructure/temporal/activities/registration.py`, `application/chemical_registration/bulk_registration_service.py` | thread `project_ids` through bulk |
| `frontend/src/features/chemical-registration/...` | wizard picker, payloads, summary |

---

### Task 1: Shared project access check + bulk link write

**Files:**
- Create: `backend/src/cellar/application/research_organization/project_links.py`
- Modify: `backend/src/cellar/domain/chemical_registration/repository.py` (MoleculeRepository protocol)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py:454-474`
- Test: `backend/tests/integration/test_project_scoping.py` (class `TestMoleculeProjectAssociation`)
- Test: `backend/tests/unit/application/research_organization/test_project_links.py` (new)

**Interfaces:**
- Produces: `MoleculeRepository.add_to_project_many(workspace_id: uuid.UUID, project_id: uuid.UUID, molecule_ids: list[uuid.UUID]) -> list[uuid.UUID]` (ids newly linked)
- Produces: `ProjectAccess(project_repo: ProjectRepository, member_repo: ProjectMemberRepository)` with `async check_editable(workspace_id: uuid.UUID, project_ids: list[uuid.UUID], auth: AuthContext | None) -> DomainError | None` (must run inside an open UoW)
- Produces: `async link_molecules_to_projects(molecule_repo: MoleculeRepository, workspace_id: uuid.UUID, project_ids: list[uuid.UUID], molecule_ids: list[uuid.UUID]) -> list[EntityAddedToProject]`

- [ ] **Step 1: Write the failing repository tests** — append to `TestMoleculeProjectAssociation` in `backend/tests/integration/test_project_scoping.py`:

```python
    async def test_add_to_project_many_returns_only_new_links(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, p1, p2, m1_id, m2_id, m3_id = await self._setup(uow)  # m1 already in p1

        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            added = await mol_repo.add_to_project_many(ws_id, p1.id, [m1_id, m3_id, m3_id])
            await uow.commit()

        assert added == [m3_id]
        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            assert await mol_repo.find_project_ids(ws_id, m3_id) == [p1.id]

    async def test_add_to_project_many_ignores_other_workspace(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, p1, p2, m1_id, m2_id, m3_id = await self._setup(uow)

        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            added = await mol_repo.add_to_project_many(uuid.uuid4(), p1.id, [m3_id])
            await uow.commit()

        assert added == []
        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            assert await mol_repo.find_project_ids(ws_id, m3_id) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/test_project_scoping.py -k add_to_project_many -v`
Expected: FAIL — `AttributeError: 'SQLAlchemyMoleculeRepository' object has no attribute 'add_to_project_many'`

- [ ] **Step 3: Add the protocol method** — in `backend/src/cellar/domain/chemical_registration/repository.py`, inside `class MoleculeRepository(Protocol)`, after `find_identifiers_in_workspace`:

```python
    async def add_to_project_many(
        self,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]:
        """Link molecules to a project; returns the ids newly linked.

        Ids outside the workspace are ignored; already-linked ids are skipped.
        """
        ...
```

- [ ] **Step 4: Implement it** — replace `add_to_project` (lines 454-474) in `molecule_repository.py` with:

```python
    async def add_to_project_many(
        self,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        molecule_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]:
        """Link molecules to a project in one statement; returns the ids newly linked.

        Defense-in-depth: the SELECT only yields molecules of ``workspace_id``.
        ``ON CONFLICT DO NOTHING`` makes repeats free, so RETURNING lists only
        new links (callers emit one audit event per new link).
        """
        if not molecule_ids:
            return []
        # A molecule saved earlier in this unit of work must be visible to the
        # INSERT … SELECT below (registration links in the same transaction).
        await self._session.flush()
        owned = select(MoleculeModel.id, sa.literal(project_id, type_=sa.Uuid)).where(
            MoleculeModel.workspace_id == workspace_id,
            MoleculeModel.id.in_(set(molecule_ids)),
        )
        stmt = (
            pg_insert(molecule_projects)
            .from_select(["molecule_id", "project_id"], owned)
            .on_conflict_do_nothing()
            .returning(molecule_projects.c.molecule_id)
        )
        result = await self._session.execute(stmt)
        return [row[0] for row in result]

    async def add_to_project(
        self, workspace_id: uuid.UUID, molecule_id: uuid.UUID, project_id: uuid.UUID
    ) -> None:
        """Link one molecule to a project (idempotent)."""
        await self.add_to_project_many(workspace_id, project_id, [molecule_id])
```

- [ ] **Step 5: Run the repository tests**

Run: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/test_project_scoping.py -v`
Expected: PASS (all, including the existing idempotency test)

- [ ] **Step 6: Write the failing unit tests** — create `backend/tests/unit/application/research_organization/test_project_links.py`:

```python
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
    assert await _access(_project(), ProjectRole.EDITOR).check_editable(WS, [uuid.uuid4()], auth) is None


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
    err = await _access(_project(), ProjectRole.VIEWER).check_editable(WS, [uuid.uuid4()], auth)
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
```

- [ ] **Step 7: Run to verify they fail**

Run: `uv run pytest tests/unit/application/research_organization/test_project_links.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cellar.application.research_organization.project_links'`

- [ ] **Step 8: Create `project_links.py`**

```python
"""Putting compounds into projects — the one access rule and the one write
shared by the bulk add endpoint and single / bulk registration."""

from __future__ import annotations

import uuid

from cellar.application.auth import AuthContext, require_project_role
from cellar.domain.chemical_registration.repository import MoleculeRepository
from cellar.domain.research_organization.enums import ProjectStatus
from cellar.domain.research_organization.events import EntityAddedToProject
from cellar.domain.research_organization.project_membership import ProjectRole
from cellar.domain.research_organization.repository import (
    ProjectMemberRepository,
    ProjectRepository,
)
from cellar.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)


class ProjectAccess:
    """May this caller add compounds to these projects?

    Every project must exist in the workspace and be active, and the caller must
    be a workspace admin or hold at least the editor project role. System calls
    (``auth=None``) skip the role check. Run inside an open unit of work — the
    repositories share it.
    """

    def __init__(
        self, project_repo: ProjectRepository, member_repo: ProjectMemberRepository
    ) -> None:
        self._project_repo = project_repo
        self._member_repo = member_repo

    async def check_editable(
        self,
        workspace_id: uuid.UUID,
        project_ids: list[uuid.UUID],
        auth: AuthContext | None,
    ) -> DomainError | None:
        """The first reason the caller may not link to ``project_ids``, else None."""
        for project_id in dict.fromkeys(project_ids):
            project = await self._project_repo.find_by_id_in_workspace(workspace_id, project_id)
            if project is None:
                return NotFoundError("Project", str(project_id))
            if project.status == ProjectStatus.ARCHIVED:
                return ValidationError(f"Project '{project.name}' is archived")
            if auth is None:
                continue
            role = await self._member_repo.get_role(workspace_id, project_id, auth.user_id)
            try:
                require_project_role(auth, role, ProjectRole.EDITOR)
            except AuthorizationError as exc:
                return AuthorizationError(f"{exc.message} ('{project.name}')", detail=exc.detail)
        return None


async def link_molecules_to_projects(
    molecule_repo: MoleculeRepository,
    workspace_id: uuid.UUID,
    project_ids: list[uuid.UUID],
    molecule_ids: list[uuid.UUID],
) -> list[EntityAddedToProject]:
    """Link every molecule to every project; one audit event per *new* link.

    The caller commits its unit of work, then dispatches the returned events.
    """
    events: list[EntityAddedToProject] = []
    for project_id in dict.fromkeys(project_ids):
        added = await molecule_repo.add_to_project_many(workspace_id, project_id, molecule_ids)
        events.extend(
            EntityAddedToProject(
                aggregate_id=project_id,
                aggregate_type="Project",
                workspace_id=workspace_id,
                entity_type="molecule",
                entity_id=molecule_id,
                project_id=project_id,
            )
            for molecule_id in added
        )
    return events
```

- [ ] **Step 9: Run the unit tests**

Run: `uv run pytest tests/unit/application/research_organization/test_project_links.py -v`
Expected: PASS (7 tests)

- [ ] **Step 10: Lint + commit**

```bash
uv run ruff check src tests/unit/application/research_organization/test_project_links.py tests/integration/test_project_scoping.py && uv run ruff format src
git add backend/src/cellar/application/research_organization/project_links.py backend/tests/unit/application/research_organization/test_project_links.py
git commit -m "feat(projects): shared project access check + bulk molecule link write

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/application/research_organization/project_links.py backend/src/cellar/domain/chemical_registration/repository.py backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py backend/tests/unit/application/research_organization/test_project_links.py backend/tests/integration/test_project_scoping.py
```

---

### Task 2: Bulk "add to project" endpoint

**Files:**
- Modify: `backend/src/cellar/application/research_organization/manage_molecule_projects.py:34-105` (replace `AddMoleculeToProject*`)
- Modify: `backend/src/cellar/infrastructure/di/_research_organization.py:243-257`
- Modify: `backend/src/cellar/interface/dependencies/_research_organization.py:78,132,265-267`
- Modify: `backend/src/cellar/interface/routes/projects.py:19-22,303-319`
- Test: `backend/tests/api/test_projects.py`

**Interfaces:**
- Consumes: `ProjectAccess`, `link_molecules_to_projects` (Task 1); `MoleculeResolver.resolve(workspace_id, refs) -> (resolved, unresolved)`; `MembershipResult(added, already_present, unresolved)` from `collection_membership.py`.
- Produces: `AddMoleculesToProjectCommand(workspace_id, project_id, refs: list[MoleculeReference])`; `AddMoleculesToProject.__call__(input, auth) -> Result[MembershipResult, DomainError]`; route `POST /api/v1/projects/{project_id}/molecules` → `201 {added_count, already_present, unresolved[]}` (the collection add contract, reused models).

- [ ] **Step 1: Write the failing API tests** — add to the imports of `backend/tests/api/test_projects.py` (`AsyncEngine` and `AsyncClient` are already imported):

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport

from tests.api.conftest import _create_test_app
from tests.fakes.fake_auth import FakeAuth
```

then append:

```python
async def _org(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/organizations",
        json={"name": f"BulkProjOrg-{uuid.uuid4().hex[:6]}", "org_type": "internal"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _mol(client: AsyncClient, org_id: str, name: str, smiles: str) -> dict:
    resp = await client.post(
        "/api/v1/molecules",
        json={"name": name, "smiles": smiles, "originating_org_id": org_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["molecule"]


@asynccontextmanager
async def _client_as(
    database_url: str, workspace_id: uuid.UUID, **auth_kwargs
) -> AsyncIterator[AsyncClient]:
    app = _create_test_app(database_url, FakeAuth(workspace_id=workspace_id, **auth_kwargs))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:  # type: ignore[arg-type]
        yield ac
    await app.state.container[AsyncEngine].dispose()


class TestBulkAddMoleculesToProject:
    async def test_mixed_references_resolve_and_report(self, client: AsyncClient) -> None:
        org = await _org(client)
        a = await _mol(client, org, "BulkA", "CCCCCCCCCCO")
        b = await _mol(client, org, "BulkB", "CCCCCCCCCCCO")
        proj = (await client.post("/api/v1/projects", json={"name": "Bulk P"})).json()["id"]

        resp = await client.post(
            f"/api/v1/projects/{proj}/molecules",
            json={
                "references": [
                    {"value": a["registration_number"], "ref_type": "registration_number"},
                    {"value": b["id"], "ref_type": "uuid"},
                    {"value": "NO-SUCH-CMPD", "ref_type": "registration_number"},
                ]
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["added_count"] == 2
        assert body["already_present"] == 0
        assert [u["value"] for u in body["unresolved"]] == ["NO-SUCH-CMPD"]

        stats = await client.get("/api/v1/projects/stats", params={"project_ids": [proj]})
        assert stats.json()[proj]["molecule_count"] == 2

    async def test_repeats_count_as_already_present(self, client: AsyncClient) -> None:
        org = await _org(client)
        a = await _mol(client, org, "RepeatA", "CCCCCCCCCCCCO")
        proj = (await client.post("/api/v1/projects", json={"name": "Repeat P"})).json()["id"]
        ref = {"references": [{"value": a["id"], "ref_type": "uuid"}]}

        assert (await client.post(f"/api/v1/projects/{proj}/molecules", json=ref)).json()[
            "added_count"
        ] == 1
        again = (await client.post(f"/api/v1/projects/{proj}/molecules", json=ref)).json()
        assert again["added_count"] == 0
        assert again["already_present"] == 1

    async def test_unknown_project_404(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/v1/projects/{uuid.uuid4()}/molecules", json={"references": []}
        )
        assert resp.status_code == 404

    async def test_archived_project_422(self, client: AsyncClient) -> None:
        proj = (await client.post("/api/v1/projects", json={"name": "Old P"})).json()["id"]
        assert (await client.post(f"/api/v1/projects/{proj}/archive")).status_code == 200
        resp = await client.post(f"/api/v1/projects/{proj}/molecules", json={"references": []})
        assert resp.status_code == 422

    async def test_non_member_editor_403(
        self, client: AsyncClient, database_url: str, workspace_id: uuid.UUID
    ) -> None:
        proj = (await client.post("/api/v1/projects", json={"name": "Private P"})).json()["id"]
        async with _client_as(
            database_url, workspace_id, role="editor", user_id=uuid.uuid4()
        ) as stranger:
            resp = await stranger.post(
                f"/api/v1/projects/{proj}/molecules", json={"references": []}
            )
        assert resp.status_code == 403

    async def test_single_add_route_keeps_its_contract(self, client: AsyncClient) -> None:
        org = await _org(client)
        a = await _mol(client, org, "SingleA", "CCCCCCCCCCCCCO")
        proj = (await client.post("/api/v1/projects", json={"name": "Single P"})).json()["id"]

        assert (await client.post(f"/api/v1/projects/{proj}/molecules/{a['id']}")).status_code == 204
        missing = await client.post(f"/api/v1/projects/{proj}/molecules/{uuid.uuid4()}")
        assert missing.status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

Run: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_projects.py -k "BulkAddMoleculesToProject" -v`
Expected: FAIL — bulk route returns 405 Method Not Allowed

- [ ] **Step 3: Replace the use case** — in `manage_molecule_projects.py`, delete the `AddMoleculeToProjectCommand` / `AddMoleculeToProject` section (lines 34-105) and add in its place:

```python
# ---------------------------------------------------------------------------
# AddMoleculesToProject
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class AddMoleculesToProjectCommand(Command):
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    refs: list[MoleculeReference]


class AddMoleculesToProject:
    """Put compounds into a project by any reference a chemist has
    (UUID, reg #, external id, SMILES, InChIKey, name)."""

    def __init__(
        self,
        uow: UnitOfWork,
        resolver: MoleculeResolver,
        molecule_repo: MoleculeRepository,
        project_access: ProjectAccess,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._resolver = resolver
        self._molecule_repo = molecule_repo
        self._project_access = project_access
        self._dispatcher = dispatcher

    async def __call__(
        self, input: AddMoleculesToProjectCommand, auth: AuthContext | None = None
    ) -> Result[MembershipResult, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            denied = await self._project_access.check_editable(
                input.workspace_id, [input.project_id], auth
            )
            if denied is not None:
                return Failure(denied)
            resolved, unresolved = await self._resolver.resolve(input.workspace_id, input.refs)
            molecule_ids = list(dict.fromkeys(r.molecule_id for r in resolved))
            events = await link_molecules_to_projects(
                self._molecule_repo, input.workspace_id, [input.project_id], molecule_ids
            )
            await self._uow.commit()
        await self._dispatcher.dispatch_all(list(events))
        added = [e.entity_id for e in events]
        return Success(
            MembershipResult(
                added=added,
                already_present=len(molecule_ids) - len(added),
                unresolved=unresolved,
            )
        )
```

Add imports at the top of the module:

```python
from cellar.application.research_organization.collection_membership import MembershipResult
from cellar.application.research_organization.project_links import (
    ProjectAccess,
    link_molecules_to_projects,
)
from cellar.application.shared.molecule_resolver import MoleculeReference, MoleculeResolver
```

Remove `EntityAddedToProject` from the `events` import (still used: `EntityRemovedFromProject`). Keep `ProjectRepository`/`ProjectMemberRepository`/`require_project_role` imports only if `RemoveMoleculeFromProject` still uses them (it does).

- [ ] **Step 4: Wire DI** — in `infrastructure/di/_research_organization.py`, replace the `container.define(AddMoleculeToProject, …)` line (256) with:

```python
    def _add_molecules_to_project(c: Container) -> AddMoleculesToProject:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        mol_repo = SQLAlchemyMoleculeRepository(uow)
        return AddMoleculesToProject(
            uow,
            MoleculeResolver(mol_repo, c[StructureProcessorProtocol]),
            mol_repo,
            ProjectAccess(SQLAlchemyProjectRepository(uow), SQLAlchemyProjectMemberRepository(uow)),
            c[EventDispatcher],
        )

    container.define(AddMoleculesToProject, _add_molecules_to_project)
```

Update the import (`AddMoleculeToProject` → `AddMoleculesToProject`) and add `from cellar.application.research_organization.project_links import ProjectAccess`.

- [ ] **Step 5: Wire the FastAPI dependency** — in `interface/dependencies/_research_organization.py` rename the import, the `__all__` entry and the alias:

```python
AddMoleculesToProjectDep = Annotated[
    AddMoleculesToProject, Depends(_get_use_case(AddMoleculesToProject))
]
```

- [ ] **Step 6: Routes** — in `interface/routes/projects.py` replace the single-add route (lines 303-319) with both routes:

```python
@router.post(
    "/{project_id}/molecules",
    response_model=MembershipResultResponse,
    status_code=201,
)
async def add_molecules_to_project(
    project_id: uuid.UUID,
    body: AddMoleculesBody,
    auth: AuthDep,
    use_case: AddMoleculesToProjectDep,
) -> MembershipResultResponse:
    """Put compounds into the project by UUID, reg #, external id, SMILES,
    InChIKey or name. Unmatched values come back in ``unresolved``."""
    refs = [
        MoleculeReference(value=r.value, ref_type=RefType(r.ref_type)) for r in body.references
    ]
    result = result_to_response(
        await use_case(
            AddMoleculesToProjectCommand(
                workspace_id=auth.workspace_id, project_id=project_id, refs=refs
            ),
            auth=auth,
        )
    )
    return MembershipResultResponse(
        added_count=len(result.added),
        already_present=result.already_present,
        unresolved=[
            UnresolvedMoleculeResponse(
                value=u.ref.value, ref_type=u.ref.ref_type.value, reason=u.reason
            )
            for u in result.unresolved
        ],
    )


@router.post("/{project_id}/molecules/{molecule_id}", status_code=204)
async def add_molecule_to_project(
    project_id: uuid.UUID,
    molecule_id: uuid.UUID,
    auth: AuthDep,
    use_case: AddMoleculesToProjectDep,
) -> Response:
    result = result_to_response(
        await use_case(
            AddMoleculesToProjectCommand(
                workspace_id=auth.workspace_id,
                project_id=project_id,
                refs=[MoleculeReference(value=str(molecule_id), ref_type=RefType.UUID)],
            ),
            auth=auth,
        )
    )
    if result.unresolved:
        raise NotFoundError("Molecule", str(molecule_id))
    return Response(status_code=204)
```

Imports for `projects.py`:

```python
from cellar.application.research_organization.manage_molecule_projects import (
    AddMoleculesToProjectCommand,
    ListMoleculeProjectsQuery,
    RemoveMoleculeFromProjectCommand,
)
from cellar.application.shared.molecule_resolver import MoleculeReference, RefType
from cellar.domain.shared.errors import NotFoundError
from cellar.interface.routes.collections import (
    AddMoleculesBody,
    MembershipResultResponse,
    UnresolvedMoleculeResponse,
)
```

(keep whatever else the existing `manage_molecule_projects` import listed; swap `AddMoleculeToProjectDep` → `AddMoleculesToProjectDep` in the dependencies import). `NotFoundError` raised in a route is mapped to 404 by the global `DomainError` handler.

- [ ] **Step 7: Run the tests**

Run: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_projects.py tests/integration/test_project_scoping.py -v`
Expected: PASS (new + existing — `_create_molecule_in_project` still uses the single route)

- [ ] **Step 8: Confirm nothing else imported the old use case**

Run: `rg -n "AddMoleculeToProject\b|AddMoleculeToProjectCommand|AddMoleculeToProjectDep" src tests`
Expected: no output

- [ ] **Step 9: Lint + commit**

```bash
uv run ruff check src tests/api/test_projects.py && uv run ruff format src tests/api/test_projects.py
git commit -m "feat(projects): bulk add compounds to a project by any reference

POST /projects/{id}/molecules takes {references:[{value, ref_type}]} (the
collection add contract) and returns {added_count, already_present,
unresolved}. The single-compound route keeps its URL and 204/404 contract
but runs on the same use case.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/application/research_organization/manage_molecule_projects.py backend/src/cellar/infrastructure/di/_research_organization.py backend/src/cellar/interface/dependencies/_research_organization.py backend/src/cellar/interface/routes/projects.py backend/tests/api/test_projects.py
```

---

### Task 3: Merges carry project links

**Files:**
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/molecule_project_merge_side_effect.py`
- Modify: `backend/src/cellar/infrastructure/di/_chemical_registration.py:332-348` (registry list + import)
- Test: `backend/tests/integration/test_project_scoping.py` (new class)

**Interfaces:**
- Produces: `MoleculeProjectMergeSideEffect().on_merge(uow, source_molecule_id, target_molecule_id) -> None` (the `MergeSideEffectRegistry` protocol).

- [ ] **Step 1: Write the failing test** — append to `backend/tests/integration/test_project_scoping.py`:

```python
@pytest.mark.integration
class TestMoleculeProjectMergeSideEffect:
    async def test_links_move_to_survivor_and_dedupe(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            proj_repo = SQLAlchemyProjectRepository(uow)
            shared = Project.create(workspace_id=ws_id, name="Shared", created_by=user_id)
            only_src = Project.create(workspace_id=ws_id, name="OnlySrc", created_by=user_id)
            await proj_repo.save(shared)
            await proj_repo.save(only_src)
            await uow.commit()
        src, tgt = uuid.uuid4(), uuid.uuid4()
        await _insert_molecule_raw(uow, src, ws_id, f"CV-{src.hex[:5]}")
        await _insert_molecule_raw(uow, tgt, ws_id, f"CV-{tgt.hex[:5]}")
        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            await mol_repo.add_to_project_many(ws_id, shared.id, [src, tgt])
            await mol_repo.add_to_project_many(ws_id, only_src.id, [src])
            await uow.commit()

        async with uow:
            await MoleculeProjectMergeSideEffect().on_merge(uow, src, tgt)
            await uow.commit()

        async with uow:
            mol_repo = SQLAlchemyMoleculeRepository(uow)
            assert set(await mol_repo.find_project_ids(ws_id, tgt)) == {shared.id, only_src.id}
            assert await mol_repo.find_project_ids(ws_id, src) == []
```

with the import:

```python
from cellar.infrastructure.persistence.sqlalchemy.research_organization.molecule_project_merge_side_effect import (  # noqa: E501
    MoleculeProjectMergeSideEffect,
)
```

- [ ] **Step 2: Run to verify it fails**

Run: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/test_project_scoping.py -k MergeSideEffect -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
"""MoleculeProjectMergeSideEffect — carry project membership across a molecule merge.

``molecule_projects`` rows of the merged-away (source) molecule move to the
survivor; otherwise a confirmed merge silently drops the compound from every
project it was registered to. If both are already in a project, the source row
is deleted first to avoid a composite-PK violation on re-point.

Mirrors :class:`MoleculeTagMergeSideEffect`.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from cellar.application.shared.unit_of_work import UnitOfWork


class MoleculeProjectMergeSideEffect:
    """Re-point molecule_projects rows from source to target molecule."""

    async def on_merge(
        self,
        uow: UnitOfWork,
        source_molecule_id: uuid.UUID,
        target_molecule_id: uuid.UUID,
    ) -> None:
        session = uow.session  # type: ignore[attr-defined]
        params = {"source": source_molecule_id, "target": target_molecule_id}
        await session.execute(
            sa.text(
                "DELETE FROM molecule_projects mp1 "
                "WHERE mp1.molecule_id = :source "
                "AND EXISTS ("
                "SELECT 1 FROM molecule_projects mp2 "
                "WHERE mp2.project_id = mp1.project_id "
                "AND mp2.molecule_id = :target"
                ")"
            ),
            params,
        )
        await session.execute(
            sa.text(
                "UPDATE molecule_projects SET molecule_id = :target WHERE molecule_id = :source"
            ),
            params,
        )
```

- [ ] **Step 4: Register it** — in `_build_merge_registry` (`infrastructure/di/_chemical_registration.py`) add `MoleculeProjectMergeSideEffect(),` after `CollectionMergeSideEffect(),`, with the import beside the collection side-effect import:

```python
from cellar.infrastructure.persistence.sqlalchemy.research_organization.molecule_project_merge_side_effect import (  # noqa: E501
    MoleculeProjectMergeSideEffect,
)
```

- [ ] **Step 5: Run the tests**

Run: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/test_project_scoping.py tests/integration/test_tagging.py -k MergeSideEffect -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
uv run ruff check src && uv run ruff format src
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/molecule_project_merge_side_effect.py
git commit -m "fix(merge): carry project membership to the surviving compound

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/molecule_project_merge_side_effect.py backend/src/cellar/infrastructure/di/_chemical_registration.py backend/tests/integration/test_project_scoping.py
```

---

### Task 4: Project choice at single registration

**Files:**
- Modify: `backend/src/cellar/application/chemical_registration/register_molecule.py` (command, ctor, `__call__`, both register paths)
- Modify: `backend/src/cellar/infrastructure/di/_chemical_registration.py:228-236` (`_register_molecule`)
- Modify: `backend/src/cellar/interface/routes/molecules.py` (`RegisterMoleculeBody`, `register_molecule` route)
- Test: `backend/tests/api/test_molecules_register.py`

**Interfaces:**
- Consumes: `ProjectAccess`, `link_molecules_to_projects` (Task 1).
- Produces: `RegisterMoleculeCommand.project_ids: list[uuid.UUID]` (default `[]`); `RegisterMolecule(..., project_access: ProjectAccess | None = None)`; `RegisterMoleculeBody.project_ids: list[uuid.UUID] = []`.

- [ ] **Step 1: Write the failing API tests** — append to `backend/tests/api/test_molecules_register.py` (add `import uuid` at the top):

```python
async def _project(client: AsyncClient, name: str) -> str:
    resp = await client.post("/api/v1/projects", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _project_ids_of(client: AsyncClient, molecule_id: str) -> set[str]:
    resp = await client.get(f"/api/v1/molecules/{molecule_id}/projects")
    assert resp.status_code == 200, resp.text
    return set(resp.json())  # the route returns a list of project UUIDs


@pytest.mark.asyncio
async def test_register_links_new_compound_to_projects(
    client: AsyncClient, originating_org_id: str
):
    p1, p2 = await _project(client, "Reg P1"), await _project(client, "Reg P2")
    resp = await client.post(
        "/api/v1/molecules",
        json={
            "name": "RegLinked",
            "smiles": "CCCCCCCCCCCCCCN",
            "originating_org_id": originating_org_id,
            "project_ids": [p1, p2, p1],
        },
    )
    assert resp.status_code == 201, resp.text
    assert await _project_ids_of(client, resp.json()["molecule"]["id"]) == {p1, p2}


@pytest.mark.asyncio
async def test_register_duplicate_links_existing_compound(
    client: AsyncClient, originating_org_id: str
):
    first = await client.post(
        "/api/v1/molecules",
        json={"name": "DupA", "smiles": "CCCCCCCCCCCCCCCN", "originating_org_id": originating_org_id},
    )
    proj = await _project(client, "Dup P")
    second = await client.post(
        "/api/v1/molecules",
        json={
            "name": "DupB",
            "smiles": "CCCCCCCCCCCCCCCN",
            "originating_org_id": originating_org_id,
            "project_ids": [proj],
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["is_new"] is False
    assert await _project_ids_of(client, first.json()["molecule"]["id"]) == {proj}


@pytest.mark.asyncio
async def test_register_with_archived_project_registers_nothing(
    client: AsyncClient, originating_org_id: str
):
    proj = await _project(client, "Archived Reg P")
    assert (await client.post(f"/api/v1/projects/{proj}/archive")).status_code == 200
    resp = await client.post(
        "/api/v1/molecules",
        json={
            "name": "NeverRegistered",
            "smiles": "CCCCCCCCCCCCCCCCN",
            "originating_org_id": originating_org_id,
            "project_ids": [proj],
        },
    )
    assert resp.status_code == 422
    listed = await client.get("/api/v1/molecules", params={"q": "NeverRegistered"})
    assert listed.json()["items"] == []


@pytest.mark.asyncio
async def test_identifier_conflict_links_nothing(
    client: AsyncClient, originating_org_id: str
):
    # The name is an identifier: "Taken" now belongs to a different structure.
    await client.post(
        "/api/v1/molecules",
        json={"name": "Taken", "smiles": "CCCCCCCCCCCCCCCCCN", "originating_org_id": originating_org_id},
    )
    proj = await _project(client, "Conflict P")
    resp = await client.post(
        "/api/v1/molecules",
        json={
            "name": "Taken",
            "smiles": "c1ccccc1CCCCCCCCN",
            "originating_org_id": originating_org_id,
            "project_ids": [proj],
        },
    )
    assert resp.status_code == 409
    stats = await client.get("/api/v1/projects/stats", params={"project_ids": [proj]})
    assert stats.json()[proj]["molecule_count"] == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_molecules_register.py -v`
Expected: the new tests FAIL (link assertions see an empty set; archived case returns 201)

- [ ] **Step 3: Command + constructor** — in `register_molecule.py`:

```python
@dataclass(frozen=True, kw_only=True)
class RegisterMoleculeCommand(Command):
    ...  # existing fields unchanged
    auto_approve: bool = True  # False from wizard — merge candidates need confirmation
    # Projects to put the surviving compound in (new, matched or disclosed).
    project_ids: list[uuid.UUID] = field(default_factory=list)
```

Constructor gains `project_access: ProjectAccess | None = None` (store as `self._project_access`). Import:

```python
from cellar.application.research_organization.project_links import (
    ProjectAccess,
    link_molecules_to_projects,
)
from cellar.domain.shared.events import DomainEvent
```

- [ ] **Step 4: Check access before registering** — at the top of `__call__`, after `require_same_workspace(...)`:

```python
        if input.project_ids and self._project_access is not None and auth is not None:
            # Read-only: enter and leave the UoW without committing.
            async with self._uow:
                denied = await self._project_access.check_editable(
                    input.workspace_id, input.project_ids, auth
                )
            if denied is not None:
                return Failure(denied)
```

and add the helper method on the class:

```python
    async def _link_projects(
        self, input: RegisterMoleculeCommand, molecule_id: uuid.UUID
    ) -> list[DomainEvent]:
        """Link the surviving compound to the command's projects inside the
        caller's open unit of work; returns the audit events to dispatch."""
        if not input.project_ids:
            return []
        return list(
            await link_molecules_to_projects(
                self._repo, input.workspace_id, input.project_ids, [molecule_id]
            )
        )
```

- [ ] **Step 5: Link in every success path** —
  1. `_register_disclosed`, DEDUPLICATED branch: replace `events = await self._uow.commit()` with
     ```python
                link_events = await self._link_projects(input, existing_by_inchi.id)
                events = [*await self._uow.commit(), *link_events]
     ```
  2. `_register_disclosed`, REGISTERED branch: same with `mol.id`.
  3. `_register_disclosed`, delegated disclosure: after computing `action` and before `return Success(...)`:
     ```python
            surviving_id = (
                d_outcome.merged_into_molecule_id
                if d_outcome.was_merged and d_outcome.merged_into_molecule_id
                else delegate_to_disclosure.id
            )
            if input.project_ids:
                # The disclosure service committed on its own UoW; link in a
                # short one of ours.
                async with self._uow:
                    link_events = await self._link_projects(input, surviving_id)
                    await self._uow.commit()
                await self._dispatcher.dispatch_all(link_events)
     ```
  4. `_register_undisclosed`, matched branch: before `events = await self._uow.commit()` insert `link_events = await self._link_projects(input, matched_molecule.id)` and make it `events = [*await self._uow.commit(), *link_events]`.
  5. `_register_undisclosed`, new-molecule branch: same with `mol.id`.

  A CONFLICT forecast returns `Failure` before any of these, so nothing is linked.

- [ ] **Step 6: DI** — in `_register_molecule` (`infrastructure/di/_chemical_registration.py`) pass:

```python
            project_access=ProjectAccess(
                SQLAlchemyProjectRepository(uow), SQLAlchemyProjectMemberRepository(uow)
            ),
```

with imports `ProjectAccess` (application) and the two SQLAlchemy research-organization repositories (copy the import lines from `infrastructure/di/_research_organization.py`).

- [ ] **Step 7: Route** — `RegisterMoleculeBody` in `interface/routes/molecules.py` gets `project_ids: list[uuid.UUID] = []`; the `register_molecule` route passes `project_ids=body.project_ids` into `RegisterMoleculeCommand(...)`.

- [ ] **Step 8: Run the tests**

Run: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_molecules_register.py tests/api/test_molecules.py tests/unit/application/chemical_registration -q -p no:cacheprovider`
Expected: new tests PASS; the only failures are the two pre-existing `TestMoleculeTestCounts` ones (`docs/backlog/test-molecules-api-drift.md`)

- [ ] **Step 9: Commit**

```bash
uv run ruff check src tests/api/test_molecules_register.py && uv run ruff format src tests/api/test_molecules_register.py
git commit -m "feat(registration): register a compound straight into projects

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/application/chemical_registration/register_molecule.py backend/src/cellar/infrastructure/di/_chemical_registration.py backend/src/cellar/interface/routes/molecules.py backend/tests/api/test_molecules_register.py
```

---

### Task 5: Project choice at bulk registration

**Files:**
- Modify: `backend/src/cellar/interface/routes/bulk_registration.py:146-171`
- Modify: `backend/src/cellar/application/chemical_registration/start_bulk_registration.py`
- Modify: `backend/src/cellar/application/chemical_registration/bulk_registration_orchestrator.py:11-25`
- Modify: `backend/src/cellar/infrastructure/temporal/orchestrators/bulk_registration.py:43-52`
- Modify: `backend/src/cellar/infrastructure/temporal/workflows/bulk_registration.py:36-60,163-172,228-250`
- Modify: `backend/src/cellar/infrastructure/temporal/activities/dtos.py:40-48`
- Modify: `backend/src/cellar/infrastructure/temporal/activities/registration.py:152-166`
- Modify: `backend/src/cellar/application/chemical_registration/bulk_registration_service.py` (command, `_process_items`)
- Modify: `backend/src/cellar/infrastructure/di/_chemical_registration.py:532-539`
- Test: `backend/tests/unit/infrastructure/temporal/test_registration_activity_policy.py`
- Test: `backend/tests/unit/infrastructure/temporal/test_bulk_registration_workflow_input.py` (new)
- Test: `backend/tests/api/test_bulk_registration_projects.py` (new)

**Interfaces:**
- Consumes: `RegisterMoleculeCommand.project_ids` (Task 4); `ProjectAccess` (Task 1).
- Produces: `StartBulkRegistrationFromFileCommand.project_ids`, `StartBulkRegistrationRequest.project_ids` (`list[uuid.UUID]`); `BulkRegistrationWorkflowInput.project_ids`, `ChunkInput.project_ids` (`list[str]`, Temporal-serializable); `StartBulkRegistrationCommand.project_ids` (sync); module function `_continue_input(input, *, bulk_reg_id, progress, remaining_chunks) -> BulkRegistrationWorkflowInput` in the workflow module.

- [ ] **Step 1: Failing test — chunk activity forwards projects** — append to `test_registration_activity_policy.py`:

```python
@pytest.mark.asyncio
async def test_chunk_forwards_project_ids_to_registration():
    """The chunk turns ChunkInput.project_ids into RegisterMoleculeCommand.project_ids."""
    project_id = uuid.uuid4()
    outcome = _make_outcome(is_new=True, action=RegistrationAction.REGISTERED)
    activity_instance = RegistrationActivities(
        session_factory=AsyncMock(),
        dispatcher=AsyncMock(),
        structure_processor=AsyncMock(),
        side_effect_registry=MagicMock(),
        settings_repo_factory=_make_settings_repo_factory(create_batch_on_duplicate=False),
    )
    chunk_input = _make_chunk_input()
    chunk_input.project_ids = [str(project_id)]
    captured: list = []
    original = _run_process_chunk_simple

    with patch.object(
        registration_module,
        "_create_batch",
        AsyncMock(return_value=(BATCH_ID, "CVB-0001", False)),
    ):
        await original(activity_instance, chunk_input, outcome=outcome, commands=captured)

    assert captured[0].project_ids == [project_id]
```

and give `_run_process_chunk_simple` an optional `commands: list | None = None` parameter that, when given, records every command: change `mock_register_uc = AsyncMock(return_value=Success(outcome))` to

```python
    async def _register(cmd, *args, **kwargs):
        if commands is not None:
            commands.append(cmd)
        return Success(outcome)

    mock_register_uc = AsyncMock(side_effect=_register)
```

- [ ] **Step 2: Failing test — continue-as-new keeps every option** — create `backend/tests/unit/infrastructure/temporal/test_bulk_registration_workflow_input.py`:

```python
"""continue_as_new must carry every non-progress field of the input; a field
listed by hand there is silently dropped the day someone adds a new option."""

from __future__ import annotations

from cellar.infrastructure.temporal.workflows.bulk_registration import (
    BulkRegistrationProgress,
    BulkRegistrationWorkflowInput,
    _continue_input,
)


def test_continue_input_keeps_options_and_takes_progress() -> None:
    first = BulkRegistrationWorkflowInput(
        workspace_id="ws",
        originating_org_id="org",
        submitted_by="u",
        source_file="f.csv",
        file_format="csv",
        storage_path="/tmp/f.csv",
        filename="f.csv",
        create_batch_on_duplicate=True,
        project_ids=["p-1", "p-2"],
    )
    progress = BulkRegistrationProgress(total_count=10, registered_count=4, chunks_processed=2)

    nxt = _continue_input(first, bulk_reg_id="br", progress=progress, remaining_chunks=[[{"row_index": 9}]])

    assert nxt.project_ids == ["p-1", "p-2"]
    assert nxt.create_batch_on_duplicate is True
    assert nxt.resume_bulk_reg_id == "br"
    assert nxt.resume_chunk_index == 2
    assert nxt.resume_registered == 4
    assert nxt.resume_chunks == [[{"row_index": 9}]]
```

(check the `BulkRegistrationProgress` field names at `workflows/bulk_registration.py:62-93` and adjust the constructor kwargs if they differ.)

- [ ] **Step 3: Failing API test — sync path links rows** — create `backend/tests/api/test_bulk_registration_projects.py`:

```python
"""Bulk registration with a project choice (sync path: TEMPORAL_DISABLED in tests)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def test_bulk_upload_links_every_row_to_the_projects(client: AsyncClient) -> None:
    org = (
        await client.post(
            "/api/v1/organizations",
            json={"name": f"BulkRegOrg-{uuid.uuid4().hex[:6]}", "org_type": "internal"},
        )
    ).json()["id"]
    existing = await client.post(
        "/api/v1/molecules",
        json={"name": "AlreadyHere", "smiles": "CCCCCCCCCCCCCCCCCCN", "originating_org_id": org},
    )
    proj = (await client.post("/api/v1/projects", json={"name": "Bulk Reg P"})).json()["id"]
    csv = b"name,smiles\nBulkNew1,CCCCCCCCCCCCCCCCCCCN\nBulkDup,CCCCCCCCCCCCCCCCCCN\n"

    resp = await client.post(
        "/api/v1/bulk-registrations",
        files={"file": ("rows.csv", csv, "text/csv")},
        data={"originating_org_id": org, "file_format": "csv", "project_ids": [proj]},
    )
    assert resp.status_code == 200, resp.text  # sync path (TEMPORAL_DISABLED in API tests)
    items = resp.json()["items"]
    assert all(i["success"] for i in items), items

    stats = await client.get("/api/v1/projects/stats", params={"project_ids": [proj]})
    assert stats.json()[proj]["molecule_count"] == 2  # new row + the deduplicated compound
    linked = await client.get(f"/api/v1/molecules/{existing.json()['molecule']['id']}/projects")
    assert proj in set(linked.json())


async def test_bulk_upload_with_archived_project_starts_nothing(client: AsyncClient) -> None:
    org = (
        await client.post(
            "/api/v1/organizations",
            json={"name": f"BulkRegOrg-{uuid.uuid4().hex[:6]}", "org_type": "internal"},
        )
    ).json()["id"]
    proj = (await client.post("/api/v1/projects", json={"name": "Archived Bulk P"})).json()["id"]
    assert (await client.post(f"/api/v1/projects/{proj}/archive")).status_code == 200

    resp = await client.post(
        "/api/v1/bulk-registrations",
        files={"file": ("rows.csv", b"name,smiles\nNope,CCCCCCCCCCCCCCCCCCCCN\n", "text/csv")},
        data={"originating_org_id": org, "file_format": "csv", "project_ids": [proj]},
    )
    assert resp.status_code == 422
```

- [ ] **Step 4: Run to verify the three fail**

Run: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/unit/infrastructure/temporal tests/api/test_bulk_registration_projects.py -q -p no:cacheprovider`
Expected: FAIL (`ChunkInput` has no `project_ids`; `_continue_input` missing; molecule_count 0 / archived upload returns 200)

- [ ] **Step 5: DTOs and request objects** —
  - `activities/dtos.py` `ChunkInput`: add `project_ids: list[str] = field(default_factory=list)` after `create_batch_on_duplicate`.
  - `workflows/bulk_registration.py` `BulkRegistrationWorkflowInput`: add `project_ids: list[str] = field(default_factory=list)` after `create_batch_on_duplicate`.
  - `bulk_registration_orchestrator.py` `StartBulkRegistrationRequest`: add `project_ids: list[uuid.UUID] = field(default_factory=list)` (import `field`).
  - `start_bulk_registration.py` `StartBulkRegistrationFromFileCommand`: add `project_ids: list[uuid.UUID] = field(default_factory=list)` (import `field`).
  - `bulk_registration_service.py` `StartBulkRegistrationCommand`: add `project_ids: list[uuid.UUID] = field(default_factory=list)`.

- [ ] **Step 6: Workflow** — in `workflows/bulk_registration.py`:
  - add `import dataclasses` to the workflow-safe imports block;
  - pass `project_ids=input.project_ids` into the `ChunkInput(...)` at line ~165;
  - add the module-level function and use it for `continue_as_new`:

```python
def _continue_input(
    input: BulkRegistrationWorkflowInput,
    *,
    bulk_reg_id: str,
    progress: BulkRegistrationProgress,
    remaining_chunks: list[list[dict]],
) -> BulkRegistrationWorkflowInput:
    """Next run's input: every option of this run (``dataclasses.replace``, so a
    new option can't be forgotten here) plus the progress to resume from."""
    return dataclasses.replace(
        input,
        resume_bulk_reg_id=bulk_reg_id,
        resume_chunk_index=progress.chunks_processed,
        resume_total_count=progress.total_count,
        resume_registered=progress.registered_count,
        resume_duplicate=progress.duplicate_count,
        resume_error=progress.error_count,
        resume_disclosed=progress.disclosed_count,
        resume_merge_candidate=progress.merge_candidate_count,
        resume_conflict=progress.conflict_count,
        resume_merge_candidates_list=progress.merge_candidates,
        resume_chunks=remaining_chunks,
    )
```

  and replace the `workflow.continue_as_new(BulkRegistrationWorkflowInput(...))` call with

```python
                workflow.continue_as_new(
                    _continue_input(
                        input,
                        bulk_reg_id=bulk_reg_id,
                        progress=self._progress,
                        remaining_chunks=chunks[i + 1 :],
                    )
                )
```

- [ ] **Step 7: Orchestrator, activity, sync service** —
  - `orchestrators/bulk_registration.py` `start`: add `project_ids=[str(p) for p in request.project_ids],` to `BulkRegistrationWorkflowInput(...)`.
  - `activities/registration.py` `process_chunk`: add `project_ids=[uuid.UUID(p) for p in input.project_ids],` to `RegisterMoleculeCommand(...)`.
  - `bulk_registration_service.py`: pass `project_ids=input.project_ids` from `__call__` into `_process_items(...)`, add the `project_ids: list[uuid.UUID]` keyword parameter to `_process_items`, and add `project_ids=project_ids,` to its `RegisterMoleculeCommand(...)`.

- [ ] **Step 8: Access check at upload start** — `StartBulkRegistration`:

```python
    def __init__(
        self,
        orchestrator: BulkRegistrationOrchestrator,
        sync_service: BulkRegistrationService,
        parser: BulkFileParserProtocol,
        uow: UnitOfWork,
        project_access: ProjectAccess,
    ) -> None:
        ...
        self._uow = uow
        self._project_access = project_access
```

  In `__call__`, right after the file-format validation and before building `request`:

```python
        if input.project_ids:
            # Validate once here: the worker registers rows as the system and
            # trusts this list.
            async with self._uow:
                denied = await self._project_access.check_editable(
                    input.workspace_id, input.project_ids, auth
                )
            if denied is not None:
                return Failure(denied)
```

  and pass `project_ids=input.project_ids` into both `StartBulkRegistrationRequest(...)` and `SyncStartBulkRegistrationCommand(...)`. Imports: `UnitOfWork` (`cellar.application.shared.unit_of_work`), `ProjectAccess` (`cellar.application.research_organization.project_links`).

  DI (`_chemical_registration.py:532-539`):

```python
    def _start_bulk_registration(c: Container) -> StartBulkRegistration:
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return StartBulkRegistration(
            orchestrator=c[BulkRegistrationOrchestrator],
            sync_service=c[BulkRegistrationService],
            parser=c[BulkFileParserProtocol],
            uow=uow,
            project_access=ProjectAccess(
                SQLAlchemyProjectRepository(uow), SQLAlchemyProjectMemberRepository(uow)
            ),
        )

    container.define(StartBulkRegistration, _start_bulk_registration)
```

- [ ] **Step 9: Route** — `start_bulk_registration` in `interface/routes/bulk_registration.py`: add parameter `project_ids: list[uuid.UUID] = Form([]),` and pass `project_ids=project_ids` into `StartBulkRegistrationFromFileCommand(...)`.

- [ ] **Step 10: Run the tests**

Run: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/unit/infrastructure/temporal tests/unit/application/chemical_registration tests/api/test_bulk_registration_projects.py -q -p no:cacheprovider`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
uv run ruff check src tests/unit/infrastructure/temporal tests/api/test_bulk_registration_projects.py && uv run ruff format src tests/unit/infrastructure/temporal tests/api/test_bulk_registration_projects.py
git add backend/tests/unit/infrastructure/temporal/test_bulk_registration_workflow_input.py backend/tests/api/test_bulk_registration_projects.py
git commit -m "feat(bulk-registration): one project choice for a whole upload

project_ids rides the bulk path like create_batch_on_duplicate (route ->
command -> Temporal input -> chunk -> RegisterMolecule, and the sync
fallback). continue_as_new now copies the input with dataclasses.replace so
no option can be dropped on restart. Access is checked before the upload
starts.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/interface/routes/bulk_registration.py backend/src/cellar/application/chemical_registration/start_bulk_registration.py backend/src/cellar/application/chemical_registration/bulk_registration_orchestrator.py backend/src/cellar/infrastructure/temporal/orchestrators/bulk_registration.py backend/src/cellar/infrastructure/temporal/workflows/bulk_registration.py backend/src/cellar/infrastructure/temporal/activities/dtos.py backend/src/cellar/infrastructure/temporal/activities/registration.py backend/src/cellar/application/chemical_registration/bulk_registration_service.py backend/src/cellar/infrastructure/di/_chemical_registration.py backend/tests/unit/infrastructure/temporal/test_registration_activity_policy.py backend/tests/unit/infrastructure/temporal/test_bulk_registration_workflow_input.py backend/tests/api/test_bulk_registration_projects.py
```

---

### Task 6: Registration wizard — project picker

**Files:**
- Regenerate: `frontend/src/shared/lib/api/model/` (orval)
- Modify: `frontend/src/features/chemical-registration/types/index.ts:120-130` (alias the generated body)
- Modify: `frontend/src/features/chemical-registration/types/registration-wizard.ts` (`SingleInput`, `BulkInput`)
- Modify: `frontend/src/features/chemical-registration/hooks/use-registration-wizard.ts:27-48` (defaults)
- Modify: `frontend/src/features/chemical-registration/hooks/use-registration-wizard-api.ts:108-140`
- Modify: `frontend/src/features/chemical-registration/components/registration-wizard/step-input.tsx` (single section ~450, bulk section ~630)
- Modify: `frontend/src/features/chemical-registration/components/registration-wizard/step-processing.tsx:103-112,266-271`
- Modify: `frontend/src/features/chemical-registration/components/registration-wizard/step-preview.tsx` (header)
- Modify: `frontend/src/features/chemical-registration/components/registration-wizard/step-summary.tsx` (both summaries)
- Create: `frontend/src/features/chemical-registration/components/registration-wizard/project-names.tsx`
- Test: `frontend/src/features/chemical-registration/hooks/use-registration-wizard-api.test.tsx` (new)

**Interfaces:**
- Consumes: backend `RegisterMoleculeBody.project_ids`, bulk form field `project_ids` (Tasks 4–5); `ProjectFilter({ selectedIds, onChange })` from `@/features/research-organization/components/search/project-filter`; `useProjects()` from `@/features/research-organization/hooks/use-projects`.
- Produces: `SingleInput.projectIds: string[]`, `BulkInput.projectIds: string[]`, `StartBulkRegistrationInput.project_ids?: string[]`, `<ProjectNames ids={string[]} />`.

- [ ] **Step 1: Regenerate the client** (backend running on :8000 with Tasks 4–5)

Run (from `frontend/`): `pnpm generate:api`, then revert version-stamp-only files:

```bash
git diff --name-only src/shared/lib/api | while read f; do f=${f#frontend/}; git diff -U0 -- "$f" | grep -E '^[+-]' | grep -v '^+++\|^---' | grep -qv 'OpenAPI spec version' || git checkout -- "$f"; done
git status --short src/shared/lib/api
```

Expected: only `registerMoleculeBody.ts` (gains `project_ids?: string[]`), the bulk-registration body model and `model/index.ts` / new model files remain changed.

- [ ] **Step 2: Alias the generated body** — replace the hand-written `RegisterMoleculeInput` interface in `types/index.ts` with:

```ts
// Backend DTO — aliased from the orval-generated model (source of truth).
export type RegisterMoleculeInput = import("@/shared/lib/api/model").RegisterMoleculeBody;
```

Run `pnpm exec tsc --noEmit -p .`; Expected: no errors (the generated body has the same fields plus `project_ids`).

- [ ] **Step 3: Write the failing hook test** — create `hooks/use-registration-wizard-api.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const customInstance = vi.fn().mockResolvedValue({ workflow_id: "w-1", status: "pending" });
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (...args: unknown[]) => customInstance(...args),
}));
vi.mock("@/shared/lib/toast", () => ({ showSuccess: vi.fn(), showError: vi.fn() }));

import { useStartBulkRegistration } from "./use-registration-wizard-api";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useStartBulkRegistration", () => {
  it("sends one project_ids form field per chosen project", async () => {
    const { result } = renderHook(() => useStartBulkRegistration(), { wrapper });
    await act(() =>
      result.current.mutateAsync({
        file: new File(["name,smiles\n"], "rows.csv"),
        originating_org_id: "org-1",
        project_ids: ["p-1", "p-2"],
      }),
    );
    const form = customInstance.mock.calls[0][0].data as FormData;
    expect(form.getAll("project_ids")).toEqual(["p-1", "p-2"]);
  });
});
```

Run: `pnpm exec vitest run src/features/chemical-registration/hooks/use-registration-wizard-api.test.tsx`
Expected: FAIL (`project_ids` not in `StartBulkRegistrationInput` / no fields appended)

- [ ] **Step 4: Hook** — in `use-registration-wizard-api.ts`: add `project_ids?: string[];` to `StartBulkRegistrationInput`, destructure `project_ids = []` in `mutationFn`, and after the `create_batch_on_duplicate` append:

```ts
      for (const id of project_ids) formData.append("project_ids", id);
```

Run the test again — Expected: PASS.

- [ ] **Step 5: Wizard state** — `types/registration-wizard.ts`: add `projectIds: string[];` to both `SingleInput` and `BulkInput` (comment: "Projects the registered compounds are added to (optional)."). `use-registration-wizard.ts`: add `projectIds: [],` to `DEFAULT_SINGLE_INPUT` and `DEFAULT_BULK_INPUT`.

- [ ] **Step 6: Picker in step-input** — import `ProjectFilter` from `@/features/research-organization/components/search/project-filter`. After the single-mode Originating Organization block (inside the same `!singleInput.disclosureMode` guard) add:

```tsx
      {!singleInput.disclosureMode && (
        <div className="grid gap-2">
          <Label>Projects <span className="text-xs text-muted-foreground">(optional)</span></Label>
          <ProjectFilter
            selectedIds={singleInput.projectIds}
            onChange={(ids) => updateSingleInput({ projectIds: ids })}
          />
        </div>
      )}
```

and after the bulk Organization selector block:

```tsx
      <div className="grid gap-2">
        <Label>Projects <span className="text-xs text-muted-foreground">(optional)</span></Label>
        <ProjectFilter
          selectedIds={bulkInput.projectIds}
          onChange={(ids) => updateBulkInput({ projectIds: ids })}
        />
        <p className="text-xs text-muted-foreground">
          Every compound in the file — new or already registered — is added to these projects.
        </p>
      </div>
```

- [ ] **Step 7: Payloads** — `step-processing.tsx`: add `project_ids: singleInput.projectIds,` to the single `RegisterMoleculeInput` object and `project_ids: bulkInput.projectIds,` to the `startMutation.mutateAsync({...})` call.

- [ ] **Step 8: Show the choice** — create `components/registration-wizard/project-names.tsx`:

```tsx
"use client";

import { useProjects } from "@/features/research-organization/hooks/use-projects";

/** Comma-separated names of the chosen projects, for wizard summaries. */
export function ProjectNames({ ids }: { ids: string[] }) {
  const { data: projects } = useProjects();
  const byId = new Map((projects ?? []).map((p) => [p.id, p.name]));
  return <>{ids.map((id) => byId.get(id) ?? "…").join(", ")}</>;
}
```

  - `step-preview.tsx`: under the `<h2 …>Preview</h2>` heading, when `bulkInput.projectIds.length > 0`, render
    `<p className="text-sm text-muted-foreground">Will be added to: <ProjectNames ids={bulkInput.projectIds} /></p>` (read `bulkInput` from `useRegistrationWizard((s) => s.bulkInput)` if the component doesn't already).
  - `step-summary.tsx`: in `SingleSummary` add after the Action row
    `{singleInput.projectIds.length > 0 && (<SummaryRow label="Projects"><ProjectNames ids={singleInput.projectIds} /></SummaryRow>)}` (select `singleInput` from the store), and in `BulkSummary` the same with `bulkInput.projectIds` after the Conflicts row.

- [ ] **Step 9: Verify**

Run: `pnpm exec tsc --noEmit -p . && pnpm exec vitest run src/features/chemical-registration && pnpm lint; echo "lint exit $?"`
Expected: no type errors, tests PASS, `lint exit 0`

- [ ] **Step 10: Commit**

```bash
git add frontend/src/features/chemical-registration/hooks/use-registration-wizard-api.test.tsx frontend/src/features/chemical-registration/components/registration-wizard/project-names.tsx
git commit -m "feat(registration-ui): pick projects when registering (single and bulk)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/src/shared/lib/api/model frontend/src/features/chemical-registration
```

(the pathspec `frontend/src/shared/lib/api/model` only carries the real DTO changes left after Step 1's revert.)

---

### Task 7: Whole-branch verification

- [ ] **Step 1: Full backend suite**

Run: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/unit tests/api tests/integration -q -p no:cacheprovider`
Expected: only the 3 known pre-existing failures (`test_pdf_renderer`, two `TestMoleculeTestCounts`).

- [ ] **Step 2: Full frontend suite** — `pnpm exec vitest run` and `pnpm lint` (exit 0).

- [ ] **Step 3: Restart the worker and try it in the app** — `make dev-worker`; in the browser register one compound with a project, upload a 2-row CSV with a project, then open `/search`, pick that project chip and confirm the count matches.
