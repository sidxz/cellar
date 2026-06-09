# Campaign Targets Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show and filter campaigns by target, where a campaign's targets are the distinct union of `run_targets` over the runs its measurements reference — computed at read time, never stored.

**Architecture:** Mirror the protocol "effective targets" pattern (`protocol_repository.find_effective_targets`). A batched repository read returns `dict[campaign_id → list[TargetRef]]` for chips; a SQL `EXISTS`/`HAVING` subquery filters campaigns by target before pagination, mirroring `tag_filter_subquery`. No stored column, no domain events. `targets: list[TargetRefResponse]` is added to the shared `CampaignResponse` (a derived, not-stored field like the existing `compound_sources`).

**Tech Stack:** Python 3.13 / SQLAlchemy 2.0 async / FastAPI / dry-python returns · Next.js / React 19 / TanStack Query v5 / orval.

**Spec:** `docs/superpowers/specs/2026-06-07-campaign-targets-projection-design.md`.

**Verified facts:**
- `run_targets` (M:N, source of truth) + `TargetModel` live in `screening_assay/models.py`; `TargetRef` domain VO in `cellar.domain.screening_assay.target`; `TargetRefResponse` (id/name/target_type, `from_ref`) in `interface/routes/_target_refs.py`.
- Cross-context import research_organization → screening_assay is already established (`project_repository.py`, `campaign_scientist_reader.py`, many `application/research_organization/*`). The only `independence` import-linter contract is for `chemical_registration`.
- Campaign domain: `Campaign.results: list[CampaignResult]`; `CampaignResult.measurements: list[CampaignMeasurement]`; `CampaignMeasurement.source_run_id: uuid|None` (campaign_measurement.py:32) + `contributing_run_ids: list[uuid]|None` (campaign_measurement.py:42). `find_by_project`/`find_by_workspace` eager-load results+measurements, so run ids are in memory.
- Persistence models: `CampaignResultModel(campaign_id, id)`, `CampaignMeasurementModel(result_id, source_run_id, contributing_run_ids: PG ARRAY(UUID))` in `research_organization/models.py`.
- `tag_filter_subquery(link_model, entity_id_attr, ids, *, match_all)` in `tagging/tag_filter.py`.
- `ListCampaigns` use case returns `Result[PageResult[Campaign], DomainError]`; its ONLY caller is the `list_campaigns` route. `GetCampaign` returns an output with `.campaign` + `.scientist_by_run_id`.
- FE: list table `features/screen-campaign/components/campaign-list.tsx`; hook `features/screen-campaign/hooks/use-campaigns.ts`; detail header `features/screen-campaign/components/sections/header-strip.tsx`; picker `add-from-campaign-dialog.tsx`; `TargetChips` in `features/screening-assay/components/target-chips.tsx` (props `{ targets: TargetRef[]|null, max=3 }`); `useTargets` (= list hook) in `features/screening-assay/hooks/use-targets.ts`; `TagFilter` in `features/tagging/components/tag-filter.tsx`.

---

## Task 1: Backend — campaign targets read projection (chips data)

