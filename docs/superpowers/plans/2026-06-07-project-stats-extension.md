# Project Stats Extension (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing batch project scope-stats endpoint to also return `campaign_count`, `last_activity_at`, `member_count`, and `member_ids` per project — the data the folder dashboard cards need.

**Architecture:** One additive change to the `ProjectScopeStats` value object, the `get_scope_stats` repository query (two extra batched sub-queries), and the `ProjectScopeStatsResponse` API schema. No new aggregate, no new endpoint. `last_activity_at` = the later of `project.updated_at` and the newest campaign's `updated_at`, computed in Python from a per-project `max(campaign.updated_at)`.

**Tech Stack:** Python 3.13 / SQLAlchemy 2.0 async / FastAPI / orval.

**Spec:** `docs/superpowers/specs/2026-06-07-projects-folder-dashboard-design.md` (Phase 2).

**Verified facts:** VO at `backend/src/cellar/domain/research_organization/project_scope_stats.py` (frozen dataclass, fields `molecule_count/protocol_count/run_count`). Query at `project_repository.py::get_scope_stats` (already batches over `project_ids`, workspace-scoped). `CampaignModel` has `project_id`, `workspace_id`, `updated_at` (via EntityModelMixin). `ProjectMemberModel` has `project_id`, `user_id`, `created_at`. API schema + endpoint in `interface/routes/projects.py`. FE consumer `use-project-scope-stats.ts` just aliases the generated `ProjectScopeStatsResponse`, so it picks up new fields on regen.

---

## Task 1: Extend the domain VO and repository query

**Files:**
- Modify: `backend/src/cellar/domain/research_organization/project_scope_stats.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/project_repository.py`
- Test: `backend/tests/integration/persistence/research_organization/test_project_scope_stats.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/persistence/research_organization/test_project_scope_stats.py`:

```python
"""Integration test for the extended project scope-stats query."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignModel,
    ProjectMemberModel,
    ProjectModel,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.project_repository import (
    SQLAlchemyProjectRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

pytestmark = pytest.mark.integration


async def test_scope_stats_includes_campaigns_members_activity(session_factory) -> None:
    ws = uuid.uuid4()
    project_id = uuid.uuid4()
    user1, user2 = uuid.uuid4(), uuid.uuid4()
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 6, 1, tzinfo=UTC)

    async with session_factory() as s:
        s.add(
            ProjectModel(
                id=project_id,
                workspace_id=ws,
                name="P",
                status="active",
                created_by=user1,
                updated_at=older,
            )
        )
        s.add(
            CampaignModel(
                id=uuid.uuid4(),
                workspace_id=ws,
                project_id=project_id,
                name="C1",
                status="draft",
                created_by=user1,
                updated_at=newer,
            )
        )
        s.add(
            CampaignModel(
                id=uuid.uuid4(),
                workspace_id=ws,
                project_id=project_id,
                name="C2",
                status="closed",
                created_by=user1,
                updated_at=older,
            )
        )
        s.add(ProjectMemberModel(project_id=project_id, user_id=user1, role="manager"))
        s.add(ProjectMemberModel(project_id=project_id, user_id=user2, role="viewer"))
        await s.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyProjectRepository(uow)
        stats = await repo.get_scope_stats(ws, [project_id])

    s1 = stats[project_id]
    assert s1.campaign_count == 2
    # greatest(project.updated_at=older, max(campaign.updated_at)=newer) == newer
    assert s1.last_activity_at == newer
    assert s1.member_count == 2
    assert set(s1.member_ids) == {user1, user2}


async def test_scope_stats_no_campaigns_uses_project_updated_at(session_factory) -> None:
    ws = uuid.uuid4()
    project_id = uuid.uuid4()
    proj_updated = datetime(2026, 3, 3, tzinfo=UTC)

    async with session_factory() as s:
        s.add(
            ProjectModel(
                id=project_id,
                workspace_id=ws,
                name="Quiet",
                status="active",
                created_by=uuid.uuid4(),
                updated_at=proj_updated,
            )
        )
        await s.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyProjectRepository(uow)
        stats = await repo.get_scope_stats(ws, [project_id])

    s1 = stats[project_id]
    assert s1.campaign_count == 0
    assert s1.last_activity_at == proj_updated
    assert s1.member_count == 0
    assert s1.member_ids == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/persistence/research_organization/test_project_scope_stats.py -v`
Expected: FAIL — `AttributeError: 'ProjectScopeStats' object has no attribute 'campaign_count'`.

- [ ] **Step 3: Extend the value object**

Replace the body of `backend/src/cellar/domain/research_organization/project_scope_stats.py`:

```python
"""ProjectScopeStats — aggregate counts describing the size of a project's scope."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class ProjectScopeStats:
    molecule_count: int
    protocol_count: int
    run_count: int
    campaign_count: int = 0
    last_activity_at: datetime | None = None
    member_count: int = 0
    member_ids: tuple[uuid.UUID, ...] = field(default_factory=tuple)
```

- [ ] **Step 4: Extend the repository query**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/project_repository.py`:

First ensure `CampaignModel` and `ProjectMemberModel` are imported from the models module (add them to the existing import of `ProjectModel` / `molecule_projects` / `protocol_projects`):

```python
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignModel,
    ProjectMemberModel,
    ProjectModel,
    molecule_projects,
)
```

Then replace the `get_scope_stats` method body with this (keeps the existing molecule/protocol/run logic, adds campaigns + members + activity):

```python
    async def get_scope_stats(
        self, workspace_id: uuid.UUID, project_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ProjectScopeStats]:
        if not project_ids:
            return {}

        # Restrict to project_ids that actually live in this workspace —
        # defense-in-depth so a forged ID can't surface a count from another
        # workspace. Also grab each project's own updated_at for last-activity.
        scoped_stmt = select(ProjectModel.id, ProjectModel.updated_at).where(
            ProjectModel.workspace_id == workspace_id,
            ProjectModel.id.in_(project_ids),
        )
        scoped_rows = (await self._session.execute(scoped_stmt)).all()
        if not scoped_rows:
            return {}
        project_updated = {row[0]: row[1] for row in scoped_rows}
        scoped_ids_list = list(project_updated.keys())

        mol_stmt = (
            select(
                molecule_projects.c.project_id,
                func.count(molecule_projects.c.molecule_id),
            )
            .where(molecule_projects.c.project_id.in_(scoped_ids_list))
            .group_by(molecule_projects.c.project_id)
        )
        prot_stmt = (
            select(
                protocol_projects.c.project_id,
                func.count(protocol_projects.c.protocol_id),
            )
            .where(protocol_projects.c.project_id.in_(scoped_ids_list))
            .group_by(protocol_projects.c.project_id)
        )
        run_stmt = (
            select(
                protocol_projects.c.project_id,
                func.count(RunModel.id),
            )
            .join(RunModel, RunModel.protocol_id == protocol_projects.c.protocol_id)
            .where(protocol_projects.c.project_id.in_(scoped_ids_list))
            .group_by(protocol_projects.c.project_id)
        )
        camp_stmt = (
            select(
                CampaignModel.project_id,
                func.count(CampaignModel.id),
                func.max(CampaignModel.updated_at),
            )
            .where(
                CampaignModel.workspace_id == workspace_id,
                CampaignModel.project_id.in_(scoped_ids_list),
            )
            .group_by(CampaignModel.project_id)
        )
        member_stmt = (
            select(ProjectMemberModel.project_id, ProjectMemberModel.user_id)
            .where(ProjectMemberModel.project_id.in_(scoped_ids_list))
            .order_by(ProjectMemberModel.created_at)
        )

        mol_counts = dict((await self._session.execute(mol_stmt)).all())
        prot_counts = dict((await self._session.execute(prot_stmt)).all())
        run_counts = dict((await self._session.execute(run_stmt)).all())

        camp_rows = (await self._session.execute(camp_stmt)).all()
        camp_counts = {r[0]: r[1] for r in camp_rows}
        camp_last = {r[0]: r[2] for r in camp_rows}

        members_by_project: dict[uuid.UUID, list[uuid.UUID]] = {}
        for pid, uid in (await self._session.execute(member_stmt)).all():
            members_by_project.setdefault(pid, []).append(uid)

        result: dict[uuid.UUID, ProjectScopeStats] = {}
        for pid in scoped_ids_list:
            last_activity = project_updated[pid]
            last_campaign = camp_last.get(pid)
            if last_campaign is not None and last_campaign > last_activity:
                last_activity = last_campaign
            member_ids = members_by_project.get(pid, [])
            result[pid] = ProjectScopeStats(
                molecule_count=mol_counts.get(pid, 0),
                protocol_count=prot_counts.get(pid, 0),
                run_count=run_counts.get(pid, 0),
                campaign_count=camp_counts.get(pid, 0),
                last_activity_at=last_activity,
                member_count=len(member_ids),
                member_ids=tuple(member_ids[:5]),
            )
        return result
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/integration/persistence/research_organization/test_project_scope_stats.py -v`
Expected: PASS (2 passed). Requires Docker.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/domain/research_organization/project_scope_stats.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/project_repository.py \
        backend/tests/integration/persistence/research_organization/test_project_scope_stats.py
git commit -m "feat(projects): scope stats add campaign_count, last_activity, members"
```