**Files:**
- Modify: `backend/src/cellar/domain/research_organization/repository.py` (add method to the `CampaignRepository` protocol)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/campaign_repository.py`
- Test: `backend/tests/integration/persistence/research_organization/test_campaign_targets_projection.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/persistence/research_organization/test_campaign_targets_projection.py`:

```python
"""Integration test: campaign targets read projection (union of run targets)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import insert

from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (
    SQLAlchemyCampaignRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignMeasurementModel,
    CampaignModel,
    CampaignResultModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ProtocolModel,
    RunModel,
    TargetModel,
    run_targets,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

pytestmark = pytest.mark.integration


async def _seed_campaign_with_targets(session, ws, project_id):
    """One campaign, one result, two measurements referencing two runs.
    run A -> {InhA, HepG2}; run B (via contributing_run_ids) -> {InhA}.
    Expected distinct campaign targets: {InhA, HepG2}.
    """
    protocol_id = uuid.uuid4()
    run_a, run_b = uuid.uuid4(), uuid.uuid4()
    inha, hepg2 = uuid.uuid4(), uuid.uuid4()
    campaign_id, result_id = uuid.uuid4(), uuid.uuid4()

    session.add(ProtocolModel(id=protocol_id, workspace_id=ws, name="P", created_by=uuid.uuid4()))
    for rid in (run_a, run_b):
        session.add(RunModel(id=rid, workspace_id=ws, protocol_id=protocol_id, name="R", created_by=uuid.uuid4()))
    session.add(TargetModel(id=inha, workspace_id=ws, name="InhA", target_type="protein"))
    session.add(TargetModel(id=hepg2, workspace_id=ws, name="HepG2", target_type="cell_line"))
    session.add(CampaignModel(id=campaign_id, workspace_id=ws, project_id=project_id, name="C", created_by=uuid.uuid4()))
    await session.flush()
    await session.execute(insert(run_targets).values([
        {"run_id": run_a, "target_id": inha},
        {"run_id": run_a, "target_id": hepg2},
        {"run_id": run_b, "target_id": inha},
    ]))
    session.add(CampaignResultModel(id=result_id, campaign_id=campaign_id, molecule_id=uuid.uuid4()))
    await session.flush()
    session.add(CampaignMeasurementModel(
        id=uuid.uuid4(), result_id=result_id, channel_id=uuid.uuid4(), source_run_id=run_a,
    ))
    session.add(CampaignMeasurementModel(
        id=uuid.uuid4(), result_id=result_id, channel_id=uuid.uuid4(),
        source_run_id=None, contributing_run_ids=[run_b],
    ))
    await session.commit()
    return campaign_id, {inha, hepg2}, {"InhA", "HepG2"}


async def test_project_targets_unions_and_dedups(session_factory) -> None:
    ws, project_id = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as s:
        campaign_id, _ids, names = await _seed_campaign_with_targets(s, ws, project_id)

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyCampaignRepository(uow)
        campaigns = await repo.find_by_project(ws, project_id)
        result = await repo.project_targets(ws, campaigns)

    targets = result[campaign_id]
    assert {t.name for t in targets} == names
    assert len(targets) == 2  # InhA deduped across the two runs
    assert [t.name for t in targets] == sorted(t.name for t in targets)  # sorted by name


async def test_project_targets_empty_campaign_returns_empty(session_factory) -> None:
    ws, project_id = uuid.uuid4(), uuid.uuid4()
    campaign_id = uuid.uuid4()
    async with session_factory() as s:
        s.add(CampaignModel(id=campaign_id, workspace_id=ws, project_id=project_id, name="Quiet", created_by=uuid.uuid4()))
        await s.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyCampaignRepository(uow)
        campaigns = await repo.find_by_project(ws, project_id)
        result = await repo.project_targets(ws, campaigns)

    assert result.get(campaign_id, []) == []
```

> Before implementing, open `research_organization/models.py` and confirm the exact required (non-null, no-default) columns on `ProtocolModel`, `RunModel`, `CampaignResultModel`, `CampaignMeasurementModel`. Adjust the seed kwargs to satisfy real NOT NULL constraints (e.g. a measurement may require `value`/`readout_definition_id`; a result may require extra fields). Keep the assertions identical. If `ProtocolModel`/`RunModel` need more required fields, add them — the point is two runs with the given `run_targets`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/persistence/research_organization/test_campaign_targets_projection.py -v`
Expected: FAIL — `AttributeError: 'SQLAlchemyCampaignRepository' object has no attribute 'project_targets'`.

- [ ] **Step 3: Add the method to the repository protocol**

In `backend/src/cellar/domain/research_organization/repository.py`, add to the `CampaignRepository` protocol (place near the other read methods like `find_by_project`). Add the import at the top of the file:

```python
from cellar.domain.screening_assay.target import TargetRef
```

Method signature in the `CampaignRepository` protocol:

```python
    async def project_targets(
        self, workspace_id: uuid.UUID, campaigns: list[Campaign]
    ) -> dict[uuid.UUID, list[TargetRef]]:
        """Distinct targets per campaign, unioned from its runs' run_targets.

        Read-time projection (never stored). Returns {} entries omitted for
        campaigns with no measured targets.
        """
        ...
```

- [ ] **Step 4: Implement the projection in the SQLAlchemy repository**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/campaign_repository.py`:

Add imports (top of file, alongside the existing ones):

```python
from sqlalchemy import select
from cellar.domain.screening_assay.target import TargetRef
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    TargetModel,
    run_targets,
)
```

Add the method on `SQLAlchemyCampaignRepository`:

```python
    async def project_targets(
        self, workspace_id: uuid.UUID, campaigns: list[Campaign]
    ) -> dict[uuid.UUID, list[TargetRef]]:
        # Collect every run id referenced by each campaign's measurements
        # (source_run_id ∪ contributing_run_ids) — the aggregate is already loaded.
        run_ids_by_campaign: dict[uuid.UUID, set[uuid.UUID]] = {}
        all_run_ids: set[uuid.UUID] = set()
        for c in campaigns:
            run_ids: set[uuid.UUID] = set()
            for result in c.results:
                for m in result.measurements:
                    if m.source_run_id is not None:
                        run_ids.add(m.source_run_id)
                    for rid in m.contributing_run_ids or ():
                        run_ids.add(rid)
            if run_ids:
                run_ids_by_campaign[c.id] = run_ids
                all_run_ids |= run_ids

        if not all_run_ids:
            return {}

        # One batched query: run_id -> target rows (workspace-scoped).
        rows = (
            await self._session.execute(
                select(run_targets.c.run_id, TargetModel)
                .select_from(
                    run_targets.join(TargetModel, run_targets.c.target_id == TargetModel.id)
                )
                .where(
                    TargetModel.workspace_id == workspace_id,
                    run_targets.c.run_id.in_(all_run_ids),
                )
            )
        ).all()
        targets_by_run: dict[uuid.UUID, list[TargetModel]] = {}
        for run_id, target in rows:
            targets_by_run.setdefault(run_id, []).append(target)

        out: dict[uuid.UUID, list[TargetRef]] = {}
        for campaign_id, run_ids in run_ids_by_campaign.items():
            seen: dict[uuid.UUID, TargetRef] = {}
            for rid in run_ids:
                for t in targets_by_run.get(rid, ()):
                    seen[t.id] = TargetRef(id=t.id, name=t.name, target_type=t.target_type)
            if seen:
                out[campaign_id] = sorted(seen.values(), key=lambda r: r.name.lower())
        return out
```

> Confirm the `TargetRef` constructor signature in `cellar/domain/screening_assay/target.py` (id/name/target_type). If it is a frozen dataclass with those fields, the call above is correct; adapt if names differ.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/integration/persistence/research_organization/test_campaign_targets_projection.py -v`
Expected: PASS (2 passed). Requires Docker.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/domain/research_organization/repository.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/campaign_repository.py \
        backend/tests/integration/persistence/research_organization/test_campaign_targets_projection.py
git commit -m "feat(campaigns): read-time campaign targets projection (run-targets union)" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Backend — target filter subquery + repo params

**Files:**
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/campaign_target_filter.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/campaign_repository.py` (`find_by_project`, `find_by_workspace`)
- Modify: `backend/src/cellar/domain/research_organization/repository.py` (extend the two method signatures on the protocol)
- Test: `backend/tests/integration/persistence/research_organization/test_campaign_target_filter.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/integration/persistence/research_organization/test_campaign_target_filter.py`:

```python
"""Integration test: filtering campaigns by target (any / all)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import insert