---

## Task 2: Extend the API response + regenerate types

**Files:**
- Modify: `backend/src/cellar/interface/routes/projects.py`
- Test: `backend/tests/api/test_projects.py` (add a case)
- Regenerate: `frontend/src/shared/lib/api/model/projectScopeStatsResponse.ts` (orval)

- [ ] **Step 1: Write the failing API test**

Add to `backend/tests/api/test_projects.py`, inside the existing `TestProjectScopeStats` class:

```python
    async def test_stats_response_includes_new_fields(self, client: AsyncClient) -> None:
        create = await client.post("/api/v1/projects", json={"name": "Stats v2"})
        pid = create.json()["id"]
        resp = await client.get("/api/v1/projects/stats", params={"project_ids": pid})
        assert resp.status_code == 200
        body = resp.json()[pid]
        assert body["campaign_count"] == 0
        assert "last_activity_at" in body
        assert "member_count" in body
        assert isinstance(body["member_ids"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest "tests/api/test_projects.py::TestProjectScopeStats::test_stats_response_includes_new_fields" -v`
Expected: FAIL — `KeyError: 'campaign_count'` (response model omits it).

- [ ] **Step 3: Extend the API response model + endpoint mapping**

In `backend/src/cellar/interface/routes/projects.py`:

Ensure `datetime` is imported at the top:

```python
from datetime import datetime
```

Replace the `ProjectScopeStatsResponse` model with:

```python
class ProjectScopeStatsResponse(BaseModel):
    molecule_count: int
    protocol_count: int
    run_count: int
    campaign_count: int
    last_activity_at: datetime | None = None
    member_count: int
    member_ids: list[uuid.UUID]
```

And update the dict-comprehension inside `get_project_scope_stats` to map the new fields:

```python
    return {
        pid: ProjectScopeStatsResponse(
            molecule_count=s.molecule_count,
            protocol_count=s.protocol_count,
            run_count=s.run_count,
            campaign_count=s.campaign_count,
            last_activity_at=s.last_activity_at,
            member_count=s.member_count,
            member_ids=list(s.member_ids),
        )
        for pid, s in stats.items()
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/api/test_projects.py -v`
Expected: PASS (existing TestProjectScopeStats cases + the new one). Requires Docker.

- [ ] **Step 5: Regenerate orval types**

With the backend running on `:8000`:

Run: `cd frontend && pnpm generate:api`
Expected: `frontend/src/shared/lib/api/model/projectScopeStatsResponse.ts` now includes `campaign_count`, `last_activity_at`, `member_count`, `member_ids`. The FE consumer `use-project-scope-stats.ts` aliases this type, so no hook change is needed. Review the diff (additive).

- [ ] **Step 6: Verify FE still type-checks + commit**

Run: `cd frontend && pnpm lint`
Expected: exit 0.

```bash
git add backend/src/cellar/interface/routes/projects.py \
        backend/tests/api/test_projects.py \
        frontend/src/shared/lib/api/model
git commit -m "feat(projects): expose extended scope stats in API + regenerate types"
```

---

## Phase 2 Done — verification

- [ ] `cd backend && uv run pytest tests/integration/persistence/research_organization/test_project_scope_stats.py tests/api/test_projects.py -v` — green
- [ ] `cd frontend && pnpm lint` — exit 0
- [ ] Confirm `ProjectScopeStatsResponse` in `model/` carries the four new fields.
- [ ] Update the GitHub project board (Phase 2 stats extension done).