from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_repository import (
    SQLAlchemyCampaignRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignMeasurementModel,
    CampaignModel,
    CampaignResultModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ProtocolModel,
    RunModel,
    TargetModel,
    run_targets,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

pytestmark = pytest.mark.integration


async def _campaign_with_run_targets(session, ws, project_id, name, target_ids):
    protocol_id, run_id = uuid.uuid4(), uuid.uuid4()
    campaign_id, result_id = uuid.uuid4(), uuid.uuid4()
    session.add(ProtocolModel(id=protocol_id, workspace_id=ws, name="P", created_by=uuid.uuid4()))
    session.add(RunModel(id=run_id, workspace_id=ws, protocol_id=protocol_id, name="R", created_by=uuid.uuid4()))
    session.add(CampaignModel(id=campaign_id, workspace_id=ws, project_id=project_id, name=name, created_by=uuid.uuid4()))
    await session.flush()
    if target_ids:
        await session.execute(insert(run_targets).values([
            {"run_id": run_id, "target_id": tid} for tid in target_ids
        ]))
    session.add(CampaignResultModel(id=result_id, campaign_id=campaign_id, molecule_id=uuid.uuid4()))
    await session.flush()
    session.add(CampaignMeasurementModel(id=uuid.uuid4(), result_id=result_id, channel_id=uuid.uuid4(), source_run_id=run_id))
    return campaign_id


async def test_filter_any_and_all(session_factory) -> None:
    ws, project_id = uuid.uuid4(), uuid.uuid4()
    inha, dnae1 = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as s:
        s.add(TargetModel(id=inha, workspace_id=ws, name="InhA", target_type="protein"))
        s.add(TargetModel(id=dnae1, workspace_id=ws, name="DnaE1", target_type="protein"))
        c_both = await _campaign_with_run_targets(s, ws, project_id, "Both", [inha, dnae1])
        c_inha = await _campaign_with_run_targets(s, ws, project_id, "InhA only", [inha])
        c_none = await _campaign_with_run_targets(s, ws, project_id, "Untargeted", [])
        await s.commit()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        repo = SQLAlchemyCampaignRepository(uow)
        any_inha = {c.id for c in await repo.find_by_project(ws, project_id, target_ids=[inha], target_logic="any")}
        all_both = {c.id for c in await repo.find_by_project(ws, project_id, target_ids=[inha, dnae1], target_logic="all")}

    assert any_inha == {c_both, c_inha}  # c_none excluded; counter-screen-style EXISTS
    assert all_both == {c_both}          # only the campaign covering BOTH
    assert c_none not in any_inha
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/persistence/research_organization/test_campaign_target_filter.py -v`
Expected: FAIL — `TypeError: find_by_project() got an unexpected keyword argument 'target_ids'`.

- [ ] **Step 3: Create the campaign target filter subquery**

Create `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/campaign_target_filter.py`:

```python
"""Campaign-by-target filter subquery.

Returns a Select of campaign ids whose measurements reference runs that carry
the given targets (``match_all=False`` = any; ``match_all=True`` = all).
A campaign "has" target T if any of its measurements references a run
(``source_run_id`` or a member of ``contributing_run_ids``) that has T in
``run_targets``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.sql import Select

from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignMeasurementModel,
    CampaignResultModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import run_targets


def campaign_target_filter_subquery(target_ids: list[uuid.UUID], *, match_all: bool) -> Select:
    unique_ids = list(dict.fromkeys(target_ids))  # dedup, preserve order
    run_match = or_(
        run_targets.c.run_id == CampaignMeasurementModel.source_run_id,
        run_targets.c.run_id == func.any(CampaignMeasurementModel.contributing_run_ids),
    )
    stmt = (
        select(CampaignResultModel.campaign_id)
        .select_from(
            CampaignResultModel.__table__.join(
                CampaignMeasurementModel,
                CampaignMeasurementModel.result_id == CampaignResultModel.id,
            ).join(run_targets, run_match)
        )
        .where(run_targets.c.target_id.in_(unique_ids))
    )
    if match_all:
        stmt = stmt.group_by(CampaignResultModel.campaign_id).having(
            func.count(distinct(run_targets.c.target_id)) == len(unique_ids)
        )
    else:
        stmt = stmt.distinct()
    return stmt
```

> `func.any(column)` renders `= ANY(contributing_run_ids)` for the PG array column. If `contributing_run_ids` is NULL for a measurement, the `ANY` simply matches nothing (correct). Verify `CampaignResultModel` / `CampaignMeasurementModel` expose `.__table__` and the `result_id` FK name; adapt the join if the column differs.

- [ ] **Step 4: Wire the filter into `find_by_project` and `find_by_workspace`**

In `campaign_repository.py`, add the import:

```python
from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_target_filter import (
    campaign_target_filter_subquery,
)
```

Extend `find_by_project` — add `target_ids` / `target_logic` params and a filter clause mirroring the tag clause (insert the new block right after the existing `if tags:` block, before `stmt = stmt.order_by(...)`):

```python
    async def find_by_project(
        self,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
        tags: list[uuid.UUID] | None = None,
        tag_logic: str = "any",
        target_ids: list[uuid.UUID] | None = None,
        target_logic: str = "any",
    ) -> list[Campaign]:
        stmt = select(CampaignModel).where(
            CampaignModel.workspace_id == workspace_id,
            CampaignModel.project_id == project_id,
        )
        if tags:
            stmt = stmt.where(
                CampaignModel.id.in_(
                    tag_filter_subquery(
                        CampaignTagLinkModel, "campaign_id", tags, match_all=tag_logic == "all"
                    )
                )
            )
        if target_ids:
            stmt = stmt.where(
                CampaignModel.id.in_(
                    campaign_target_filter_subquery(target_ids, match_all=target_logic == "all")
                )
            )
        stmt = stmt.order_by(CampaignModel.id)
        if cursor_id is not None:
            stmt = stmt.where(CampaignModel.id > cursor_id)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]
```

Apply the identical `target_ids` / `target_logic` param + `if target_ids:` block to `find_by_workspace` (same placement, after its `if tags:` block).

- [ ] **Step 5: Extend the protocol signatures**

In `backend/src/cellar/domain/research_organization/repository.py`, add `target_ids: list[uuid.UUID] | None = None` and `target_logic: str = "any"` to the `CampaignRepository.find_by_project` and `find_by_workspace` protocol signatures (keyword-only, matching the impl).

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/integration/persistence/research_organization/test_campaign_target_filter.py -v`
Expected: PASS (1 passed). Requires Docker.

- [ ] **Step 7: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/campaign_target_filter.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/campaign_repository.py \
        backend/src/cellar/domain/research_organization/repository.py \
        backend/tests/integration/persistence/research_organization/test_campaign_target_filter.py
git commit -m "feat(campaigns): filter campaigns by target (any/all) via run-targets subquery" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Backend — use case result + DTO field + list/get routes + API tests

**Files:**
- Modify: `backend/src/cellar/application/research_organization/list_campaigns.py`
- Modify: `backend/src/cellar/application/research_organization/get_campaign.py` (add targets to its output)
- Modify: `backend/src/cellar/interface/routes/_campaign_dtos.py` (`CampaignResponse`)
- Modify: `backend/src/cellar/interface/routes/campaigns.py` (`list_campaigns`, `get_campaign`)
- Test: `backend/tests/api/test_campaigns.py` (add cases)

- [ ] **Step 1: Write the failing API test**

Add to `backend/tests/api/test_campaigns.py` (match the existing fixtures/style — find how a campaign with a result+measurement+run+target is created in that file or a helper; if no helper exists, build the minimal campaign via the API/seed used by sibling tests). Add:

```python
    async def test_list_campaigns_includes_targets(self, client) -> None:
        # Arrange: a project with one campaign whose run measures target "InhA".
        # (Reuse the suite's campaign-with-measurement seed helper.)
        project_id, campaign_id, target_name = await self._seed_campaign_with_target(client)
        resp = await client.get("/api/v1/campaigns", params={"project_id": project_id})
        assert resp.status_code == 200
        row = next(c for c in resp.json()["items"] if c["id"] == campaign_id)
        assert target_name in [t["name"] for t in row["targets"]]

    async def test_list_campaigns_target_filter(self, client) -> None:
        project_id, campaign_id, _ = await self._seed_campaign_with_target(client)
        # the campaign's target id:
        row = next(
            c for c in (await client.get("/api/v1/campaigns", params={"project_id": project_id})).json()["items"]
            if c["id"] == campaign_id
        )
        target_id = row["targets"][0]["id"]
        other = str(uuid.uuid4())
        match = await client.get("/api/v1/campaigns", params={"project_id": project_id, "targets": target_id})
        miss = await client.get("/api/v1/campaigns", params={"project_id": project_id, "targets": other})
        assert campaign_id in [c["id"] for c in match.json()["items"]]
        assert campaign_id not in [c["id"] for c in miss.json()["items"]]
```

> If `test_campaigns.py` has no existing seed that attaches a run+target to a campaign measurement, add a small `_seed_campaign_with_target(client)` helper in the test class that creates a target, protocol, run (with run_targets), campaign, result, and measurement via the repository/session fixture the suite already uses (mirror Task 1's seed). Keep it inside the test module.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/api/test_campaigns.py -k "targets or target_filter" -v`
Expected: FAIL — `KeyError: 'targets'` (field absent) / filter has no effect.

- [ ] **Step 3: Add `targets` to `CampaignResponse`**

In `_campaign_dtos.py`, add the import:

```python
from cellar.interface.routes._target_refs import TargetRefResponse
```

Add the field to `CampaignResponse` (place after `results`):

```python
    targets: list[TargetRefResponse] = []
```

Extend `from_domain` to accept and map it (add the param after `scientist_by_run_id`):

```python
    @classmethod
    def from_domain(
        cls,
        c: Campaign,
        scientist_by_run_id: dict[uuid.UUID, str] | None = None,
        targets: list[TargetRef] | None = None,
    ) -> CampaignResponse:
        return cls(
            ...  # all existing fields unchanged
            results=[CampaignResultResponse.from_domain(r) for r in c.results],
            targets=[TargetRefResponse.from_ref(t) for t in (targets or [])],
        )
```

Add the `TargetRef` import for the type hint:

```python
from cellar.domain.screening_assay.target import TargetRef
```

- [ ] **Step 4: Make `ListCampaigns` return campaigns + targets map**

In `list_campaigns.py`: add a result dataclass and compute the projection inside the uow. Add imports:

```python
from cellar.domain.screening_assay.target import TargetRef
```

Add the result type and extend the query:

```python
@dataclass(frozen=True, kw_only=True)
class ListCampaignsQuery(Query):
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None = None
    cursor_id: uuid.UUID | None = None
    limit: int | None = None
    tags: list[uuid.UUID] | None = None
    tag_logic: str = "any"
    target_ids: list[uuid.UUID] | None = None
    target_logic: str = "any"


@dataclass(frozen=True, kw_only=True)
class ListCampaignsResult:
    page: PageResult[Campaign]
    targets_by_campaign: dict[uuid.UUID, list[TargetRef]]
```

Change `__call__` return type to `Result[ListCampaignsResult, DomainError]`, pass the new params to the repo calls, and after trimming to `effective_limit` (still inside `async with self._uow:`):

```python
            targets_by_campaign = await self._campaign_repo.project_targets(
                input.workspace_id, campaigns
            )
            return Success(
                ListCampaignsResult(
                    page=PageResult(items=campaigns, next_cursor=next_cursor),
                    targets_by_campaign=targets_by_campaign,
                )
            )
```

Pass `target_ids=input.target_ids, target_logic=input.target_logic` into both `find_by_project` and `find_by_workspace` calls.

- [ ] **Step 5: Update the `list_campaigns` route**

In `campaigns.py`, add `targets` / `target_logic` query params and thread the map:

```python
@router.get("", response_model=PaginatedResponse[CampaignResponse])
async def list_campaigns(
    auth: AuthDep,
    uc: ListCampaignsDep,
    project_id: uuid.UUID | None = Query(default=None),
    cursor: str | None = None,
    limit: int | None = None,
    tags: list[uuid.UUID] | None = Query(default=None),
    tag_logic: Literal["any", "all"] = Query(default="any"),
    targets: list[uuid.UUID] | None = Query(default=None),
    target_logic: Literal["any", "all"] = Query(default="any"),
) -> PaginatedResponse[CampaignResponse]:
    """List campaigns in the workspace, optionally filtered by project/tags/targets."""
    query = ListCampaignsQuery(
        workspace_id=auth.workspace_id,
        project_id=project_id,
        cursor_id=parse_cursor(cursor),
        limit=clamp_limit(limit),
        tags=tags,
        tag_logic=tag_logic,
        target_ids=targets,
        target_logic=target_logic,
    )
    out = result_to_response(await uc(query, auth=auth))
    return PaginatedResponse(
        items=[
            CampaignResponse.from_domain(c, targets=out.targets_by_campaign.get(c.id, []))
            for c in out.page.items
        ],
        next_cursor=out.page.next_cursor,
    )
```

- [ ] **Step 6: Populate `targets` on `get_campaign` (detail header)**

In `get_campaign.py`, after loading the campaign (inside the uow), compute its targets and add them to the output. Add to the use case's output object a `targets: list[TargetRef]` field (mirror how `scientist_by_run_id` is carried), populated via:

```python
            targets_by_campaign = await self._campaign_repo.project_targets(
                input.workspace_id, [campaign]
            )
            targets = targets_by_campaign.get(campaign.id, [])
```

> Read `get_campaign.py` first to see its exact output dataclass; add a `targets` field there and set it. If `GetCampaign` does not currently hold a `CampaignRepository` reference, inject the same repo it already uses to load the campaign (it must already have one).

Then update the `get_campaign` route:

```python
    return CampaignResponse.from_domain(out.campaign, out.scientist_by_run_id, targets=out.targets)
```

- [ ] **Step 7: Run the API tests + full campaign suite**

Run: `cd backend && uv run pytest tests/api/test_campaigns.py -v`
Expected: PASS (existing + 2 new). Then `uv run pytest tests/integration/application/research_organization -k campaign -v` to catch any `ListCampaigns` caller breakage.

- [ ] **Step 8: import-linter + commit**

Run: `cd backend && uv run lint-imports` (contracts must stay 3 kept / 0 broken).

```bash
git add backend/src/cellar/application/research_organization/list_campaigns.py \
        backend/src/cellar/application/research_organization/get_campaign.py \
        backend/src/cellar/interface/routes/_campaign_dtos.py \
        backend/src/cellar/interface/routes/campaigns.py \
        backend/tests/api/test_campaigns.py
git commit -m "feat(campaigns): expose targets on CampaignResponse + target filter params" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Frontend — regenerate types + `useCampaigns` target params

**Files:**
- Regenerate: `frontend/src/shared/lib/api/model/*` (orval — `CampaignResponse.targets`, list query params)
- Modify: `frontend/src/features/screen-campaign/hooks/use-campaigns.ts`

- [ ] **Step 1: Regenerate orval types**

With the backend running on `:8000` (it auto-reloads):

Run: `cd frontend && pnpm generate:api`
Expected: `CampaignResponse` in `model/campaignResponse.ts` gains `targets: TargetRefResponse[]`. Review `git diff --stat frontend/src/shared/lib/api/model` — additive only (a `targets` field; possibly a shared `TargetRefResponse` already exists). If the diff shows unrelated non-additive churn, STOP and report.

- [ ] **Step 2: Write the failing test**

Add to (or create) `frontend/src/features/screen-campaign/hooks/use-campaigns.test.tsx` a test that asserts the target params are forwarded. Mirror any existing hook test in the repo for `customInstance` mocking. Minimal:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCampaigns } from "./use-campaigns";

const customInstance = vi.fn(async () => ({ items: [], next_cursor: null }));
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: (args: unknown) => customInstance(args),
}));
vi.mock("@/shared/lib/api/campaigns/campaigns", () => ({
  getCampaignApiV1CampaignsCampaignIdGet: vi.fn(),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useCampaigns target params", () => {
  beforeEach(() => vi.clearAllMocks());
  it("forwards targets + target_logic", async () => {
    renderHook(() => useCampaigns("p1", { targets: ["t1", "t2"], targetLogic: "all" }), { wrapper });
    await waitFor(() => expect(customInstance).toHaveBeenCalled());
    const arg = customInstance.mock.calls[0][0] as { params?: Record<string, unknown> };
    expect(arg.params?.targets).toEqual(["t1", "t2"]);
    expect(arg.params?.target_logic).toBe("all");
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && pnpm test -- use-campaigns`
Expected: FAIL — params undefined (hook ignores `targets`).

- [ ] **Step 4: Extend the hook**

In `use-campaigns.ts`, extend the options type + queryKey + params:

```ts
export function useCampaigns(
  projectId?: string,
  options?: {
    tags?: string[];
    tagLogic?: "any" | "all";
    targets?: string[];
    targetLogic?: "any" | "all";
  } & Partial<UseQueryOptions<CampaignResponse[], Error, CampaignResponse[]>>,
) {
  const { tags: rawTags, tagLogic, targets: rawTargets, targetLogic, ...queryOptions } =
    options ?? {};
  const tags = rawTags?.length ? rawTags : null;
  const targets = rawTargets?.length ? rawTargets : null;

  const filterKey =
    tags || targets
      ? { tags, tagLogic: tagLogic ?? "any", targets, targetLogic: targetLogic ?? "any" }
      : null;
  const baseKey = projectId ? campaignKeys.byProject(projectId) : campaignKeys.all;
  const queryKey = filterKey ? [...baseKey, filterKey] : baseKey;

  return useQuery({
    queryKey,
    queryFn: async () => {
      const params: Record<string, unknown> = {};
      if (projectId) params.project_id = projectId;
      if (tags) {
        params.tags = tags;
        params.tag_logic = tagLogic ?? "any";
      }
      if (targets) {
        params.targets = targets;
        params.target_logic = targetLogic ?? "any";
      }
      const page = await customInstance<PaginatedResponseCampaignResponse>({
        url: `${API_V1}/campaigns`,
        method: "GET",
        ...(Object.keys(params).length ? { params } : {}),
      });
      return page.items;
    },
    enabled: projectId !== undefined ? !!projectId : true,
    ...queryOptions,
  });
}
```

- [ ] **Step 5: Run test + lint**

Run: `cd frontend && pnpm test -- use-campaigns` → PASS. Then `pnpm lint` (judge by exit code; the new/changed files must produce no diagnostics — verify with `npx @biomejs/biome check src/features/screen-campaign/hooks/use-campaigns.ts` exit 0).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/shared/lib/api/model \
        frontend/src/features/screen-campaign/hooks/use-campaigns.ts \
        frontend/src/features/screen-campaign/hooks/use-campaigns.test.tsx
git commit -m "feat(campaigns): generated targets type + target filter params on useCampaigns" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Frontend — `TargetFilter` component

**Files:**
- Create: `frontend/src/features/screening-assay/components/target-filter.tsx`
- Test: `frontend/src/features/screening-assay/components/target-filter.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/screening-assay/components/target-filter.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TargetFilter } from "./target-filter";

vi.mock("../hooks/use-targets", () => ({
  useTargets: () => ({
    data: [
      { id: "t1", name: "InhA", target_type: "protein" },
      { id: "t2", name: "DnaE1", target_type: "protein" },
    ],
  }),
}));

describe("TargetFilter", () => {
  it("toggles a target and reports it via onChange", () => {
    const onChange = vi.fn();
    render(
      <TargetFilter value={{ targetIds: [], targetLogic: "any" }} onChange={onChange} />,
    );
    fireEvent.click(screen.getByRole("button"));        // open popover
    fireEvent.click(screen.getByText("InhA"));
    expect(onChange).toHaveBeenCalledWith({ targetIds: ["t1"], targetLogic: "any" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- target-filter`
Expected: FAIL — cannot find module `./target-filter`.

- [ ] **Step 3: Create the component (clone of `TagFilter`)**

Read `frontend/src/features/tagging/components/tag-filter.tsx` and create `target-filter.tsx` by mirroring it exactly, with these substitutions: `useTags`→`useTargets`, tag/`TagChip` rendering → plain target name, `TagIcon`→`Target` (lucide), label "Tags"→"Targets", key shape `tagIds`/`tagLogic`→`targetIds`/`targetLogic`. Full component:

```tsx
"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/shared/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { useDebounce } from "@/shared/hooks/use-debounce";
import { SEARCH_DEBOUNCE_MS } from "@/shared/lib/timing";
import { cn } from "@/shared/lib/utils";
import { Check, Target as TargetIcon } from "lucide-react";
import { useState } from "react";
import { useTargets } from "../hooks/use-targets";

export interface TargetFilterValue {
  targetIds: string[];
  targetLogic: "any" | "all";
}

interface TargetFilterProps {
  value: TargetFilterValue;
  onChange: (v: TargetFilterValue) => void;
}

export function TargetFilter({ value, onChange }: TargetFilterProps) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const debouncedQ = useDebounce(q, SEARCH_DEBOUNCE_MS);
  const { data: targets } = useTargets({ q: debouncedQ || undefined, limit: 50 });

  const toggle = (id: string) =>
    onChange({
      ...value,
      targetIds: value.targetIds.includes(id)
        ? value.targetIds.filter((x) => x !== id)
        : [...value.targetIds, id],
    });

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant={value.targetIds.length ? "secondary" : "outline"} size="sm">
          <TargetIcon className="mr-2 h-4 w-4" />
          Targets{value.targetIds.length ? ` (${value.targetIds.length})` : ""}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            value={q}
            onValueChange={setQ}
            placeholder="Search targets…"
            className="h-8 text-sm"
          />
          <CommandList>
            <CommandEmpty className="px-3 py-2 text-xs text-muted-foreground">
              No targets.
            </CommandEmpty>
            <CommandGroup>
              {targets?.map((t) => (
                <CommandItem
                  key={t.id}
                  value={t.name}
                  onSelect={() => toggle(t.id)}
                  className="gap-1.5 text-sm"
                >
                  <Check
                    className={cn(
                      "h-3 w-3",
                      value.targetIds.includes(t.id) ? "opacity-100" : "opacity-0",
                    )}
                  />
                  {t.name}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
          {value.targetIds.length > 1 && (
            <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs">
              <span className="text-muted-foreground">Match</span>
              <div className="flex gap-1">
                {(["any", "all"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => onChange({ ...value, targetLogic: mode })}
                    className={cn(
                      "rounded px-2 py-0.5 capitalize",
                      value.targetLogic === mode
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-accent",
                    )}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>
          )}
          {value.targetIds.length > 0 && (
            <button
              type="button"
              onClick={() => onChange({ targetIds: [], targetLogic: value.targetLogic })}
              className="w-full border-t border-border px-3 py-1.5 text-left text-xs text-muted-foreground hover:bg-accent"
            >
              Clear target filter
            </button>
          )}
        </Command>
      </PopoverContent>
    </Popover>
  );
}
```

> Confirm `useTargets` accepts `{ q, limit }` (it's `createCrudHooks(...).useList`; check `create-crud-hooks.ts` for the list param names — if it uses `query` not `q`, adjust). The mocked test bypasses this, so verify against the real hook before finishing.

- [ ] **Step 4: Run test + lint**

Run: `cd frontend && pnpm test -- target-filter` → PASS. `npx @biomejs/biome check src/features/screening-assay/components/target-filter.tsx` → exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/screening-assay/components/target-filter.tsx \
        frontend/src/features/screening-assay/components/target-filter.test.tsx
git commit -m "feat(targets): TargetFilter multi-select (mirrors TagFilter)" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Frontend — Targets column + filter on the project campaign table

**Files:**
- Modify: `frontend/src/features/screen-campaign/components/campaign-list.tsx`

- [ ] **Step 1: Add imports**

Add to the imports in `campaign-list.tsx`:

```tsx
import { TargetChips } from "@/features/screening-assay/components/target-chips";
import { TargetFilter, type TargetFilterValue } from "@/features/screening-assay/components/target-filter";
```

- [ ] **Step 2: Add filter state + wire the hook**

Replace the `tagFilter` state + `useCampaigns` call:

```tsx
  const [tagFilter, setTagFilter] = useState<TagFilterValue>({ tagIds: [], tagLogic: "any" });
  const [targetFilter, setTargetFilter] = useState<TargetFilterValue>({
    targetIds: [],
    targetLogic: "any",
  });
  const { data, isLoading, error } = useCampaigns(projectId, {
    tags: tagFilter.tagIds,
    tagLogic: tagFilter.tagLogic,
    targets: targetFilter.targetIds,
    targetLogic: targetFilter.targetLogic,
  });
```

Update `hasFilter`:

```tsx
  const hasFilter = tagFilter.tagIds.length > 0 || targetFilter.targetIds.length > 0;
```

- [ ] **Step 3: Render the TargetFilter in the toolbar**

In the toolbar `div`, add `TargetFilter` next to `TagFilter`:

```tsx
      <div className="mb-4 flex items-center gap-3 justify-between">
        <div className="flex items-center gap-2">
          <TagFilter value={tagFilter} onChange={setTagFilter} />
          <TargetFilter value={targetFilter} onChange={setTargetFilter} />
        </div>
        <CreateCampaignDialog
          projectId={projectId}
          trigger={
            <Button size="sm">
              <Plus className="mr-2 h-4 w-4" />
              New Campaign
            </Button>
          }
        />
      </div>
```

Update the empty-state copy to be filter-agnostic:

```tsx
            {hasFilter ? "No campaigns match the current filters." : "No campaigns yet."}
```

- [ ] **Step 4: Add the Targets column**

Add a header between "Status" and "Channels":

```tsx
              <TableHead>Status</TableHead>
              <TableHead>Targets</TableHead>
              <TableHead>Channels</TableHead>
```

Add the cell in the row (between the status cell and channels cell):

```tsx
                <TableCell>
                  <CampaignStatusChip status={c.status} />
                </TableCell>
                <TableCell>
                  <TargetChips targets={c.targets} max={3} />
                </TableCell>
                <TableCell>{c.channels?.length ?? 0}</TableCell>
```

> `c.targets` is `TargetRefResponse[]` from the regenerated type; `TargetChips` accepts `TargetRef[]` (id/name/target_type) — same shape. If TS complains about the generated vs feature `TargetRef` type, cast `c.targets as TargetRef[]` or map to `{ id, name, target_type }`; prefer a direct pass if structurally compatible.

- [ ] **Step 5: Verify + lint + commit**

Run: `cd frontend && pnpm test -- campaign-list` (if a test exists; otherwise run the suite touching this area) and `npx @biomejs/biome check src/features/screen-campaign/components/campaign-list.tsx` → exit 0. Also `npx tsc --noEmit 2>&1 | grep -i campaign-list` → empty.

```bash
git add frontend/src/features/screen-campaign/components/campaign-list.tsx
git commit -m "feat(campaigns): targets column + target filter on project campaign table" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Frontend — target chips on the campaign detail header

**Files:**
- Modify: `frontend/src/features/screen-campaign/components/sections/header-strip.tsx`

- [ ] **Step 1: Inspect the header**

Read `header-strip.tsx` to find where it receives the campaign (`CampaignResponse`) and renders metadata. It already has the campaign object (it shows name/status).

- [ ] **Step 2: Render chips**

Import and render `TargetChips`, sourced from `campaign.targets`, in the metadata area (next to status / below the title — match the existing layout):

```tsx
import { TargetChips } from "@/features/screening-assay/components/target-chips";
// ...
<div className="flex items-center gap-2">
  <span className="text-xs text-muted-foreground">Targets</span>
  <TargetChips targets={campaign.targets} max={5} />
</div>
```

> Use the actual prop name the component receives for the campaign object (likely `campaign`); place the block consistently with sibling metadata rows. No filter here — chips only.

- [ ] **Step 3: Verify + commit**

Run: `npx @biomejs/biome check src/features/screen-campaign/components/sections/header-strip.tsx` → exit 0; `npx tsc --noEmit 2>&1 | grep -i header-strip` → empty.

```bash
git add frontend/src/features/screen-campaign/components/sections/header-strip.tsx
git commit -m "feat(campaigns): target chips on campaign detail header" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8 (DROPPABLE): Frontend — target chips in the add-from-campaign picker

> Lowest priority. Skip if scope needs trimming — the field is already on the DTO and can be added later in one line.

**Files:**
- Modify: `frontend/src/features/screen-campaign/components/add-from-campaign-dialog.tsx`

- [ ] **Step 1: Inspect the picker**

Read `add-from-campaign-dialog.tsx`; find where each candidate campaign row is rendered (it uses `useCampaigns`).

- [ ] **Step 2: Add chips to each campaign row**

```tsx
import { TargetChips } from "@/features/screening-assay/components/target-chips";
// in each campaign row, next to the name/metadata:
<TargetChips targets={c.targets} max={2} />
```

- [ ] **Step 3: Verify + commit**

Run: `npx @biomejs/biome check src/features/screen-campaign/components/add-from-campaign-dialog.tsx` → exit 0.

```bash
git add frontend/src/features/screen-campaign/components/add-from-campaign-dialog.tsx
git commit -m "feat(campaigns): target chips in add-from-campaign picker" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Done — verification

- [ ] `cd backend && uv run pytest tests/integration/persistence/research_organization/test_campaign_targets_projection.py tests/integration/persistence/research_organization/test_campaign_target_filter.py tests/api/test_campaigns.py -v` — all green
- [ ] `cd backend && uv run lint-imports` — 3 contracts kept, 0 broken
- [ ] `cd frontend && pnpm test -- "use-campaigns target-filter"` — green; `npx @biomejs/biome check src/` — **0 errors** (warnings are the pre-existing burn-down only; confirm by exit code, not piped output)
- [ ] Manual: project campaign table shows a Targets column (chips) + a Targets filter; filtering by a target narrows the list; a campaign with no measured targets shows an em-dash and is excluded by an active filter; detail header shows chips.
- [ ] Counter-screen sanity: a campaign whose run has a counter-screen target chips that target and matches its filter (expected per the run-union semantics).
```
