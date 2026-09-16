# Tagging Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Run, Campaign, Batch, and the inventory RegisteredPlate taggable (assign + display + filter), finish the Protocol/Project detail-page tag editors, and add a cross-entity "everything tagged X" browse surface.

**Architecture:** The tagging backend is already generalized (a `TaggableEntityType` enum, a `TagLinkMixin`, a generic `SQLAlchemyTagLinkRepository` base + per-type subclasses resolved through a static `_REGISTRY`, a generic assignment router keyed off `_ENTITY_COLLECTIONS`, and a shared `tag_filter_subquery`). Adding an entity type is therefore additive: enum value + link table + 3-line repo subclass + registry entry + route-map entry + migration + `tags`/`tag_logic` params on its list endpoint. The only new component is a `UNION ALL` browse read repository + endpoint + `/tags` page. The FE tagging components (`TagTable`, `TagFilter`, `TagChip`) and hooks are already generic over the entity-collection string.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 async / Alembic / Lagom DI / dry-returns; Next.js / React / TanStack Query / orval.

**Spec:** `docs/superpowers/specs/2026-06-04-tagging-expansion-design.md`

**Entity → table → URL-collection → link table → entity_id attr → browse label:**
| Entity | table | URL coll. | link table | entity_id attr | label column |
|--------|-------|-----------|-----------|----------------|--------------|
| Run | `runs` | `runs` | `run_tags` | `run_id` | `protocols.name · runs.run_date` |
| Campaign | `campaign` | `campaigns` | `campaign_tags` | `campaign_id` | `campaign.name` |
| Batch | `batches` | `batches` | `batch_tags` | `batch_id` | `batches.batch_number` |
| RegisteredPlate | `registered_plates` | `plates` | `registered_plate_tags` | `registered_plate_id` | `registered_plates.plate_label` |

> ⚠️ Campaign's table is **`campaign`** (singular). The migration FK and the model FK target use `campaign`, never `campaigns`. The URL collection stays `campaigns`.

---

## PHASE 1 — Backend foundation (enum + link tables + repos + route map + migration)

### Task 1: Add the four new taggable entity types end-to-end (red→green)

**Files:**
- Modify: `backend/src/cellar/domain/workspace_config/tagging/tag.py` (enum)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/models.py` (link models)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_link_repository.py` (subclasses + registry)
- Modify: `backend/src/cellar/interface/routes/tags.py` (`_ENTITY_COLLECTIONS`)
- Create: `backend/alembic/versions/050_tagging_expansion.py` (migration)
- Test: `backend/tests/integration/test_tagging_expansion.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/integration/test_tagging_expansion.py`. It proves the plumbing exists: (a) the registry resolves a link repo for each new type, and (b) the migration created the four link tables. The *functional* link behavior (assign / find / filter) is exercised end-to-end through real entities in the Phase 2 API tests — no fragile raw-SQL entity inserts here (those would trip the entities' own FK constraints, e.g. `batches.molecule_id`). Cascade-on-delete is FK-enforced via the identical `_create_link_table` helper already covered for molecules in `tests/integration/test_tagging.py`.

```python
"""Integration tests for the four new taggable entity types (plumbing)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from cellar.domain.workspace_config.tagging.tag import TaggableEntityType
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    get_tag_link_repository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

pytestmark = pytest.mark.asyncio


NEW_TYPES = [
    TaggableEntityType.RUN,
    TaggableEntityType.CAMPAIGN,
    TaggableEntityType.BATCH,
    TaggableEntityType.PLATE,
]

NEW_LINK_TABLES = ["run_tags", "campaign_tags", "batch_tags", "registered_plate_tags"]


def test_registry_resolves_all_new_types(uow: AsyncUnitOfWork) -> None:
    for t in NEW_TYPES:
        repo = get_tag_link_repository(t, uow)
        assert repo is not None
        assert repo.entity_id_attr  # bound to a real column name


async def test_new_link_tables_exist(uow: AsyncUnitOfWork) -> None:
    async with uow:
        for table in NEW_LINK_TABLES:
            res = await uow.session.execute(
                text("SELECT to_regclass(:t)"), {"t": table}
            )
            assert res.scalar_one() is not None, f"{table} missing — migration 050 not applied"
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `cd backend && uv run pytest tests/integration/test_tagging_expansion.py -v`
Expected: FAIL — `AttributeError: RUN` (enum has no `RUN` yet) on the registry test; the table-existence test fails once the enum exists but before the migration runs.

- [ ] **Step 3: Add the enum values**

In `backend/src/cellar/domain/workspace_config/tagging/tag.py`, extend `TaggableEntityType`:

```python
class TaggableEntityType(str, Enum):
    """Entity types that can carry tags (one link table each)."""

    MOLECULE = "Molecule"
    PROTOCOL = "Protocol"
    PROJECT = "Project"
    COLLECTION = "Collection"
    RUN = "Run"
    CAMPAIGN = "Campaign"
    BATCH = "Batch"
    PLATE = "Plate"
```

- [ ] **Step 4: Add the four link-table models**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/models.py`, append after `CollectionTagLinkModel`:

```python
class RunTagLinkModel(Base, TagLinkMixin):
    __tablename__ = "run_tags"

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_run_tags_tag_id", "tag_id"),)


class CampaignTagLinkModel(Base, TagLinkMixin):
    __tablename__ = "campaign_tags"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("campaign.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_campaign_tags_tag_id", "tag_id"),)


class BatchTagLinkModel(Base, TagLinkMixin):
    __tablename__ = "batch_tags"

    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("batches.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_batch_tags_tag_id", "tag_id"),)


class RegisteredPlateTagLinkModel(Base, TagLinkMixin):
    __tablename__ = "registered_plate_tags"

    registered_plate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("registered_plates.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (Index("ix_registered_plate_tags_tag_id", "tag_id"),)
```

- [ ] **Step 5: Add the four repo subclasses + registry entries**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_link_repository.py`:

Extend the model imports:
```python
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
    RegisteredPlateModel,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignModel,
    CollectionModel,
    ProjectModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ProtocolModel,
    RunModel,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import (
    BatchTagLinkModel,
    CampaignTagLinkModel,
    CollectionTagLinkModel,
    MoleculeTagLinkModel,
    ProjectTagLinkModel,
    ProtocolTagLinkModel,
    RegisteredPlateTagLinkModel,
    RunTagLinkModel,
    TagModel,
)
```

Add the subclasses after `CollectionTagLinkRepository`:
```python
class RunTagLinkRepository(SQLAlchemyTagLinkRepository):
    link_model = RunTagLinkModel
    entity_model = RunModel
    entity_id_attr = "run_id"


class CampaignTagLinkRepository(SQLAlchemyTagLinkRepository):
    link_model = CampaignTagLinkModel
    entity_model = CampaignModel
    entity_id_attr = "campaign_id"


class BatchTagLinkRepository(SQLAlchemyTagLinkRepository):
    link_model = BatchTagLinkModel
    entity_model = BatchModel
    entity_id_attr = "batch_id"


class RegisteredPlateTagLinkRepository(SQLAlchemyTagLinkRepository):
    link_model = RegisteredPlateTagLinkModel
    entity_model = RegisteredPlateModel
    entity_id_attr = "registered_plate_id"
```

Extend `_REGISTRY`:
```python
_REGISTRY: dict[TaggableEntityType, type[SQLAlchemyTagLinkRepository]] = {
    TaggableEntityType.MOLECULE: MoleculeTagLinkRepository,
    TaggableEntityType.PROTOCOL: ProtocolTagLinkRepository,
    TaggableEntityType.PROJECT: ProjectTagLinkRepository,
    TaggableEntityType.COLLECTION: CollectionTagLinkRepository,
    TaggableEntityType.RUN: RunTagLinkRepository,
    TaggableEntityType.CAMPAIGN: CampaignTagLinkRepository,
    TaggableEntityType.BATCH: BatchTagLinkRepository,
    TaggableEntityType.PLATE: RegisteredPlateTagLinkRepository,
}
```

- [ ] **Step 6: Add the URL-collection route map entries**

In `backend/src/cellar/interface/routes/tags.py`, extend `_ENTITY_COLLECTIONS`:
```python
_ENTITY_COLLECTIONS: dict[str, TaggableEntityType] = {
    "molecules": TaggableEntityType.MOLECULE,
    "protocols": TaggableEntityType.PROTOCOL,
    "projects": TaggableEntityType.PROJECT,
    "collections": TaggableEntityType.COLLECTION,
    "runs": TaggableEntityType.RUN,
    "campaigns": TaggableEntityType.CAMPAIGN,
    "batches": TaggableEntityType.BATCH,
    "plates": TaggableEntityType.PLATE,
}
```

- [ ] **Step 7: Write the migration (create 4 link tables + recreate the cross-type view)**

Create `backend/alembic/versions/050_tagging_expansion.py`:
```python
"""050 — tagging expansion: link tables for run/campaign/batch/registered_plate.

Adds four per-entity tag link tables and recreates the tag_links_all UNION view
to cover all eight taggable entity types. No backfill (these entities carry no
legacy tag data).

Revision ID: 050_tagging_expansion
Revises: 049_readout_data_wellless_unique
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "050_tagging_expansion"
down_revision = "049_readout_data_wellless_unique"


def _create_link_table(name: str, entity_col: str, entity_table: str) -> None:
    op.create_table(
        name,
        sa.Column(
            entity_col,
            sa.Uuid(),
            sa.ForeignKey(f"{entity_table}.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Uuid(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("assigned_by", sa.Uuid(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(f"ix_{name}_tag_id", name, ["tag_id"])


_VIEW_SQL = """
    CREATE VIEW tag_links_all AS
        SELECT 'Molecule' AS entity_type, molecule_id AS entity_id,
               tag_id, assigned_by, assigned_at FROM molecule_tags
        UNION ALL
        SELECT 'Protocol', protocol_id, tag_id, assigned_by, assigned_at FROM protocol_tags
        UNION ALL
        SELECT 'Project', project_id, tag_id, assigned_by, assigned_at FROM project_tags
        UNION ALL
        SELECT 'Collection', collection_id, tag_id, assigned_by, assigned_at FROM collection_tags
        UNION ALL
        SELECT 'Run', run_id, tag_id, assigned_by, assigned_at FROM run_tags
        UNION ALL
        SELECT 'Campaign', campaign_id, tag_id, assigned_by, assigned_at FROM campaign_tags
        UNION ALL
        SELECT 'Batch', batch_id, tag_id, assigned_by, assigned_at FROM batch_tags
        UNION ALL
        SELECT 'Plate', registered_plate_id, tag_id, assigned_by, assigned_at
               FROM registered_plate_tags
"""

_VIEW_SQL_OLD = """
    CREATE VIEW tag_links_all AS
        SELECT 'Molecule' AS entity_type, molecule_id AS entity_id,
               tag_id, assigned_by, assigned_at FROM molecule_tags
        UNION ALL
        SELECT 'Protocol', protocol_id, tag_id, assigned_by, assigned_at FROM protocol_tags
        UNION ALL
        SELECT 'Project', project_id, tag_id, assigned_by, assigned_at FROM project_tags
        UNION ALL
        SELECT 'Collection', collection_id, tag_id, assigned_by, assigned_at FROM collection_tags
"""


def upgrade() -> None:
    _create_link_table("run_tags", "run_id", "runs")
    _create_link_table("campaign_tags", "campaign_id", "campaign")
    _create_link_table("batch_tags", "batch_id", "batches")
    _create_link_table("registered_plate_tags", "registered_plate_id", "registered_plates")
    op.execute("DROP VIEW IF EXISTS tag_links_all")
    op.execute(_VIEW_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS tag_links_all")
    op.execute(_VIEW_SQL_OLD)
    op.drop_table("registered_plate_tags")
    op.drop_table("batch_tags")
    op.drop_table("campaign_tags")
    op.drop_table("run_tags")
```

- [ ] **Step 8: Apply the migration**

Run: `cd backend && uv run alembic upgrade head`
Expected: `Running upgrade 049_readout_data_wellless_unique -> 050_tagging_expansion`.

- [ ] **Step 9: Run the integration test to confirm green**

Run: `cd backend && uv run pytest tests/integration/test_tagging_expansion.py -v`
Expected: PASS (2 tests).

- [ ] **Step 10: Run the existing tagging tests for regressions**

Run: `cd backend && uv run pytest tests/integration/test_tagging.py tests/api/test_tags.py -q`
Expected: PASS (no regressions — registry/view changes are additive).

- [ ] **Step 11: Commit**

```bash
cd backend && git add src/cellar/domain/workspace_config/tagging/tag.py \
  src/cellar/infrastructure/persistence/sqlalchemy/tagging/models.py \
  src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_link_repository.py \
  src/cellar/interface/routes/tags.py \
  alembic/versions/050_tagging_expansion.py \
  tests/integration/test_tagging_expansion.py
git commit -m "feat(tagging): link tables + repos for run/campaign/batch/registered_plate (migration 050)"
```

---

## PHASE 2 — List tag-filtering (4 endpoints)

Each endpoint follows the exact Protocol/Project template: add `tags`/`tag_logic` to the route, the Query object, the use case, and the repository method (which applies `tag_filter_subquery`). The shared helper:

```python
# already exists: backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_filter.py
tag_filter_subquery(LinkModel, "<entity>_id", tags, match_all=tag_logic == "all")
```

### Task 2: Run list — filter by tag

**Files:**
- Modify: `backend/src/cellar/application/screening/list_runs_with_counts.py` (Query + use case)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/run_repository.py` (`find_by_protocol`)
- Modify: `backend/src/cellar/interface/routes/runs.py` (`list_runs_by_protocol`)
- Test: `backend/tests/api/test_tagging_expansion_filters.py`

- [ ] **Step 1: Write the failing API test**

Create `backend/tests/api/test_tagging_expansion_filters.py`. Use the existing `_seed_protocol_with_run` helper pattern from `tests/api/test_projects.py:171` (import or replicate it) to create a protocol + run, then tag the run and filter.

```python
"""API tests: tag-filtering the run/campaign/batch/plate list endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _make_run(client: AsyncClient) -> tuple[str, str]:
    """Create a protocol + run; return (protocol_id, run_id)."""
    proto = await client.post(
        "/api/v1/protocols",
        json={"name": "TagRunProto", "protocol_type": "dose_response"},
    )
    assert proto.status_code in (200, 201), proto.text
    protocol_id = proto.json()["id"]
    run = await client.post(
        "/api/v1/runs", json={"protocol_id": protocol_id, "run_date": "2026-06-04"}
    )
    assert run.status_code in (200, 201), run.text
    return protocol_id, run.json()["id"]


class TestRunTagFilter:
    async def test_filter_runs_by_tag(self, client: AsyncClient) -> None:
        protocol_id, run_id = await _make_run(client)
        assign = await client.post(
            f"/api/v1/runs/{run_id}/tags", json={"key": "qc", "value": "pass"}
        )
        assert assign.status_code == 201, assign.text
        tag_id = assign.json()["id"]

        listed = await client.get(
            f"/api/v1/protocols/{protocol_id}/runs", params={"tags": [tag_id]}
        )
        assert listed.status_code == 200, listed.text
        assert [r["id"] for r in listed.json()] == [run_id]

        # A different tag id returns no runs.
        other = await client.post(
            f"/api/v1/runs/{run_id}/tags", json={"key": "unrelated"}
        )
        none = await client.get(
            f"/api/v1/protocols/{protocol_id}/runs",
            params={"tags": ["00000000-0000-0000-0000-000000000000"]},
        )
        assert none.json() == []
```

> If `_make_run`'s exact create payloads differ from the real routes, adjust to match `routes/protocols.py` create + `routes/runs.py::create_run` (the run create body is `{protocol_id, run_date}` — see `RunResponse`/create handler). Reuse `tests/api/test_projects.py::_seed_protocol_with_run` if it already produces a run id.

- [ ] **Step 2: Run the test — confirm it fails**

Run: `cd backend && uv run pytest tests/api/test_tagging_expansion_filters.py::TestRunTagFilter -v`
Expected: FAIL — `list_runs_by_protocol` ignores `tags` (returns the run regardless / 422 on unknown param is not raised but filter has no effect → the "none" assertion fails).

- [ ] **Step 3: Thread `tags`/`tag_logic` through the Query + use case**

In `backend/src/cellar/application/screening/list_runs_with_counts.py`, extend the dataclass and the repo call:
```python
@dataclass(frozen=True, kw_only=True)
class ListRunsWithCountsQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    tags: list[uuid.UUID] | None = None
    tag_logic: str = "any"
```
In `ListRunsWithCounts.__call__`, change the repo call:
```python
            runs = await self._run_repo.find_by_protocol(
                input.workspace_id,
                input.protocol_id,
                tags=input.tags,
                tag_logic=input.tag_logic,
            )
```

- [ ] **Step 4: Apply the filter in the repository**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/run_repository.py`, add imports at the top:
```python
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import RunTagLinkModel
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_filter import tag_filter_subquery
```
Replace `find_by_protocol` with:
```python
    async def find_by_protocol(
        self,
        workspace_id: uuid.UUID,
        protocol_id: uuid.UUID,
        *,
        tags: list[uuid.UUID] | None = None,
        tag_logic: str = "any",
    ) -> list[Run]:
        """List all runs for a protocol in a workspace, newest first."""
        stmt = select(RunModel).where(
            RunModel.workspace_id == workspace_id,
            RunModel.protocol_id == protocol_id,
        )
        if tags:
            stmt = stmt.where(
                RunModel.id.in_(
                    tag_filter_subquery(
                        RunTagLinkModel, "run_id", tags, match_all=tag_logic == "all"
                    )
                )
            )
        stmt = stmt.order_by(RunModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]
```

- [ ] **Step 5: Add the route query params**

In `backend/src/cellar/interface/routes/runs.py`, update `list_runs_by_protocol` (ensure `from typing import Literal` and `Query` are imported):
```python
@router.get("/protocols/{protocol_id}/runs", response_model=list[RunResponse])
async def list_runs_by_protocol(
    protocol_id: uuid.UUID,
    auth: AuthDep,
    uc: ListRunsWithCountsDep,
    tags: list[uuid.UUID] | None = Query(default=None),
    tag_logic: Literal["any", "all"] = Query(default="any"),
) -> list[RunResponse]:
    result = await uc(
        ListRunsWithCountsQuery(
            workspace_id=auth.workspace_id,
            protocol_id=protocol_id,
            tags=tags,
            tag_logic=tag_logic,
        ),
        auth=auth,
    )
    items = result_to_response(result)
    return [
        RunResponse.from_domain(item.run, molecule_count=item.molecule_count)
        for item in items
    ]
```

- [ ] **Step 6: Run the test — confirm green**

Run: `cd backend && uv run pytest tests/api/test_tagging_expansion_filters.py::TestRunTagFilter -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd backend && git add src/cellar/application/screening/list_runs_with_counts.py \
  src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/run_repository.py \
  src/cellar/interface/routes/runs.py tests/api/test_tagging_expansion_filters.py
git commit -m "feat(tagging): tag-filter the per-protocol run list"
```

### Task 3: Campaign list — filter by tag

**Files:**
- Modify: `backend/src/cellar/application/research_organization/list_campaigns.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/campaign_repository.py` (`find_by_project`, `find_by_workspace`)
- Modify: `backend/src/cellar/interface/routes/campaigns.py` (`list_campaigns`)
- Test: same file, add `TestCampaignTagFilter`

- [ ] **Step 1: Write the failing test**

Add to `tests/api/test_tagging_expansion_filters.py` (reuse `_create_empty_campaign` from `tests/api/test_campaigns_api.py:72`, or create via `POST /api/v1/campaigns`):
```python
class TestCampaignTagFilter:
    async def test_filter_campaigns_by_tag(self, client: AsyncClient) -> None:
        proj = await client.post("/api/v1/projects", json={"name": "TagCampProj"})
        project_id = proj.json()["id"]
        camp = await client.post(
            "/api/v1/campaigns", json={"project_id": project_id, "name": "C-tag"}
        )
        assert camp.status_code in (200, 201), camp.text
        campaign_id = camp.json()["id"]
        assign = await client.post(
            f"/api/v1/campaigns/{campaign_id}/tags", json={"key": "lead-series"}
        )
        assert assign.status_code == 201, assign.text
        tag_id = assign.json()["id"]
        listed = await client.get(
            "/api/v1/campaigns", params={"project_id": project_id, "tags": [tag_id]}
        )
        assert listed.status_code == 200, listed.text
        assert [c["id"] for c in listed.json()["items"]] == [campaign_id]
```

- [ ] **Step 2: Run — confirm fail**

Run: `cd backend && uv run pytest tests/api/test_tagging_expansion_filters.py::TestCampaignTagFilter -v`
Expected: FAIL (filter ignored).

- [ ] **Step 3: Thread params through Query + use case**

In `backend/src/cellar/application/research_organization/list_campaigns.py`, add to `ListCampaignsQuery`:
```python
    tags: list[uuid.UUID] | None = None
    tag_logic: str = "any"
```
In both repo-call branches of `ListCampaigns.__call__`, pass `tags=input.tags, tag_logic=input.tag_logic`:
```python
                campaigns = await self._campaign_repo.find_by_project(
                    input.workspace_id, input.project_id,
                    cursor_id=input.cursor_id, limit=fetch_limit,
                    tags=input.tags, tag_logic=input.tag_logic,
                )
            else:
                campaigns = await self._campaign_repo.find_by_workspace(
                    input.workspace_id,
                    cursor_id=input.cursor_id, limit=fetch_limit,
                    tags=input.tags, tag_logic=input.tag_logic,
                )
```

- [ ] **Step 4: Apply the filter in both repo methods**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/campaign_repository.py`, add imports:
```python
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import CampaignTagLinkModel
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_filter import tag_filter_subquery
```
Add `tags`/`tag_logic` kwargs to both `find_by_project` and `find_by_workspace`, and inside each, after the base `.where(...)` and before `.order_by(CampaignModel.id)`, insert:
```python
        if tags:
            stmt = stmt.where(
                CampaignModel.id.in_(
                    tag_filter_subquery(
                        CampaignTagLinkModel, "campaign_id", tags, match_all=tag_logic == "all"
                    )
                )
            )
```
(Signature additions: `tags: list[uuid.UUID] | None = None, tag_logic: str = "any"` as keyword-only params.)

- [ ] **Step 5: Add the route query params**

In `backend/src/cellar/interface/routes/campaigns.py`, add to `list_campaigns` (ensure `Literal` imported):
```python
    tags: list[uuid.UUID] | None = Query(default=None),
    tag_logic: Literal["any", "all"] = Query(default="any"),
```
and pass them into `ListCampaignsQuery(...)`:
```python
        tags=tags,
        tag_logic=tag_logic,
```

- [ ] **Step 6: Run — confirm green**

Run: `cd backend && uv run pytest tests/api/test_tagging_expansion_filters.py::TestCampaignTagFilter -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd backend && git add src/cellar/application/research_organization/list_campaigns.py \
  src/cellar/infrastructure/persistence/sqlalchemy/research_organization/campaign_repository.py \
  src/cellar/interface/routes/campaigns.py tests/api/test_tagging_expansion_filters.py
git commit -m "feat(tagging): tag-filter the per-project campaign list"
```

### Task 4: Batch global list — filter by tag

**Files:**
- Modify: `backend/src/cellar/application/inventory/list_batches_global.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/batch_repository.py` (`list_global`)
- Modify: `backend/src/cellar/interface/routes/inventory_hub.py` (`list_batches_global`)
- Test: same file, add `TestBatchTagFilter`

- [ ] **Step 1: Write the failing test**

Add to `tests/api/test_tagging_expansion_filters.py`:
```python
class TestBatchTagFilter:
    async def test_filter_global_batches_by_tag(self, client: AsyncClient) -> None:
        mol = await client.post(
            "/api/v1/molecules", json={"smiles": "CCO", "name": "ethanol-tag"}
        )
        assert mol.status_code in (200, 201), mol.text
        molecule_id = mol.json()["id"]
        batch = await client.post(
            "/api/v1/batches", json={"molecule_id": molecule_id, "batch_number": "BT-1"}
        )
        assert batch.status_code in (200, 201), batch.text
        batch_id = batch.json()["id"]
        assign = await client.post(
            f"/api/v1/batches/{batch_id}/tags", json={"key": "freezer", "value": "A3"}
        )
        assert assign.status_code == 201, assign.text
        tag_id = assign.json()["id"]
        listed = await client.get("/api/v1/batches", params={"tags": [tag_id]})
        assert listed.status_code == 200, listed.text
        assert any(row["id"] == batch_id for row in listed.json()["items"])
```
> Match the real molecule/batch create payloads (`routes/molecules.py`, `routes/batches.py`); adjust field names if the create contract differs.

- [ ] **Step 2: Run — confirm fail.** `cd backend && uv run pytest tests/api/test_tagging_expansion_filters.py::TestBatchTagFilter -v` → FAIL.

- [ ] **Step 3: Thread params through Query + use case**

In `backend/src/cellar/application/inventory/list_batches_global.py`, add to `ListBatchesGlobalQuery`:
```python
    tags: list[uuid.UUID] | None = None
    tag_logic: str = "any"
```
In `ListBatchesGlobal.__call__`, pass to `list_global`:
```python
                tags=input.tags,
                tag_logic=input.tag_logic,
```

- [ ] **Step 4: Apply the filter in `list_global`**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/batch_repository.py`, add imports:
```python
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import BatchTagLinkModel
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_filter import tag_filter_subquery
```
Add `tags: list[uuid.UUID] | None = None, tag_logic: str = "any"` to the `list_global` signature (keyword-only). In its statement construction, after the workspace `.where(BatchModel.workspace_id == workspace_id)` (and alongside the other optional filters), add:
```python
        if tags:
            stmt = stmt.where(
                BatchModel.id.in_(
                    tag_filter_subquery(
                        BatchTagLinkModel, "batch_id", tags, match_all=tag_logic == "all"
                    )
                )
            )
```
> Apply this to the main `stmt` that selects batch rows (the one filtered by `search`/`sources`), before pagination/ordering. If `list_global` builds a count query separately, apply the same `.where(...)` to it so totals stay consistent.

- [ ] **Step 5: Add the route query params**

In `backend/src/cellar/interface/routes/inventory_hub.py`, add to `list_batches_global` (ensure `Literal` imported):
```python
    tags: list[uuid.UUID] | None = Query(default=None),
    tag_logic: Literal["any", "all"] = Query(default="any"),
```
and pass into `ListBatchesGlobalQuery(...)`:
```python
        tags=tags,
        tag_logic=tag_logic,
```

- [ ] **Step 6: Run — confirm green.** `cd backend && uv run pytest tests/api/test_tagging_expansion_filters.py::TestBatchTagFilter -v` → PASS.

- [ ] **Step 7: Commit**

```bash
cd backend && git add src/cellar/application/inventory/list_batches_global.py \
  src/cellar/infrastructure/persistence/sqlalchemy/inventory/batch_repository.py \
  src/cellar/interface/routes/inventory_hub.py tests/api/test_tagging_expansion_filters.py
git commit -m "feat(tagging): tag-filter the global batch list"
```

### Task 5: RegisteredPlate list — filter by tag

**Files:**
- Modify: `backend/src/cellar/application/inventory/registered_plates.py` (`ListPlatesQuery`, `ListPlates`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/registered_plate_repository.py` (`search`)
- Modify: `backend/src/cellar/interface/routes/registered_plates.py` (`list_plates`)
- Test: same file, add `TestPlateTagFilter`

- [ ] **Step 1: Write the failing test**

Add to `tests/api/test_tagging_expansion_filters.py`:
```python
class TestPlateTagFilter:
    async def test_filter_plates_by_tag(self, client: AsyncClient) -> None:
        plate = await client.post(
            "/api/v1/plates",
            json={"barcode": "PLATE-TAG-1", "plate_label": "Tagged", "format": "96"},
        )
        assert plate.status_code in (200, 201), plate.text
        plate_id = plate.json()["id"]
        assign = await client.post(
            f"/api/v1/plates/{plate_id}/tags", json={"key": "assay-ready"}
        )
        assert assign.status_code == 201, assign.text
        tag_id = assign.json()["id"]
        listed = await client.get("/api/v1/plates", params={"tags": [tag_id]})
        assert listed.status_code == 200, listed.text
        assert [p["id"] for p in listed.json()] == [plate_id]
```
> Match the real plate create payload from `routes/registered_plates.py::create` (the create body — barcode/plate_label/format and any required fields).

- [ ] **Step 2: Run — confirm fail.** → FAIL.

- [ ] **Step 3: Thread params through Query + use case**

In `backend/src/cellar/application/inventory/registered_plates.py`, add to `ListPlatesQuery`:
```python
    tags: list[uuid.UUID] | None = None
    tag_logic: str = "any"
```
In `ListPlates.__call__`, pass to `self._repo.search(...)`:
```python
                tags=input.tags,
                tag_logic=input.tag_logic,
```

- [ ] **Step 4: Apply the filter in `search`**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/registered_plate_repository.py`, add imports:
```python
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import (
    RegisteredPlateTagLinkModel,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_filter import tag_filter_subquery
```
Add `tags: list[uuid.UUID] | None = None, tag_logic: str = "any"` (keyword-only) to `search`, and after the other optional `.where(...)` filters and before `.order_by(...)`, add:
```python
        if tags:
            stmt = stmt.where(
                RegisteredPlateModel.id.in_(
                    tag_filter_subquery(
                        RegisteredPlateTagLinkModel,
                        "registered_plate_id",
                        tags,
                        match_all=tag_logic == "all",
                    )
                )
            )
```

- [ ] **Step 5: Add the route query params**

In `backend/src/cellar/interface/routes/registered_plates.py`, add to `list_plates` (ensure `Literal` and `Query` imported):
```python
    tags: list[uuid.UUID] | None = Query(default=None),
    tag_logic: Literal["any", "all"] = Query(default="any"),
```
and pass into `ListPlatesQuery(...)`:
```python
        tags=tags,
        tag_logic=tag_logic,
```

- [ ] **Step 6: Run — confirm green.** → PASS. Then run the whole new filter file:
`cd backend && uv run pytest tests/api/test_tagging_expansion_filters.py -q` → all PASS.

- [ ] **Step 7: Commit**

```bash
cd backend && git add src/cellar/application/inventory/registered_plates.py \
  src/cellar/infrastructure/persistence/sqlalchemy/inventory/registered_plate_repository.py \
  src/cellar/interface/routes/registered_plates.py tests/api/test_tagging_expansion_filters.py
git commit -m "feat(tagging): tag-filter the registered-plate list"
```

---

## PHASE 3 — Cross-entity tag-browse endpoint

### Task 6: Browse read repository + use case + endpoint + DI

**Files:**
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_browse_repository.py`
- Create: `backend/src/cellar/application/workspace_config/tagging/list_tag_entities.py`
- Modify: `backend/src/cellar/infrastructure/di/_workspace_config.py` (binding)
- Modify: `backend/src/cellar/interface/dependencies/_workspace_config.py` (Dep alias)
- Modify: `backend/src/cellar/interface/routes/tags.py` (endpoint + response model)
- Test: `backend/tests/api/test_tag_browse.py`

- [ ] **Step 1: Write the failing API test**

Create `backend/tests/api/test_tag_browse.py`:
```python
"""API test: cross-entity tag-browse endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_browse_returns_entities_across_types(client: AsyncClient) -> None:
    # Tag a project and a collection with the SAME (key,value).
    proj = await client.post("/api/v1/projects", json={"name": "BrowseProj"})
    project_id = proj.json()["id"]
    col = await client.post("/api/v1/collections", json={"name": "BrowseCol"})
    collection_id = col.json()["id"]

    pt = await client.post(
        f"/api/v1/projects/{project_id}/tags", json={"key": "theme", "value": "kinase"}
    )
    tag_id = pt.json()["id"]
    await client.post(
        f"/api/v1/collections/{collection_id}/tags", json={"key": "theme", "value": "kinase"}
    )

    resp = await client.get(f"/api/v1/tags/{tag_id}/entities")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    by_type = {(r["entity_type"], r["entity_id"]) for r in rows}
    assert ("Project", project_id) in by_type
    assert ("Collection", collection_id) in by_type
    # Labels are present.
    assert all(r["label"] for r in rows)

    # types filter narrows results.
    only_proj = await client.get(
        f"/api/v1/tags/{tag_id}/entities", params={"types": ["Project"]}
    )
    assert {r["entity_type"] for r in only_proj.json()} == {"Project"}
```

- [ ] **Step 2: Run — confirm fail.** `cd backend && uv run pytest tests/api/test_tag_browse.py -v` → FAIL (404, route missing).

- [ ] **Step 3: Write the browse read repository**

Create `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_browse_repository.py`:
```python
"""Cross-entity tag-browse read repository.

Given a tag, returns the entities of every taggable type that carry it, each with
a display label. A UNION ALL across the eight link tables, each branch joined to
its entity table for the label and workspace-scoped. Read-only; not an aggregate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import String, cast, literal, select, union_all

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    BatchModel,
    RegisteredPlateModel,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignModel,
    CollectionModel,
    ProjectModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    ProtocolModel,
    RunModel,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import (
    BatchTagLinkModel,
    CampaignTagLinkModel,
    CollectionTagLinkModel,
    MoleculeTagLinkModel,
    ProjectTagLinkModel,
    ProtocolTagLinkModel,
    RegisteredPlateTagLinkModel,
    RunTagLinkModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@dataclass(frozen=True, kw_only=True)
class TaggedEntityRow:
    entity_type: str
    entity_id: uuid.UUID
    label: str


class SQLAlchemyTagBrowseRepository:
    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    @property
    def _session(self):  # noqa: ANN202
        return self._uow.session

    def _branch(
        self, entity_type, link_model, entity_id_attr, entity_model, label_col,
        tag_id, workspace_id, extra_where=None,
    ):
        link_fk = getattr(link_model, entity_id_attr)
        stmt = (
            select(
                literal(entity_type).label("entity_type"),
                entity_model.id.label("entity_id"),
                label_col.label("label"),
            )
            .join(link_model, link_fk == entity_model.id)
            .where(link_model.tag_id == tag_id, entity_model.workspace_id == workspace_id)
        )
        if extra_where is not None:
            stmt = stmt.where(extra_where)
        return stmt

    async def find_entities_for_tag(
        self,
        workspace_id: uuid.UUID,
        tag_id: uuid.UUID,
        *,
        types: list[str] | None = None,
        limit: int = 200,
    ) -> list[TaggedEntityRow]:
        b = self._branch
        run_branch = (
            select(
                literal("Run").label("entity_type"),
                RunModel.id.label("entity_id"),
                (ProtocolModel.name + literal(" · ") + cast(RunModel.run_date, String)).label(
                    "label"
                ),
            )
            .join(RunTagLinkModel, RunTagLinkModel.run_id == RunModel.id)
            .join(ProtocolModel, ProtocolModel.id == RunModel.protocol_id)
            .where(RunTagLinkModel.tag_id == tag_id, RunModel.workspace_id == workspace_id)
        )
        branches = {
            "Molecule": b("Molecule", MoleculeTagLinkModel, "molecule_id", MoleculeModel,
                          MoleculeModel.registration_number, tag_id, workspace_id,
                          extra_where=MoleculeModel.merged_into_id.is_(None)),
            "Protocol": b("Protocol", ProtocolTagLinkModel, "protocol_id", ProtocolModel,
                          ProtocolModel.name, tag_id, workspace_id),
            "Project": b("Project", ProjectTagLinkModel, "project_id", ProjectModel,
                         ProjectModel.name, tag_id, workspace_id),
            "Collection": b("Collection", CollectionTagLinkModel, "collection_id", CollectionModel,
                            CollectionModel.name, tag_id, workspace_id),
            "Run": run_branch,
            "Campaign": b("Campaign", CampaignTagLinkModel, "campaign_id", CampaignModel,
                          CampaignModel.name, tag_id, workspace_id),
            "Batch": b("Batch", BatchTagLinkModel, "batch_id", BatchModel,
                       BatchModel.batch_number, tag_id, workspace_id),
            "Plate": b("Plate", RegisteredPlateTagLinkModel, "registered_plate_id",
                       RegisteredPlateModel, RegisteredPlateModel.plate_label, tag_id, workspace_id),
        }
        selected = [s for name, s in branches.items() if not types or name in types]
        if not selected:
            return []
        unioned = union_all(*selected).subquery()
        stmt = (
            select(unioned.c.entity_type, unioned.c.entity_id, unioned.c.label)
            .order_by(unioned.c.entity_type, unioned.c.label)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [
            TaggedEntityRow(entity_type=r.entity_type, entity_id=r.entity_id, label=r.label)
            for r in result.all()
        ]
```

- [ ] **Step 4: Write the use case**

Create `backend/src/cellar/application/workspace_config/tagging/list_tag_entities.py`:
```python
"""List all entities (across types) carrying a given tag — viewer-level read."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.shared.auth import require_workspace_role
from cellar.application.shared.cqrs import Query
from cellar.application.shared.types import AuthContext
from cellar.domain.shared.errors import DomainError
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_browse_repository import (
    SQLAlchemyTagBrowseRepository,
    TaggedEntityRow,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


@dataclass(frozen=True, kw_only=True)
class ListTagEntitiesQuery(Query):
    workspace_id: uuid.UUID
    tag_id: uuid.UUID
    types: list[str] | None = None
    limit: int = 200


class ListTagEntities:
    def __init__(self, uow: AsyncUnitOfWork, repo: SQLAlchemyTagBrowseRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListTagEntitiesQuery, auth: AuthContext | None = None
    ) -> Result[list[TaggedEntityRow], DomainError]:
        require_workspace_role(auth, "viewer")
        async with self._uow:
            rows = await self._repo.find_entities_for_tag(
                input.workspace_id, input.tag_id, types=input.types, limit=input.limit
            )
            return Success(rows)
```
> Confirm the import paths for `Query`, `require_workspace_role`, `AuthContext`, `DomainError` against a sibling use case (e.g. `list_tags.py`) and match them exactly — these vary slightly across the codebase.

- [ ] **Step 5: Wire DI**

In `backend/src/cellar/infrastructure/di/_workspace_config.py`, add imports near the other tagging imports:
```python
from cellar.application.workspace_config.tagging.list_tag_entities import ListTagEntities
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_browse_repository import (
    SQLAlchemyTagBrowseRepository,
)
```
After the `container.define(ListTags, _list_tags)` block, add:
```python
    def _list_tag_entities(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListTagEntities(uow, SQLAlchemyTagBrowseRepository(uow))

    container.define(ListTagEntities, _list_tag_entities)
```

In `backend/src/cellar/interface/dependencies/_workspace_config.py`, add the import + Dep alias beside the other tag deps:
```python
from cellar.application.workspace_config.tagging.list_tag_entities import ListTagEntities
# ...
ListTagEntitiesDep = Annotated[ListTagEntities, Depends(_get_use_case(ListTagEntities))]
```

- [ ] **Step 6: Add the endpoint**

In `backend/src/cellar/interface/routes/tags.py`, add the response model near the others:
```python
class TaggedEntityResponse(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    label: str
```
Add to the imports: `from fastapi import APIRouter, Query, Response` (add `Query`), the `ListTagEntitiesDep`, and the use-case Query:
```python
from cellar.application.workspace_config.tagging.list_tag_entities import (
    ListTagEntitiesQuery,
)
from cellar.interface.dependencies._workspace_config import ListTagEntitiesDep  # add to existing import
```
On the **management** router (`router = APIRouter(prefix="/api/v1/tags", ...)`), add:
```python
@router.get("/{tag_id}/entities", response_model=list[TaggedEntityResponse])
async def list_tag_entities(
    tag_id: uuid.UUID,
    auth: AuthDep,
    use_case: ListTagEntitiesDep,
    types: list[str] | None = Query(default=None),
    limit: int = 200,
) -> list[TaggedEntityResponse]:
    query = ListTagEntitiesQuery(
        workspace_id=auth.workspace_id, tag_id=tag_id, types=types, limit=limit
    )
    rows = result_to_response(await use_case(query, auth=auth))
    return [
        TaggedEntityResponse(entity_type=r.entity_type, entity_id=r.entity_id, label=r.label)
        for r in rows
    ]
```
> Route ordering: `/{tag_id}/entities` must be declared so it doesn't shadow `/{tag_id}` PATCH/DELETE — FastAPI matches by path + method, so this is fine, but keep it grouped with the other `/{tag_id}/...` routes.

- [ ] **Step 7: Run — confirm green.** `cd backend && uv run pytest tests/api/test_tag_browse.py -v` → PASS.

- [ ] **Step 8: Regenerate the orval client (new endpoint + response type)**

Run (backend up on :8000):
```bash
cd frontend && pnpm generate:api
```
Review the `src/shared/lib/api/model/` diff — expect new `TaggedEntityResponse` + the `listTagEntities*` params type. Additive only.

- [ ] **Step 9: Commit**

```bash
cd backend && git add src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_browse_repository.py \
  src/cellar/application/workspace_config/tagging/list_tag_entities.py \
  src/cellar/infrastructure/di/_workspace_config.py \
  src/cellar/interface/dependencies/_workspace_config.py \
  src/cellar/interface/routes/tags.py tests/api/test_tag_browse.py
git commit -m "feat(tagging): cross-entity tag-browse endpoint (GET /tags/{id}/entities)"
cd ../frontend && git add src/shared/lib/api/model src/shared/lib/api/tags
git commit -m "chore(api): regenerate orval client for tag-browse endpoint"
```

---

## PHASE 4 — Frontend detail-page tag editors

### Task 7: Extend the `TaggableEntity` union

**Files:** Modify `frontend/src/features/tagging/types.ts`

- [ ] **Step 1: Add the four collections**

```typescript
export type TaggableEntity =
  | "molecules"
  | "protocols"
  | "projects"
  | "collections"
  | "runs"
  | "campaigns"
  | "batches"
  | "plates";
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/features/tagging/types.ts
git commit -m "feat(tagging): allow runs/campaigns/batches/plates as taggable entities"
```

### Task 8: Mount `TagTable` on the six detail pages

The editor component: `<TagTable entity="<collection>" entityId={<id>} canEdit={canEditTags} />`, with `const canEditTags = useAuthzHasRole("editor")` (import `{ useAuthzHasRole } from "@duar-auth/nextjs"`; import `{ TagTable } from "@/features/tagging/components/tag-table"`).

**Files (one mount each):**
- Modify: `frontend/src/features/screening-assay/components/protocol-detail.tsx` (or its overview tab)
- Modify: `frontend/src/features/research-organization/components/project-detail.tsx` (overview tab)
- Modify: `frontend/src/features/screening-assay/components/run-detail.tsx` (already imports `useAuthzHasRole`)
- Modify: `frontend/src/features/screen-campaign/components/sections/header-strip.tsx` (shared by builder + view)
- Modify: `frontend/src/features/inventory/components/batch-detail.tsx`
- Modify: `frontend/src/features/inventory/components/plate-detail.tsx`

- [ ] **Step 1: Protocol detail** — in the overview/main content area of `protocol-detail.tsx`, add `const canEditTags = useAuthzHasRole("editor");` (if not present) and render:
```tsx
<TagTable entity="protocols" entityId={protocol.id} canEdit={canEditTags} />
```

- [ ] **Step 2: Project detail** — in the Overview tab of `project-detail.tsx`:
```tsx
<TagTable entity="projects" entityId={project.id} canEdit={canEditTags} />
```

- [ ] **Step 3: Run detail** — `run-detail.tsx` already has `useAuthzHasRole`; add `const canEditTags = useAuthzHasRole("editor");` and after the metadata `Card` (around line 615):
```tsx
<TagTable entity="runs" entityId={run.id} canEdit={canEditTags} />
```

- [ ] **Step 4: Campaign** — in the shared `header-strip.tsx` (rendered by both `campaign-builder.tsx` and `campaign-view/index.tsx`), add a tags row. The header receives the campaign; mount:
```tsx
<TagTable entity="campaigns" entityId={campaign.id} canEdit={canEditTags} />
```
Derive `canEditTags` here, or thread it as a prop if the header already takes editability flags. Place it below the title/badges block so it appears in both draft and closed views.

- [ ] **Step 5: Batch detail** — after the properties `Card` (around line 138) in `batch-detail.tsx`:
```tsx
<TagTable entity="batches" entityId={batch.id} canEdit={canEditTags} />
```

- [ ] **Step 6: Plate detail** — in the metadata area of `plate-detail.tsx`:
```tsx
<TagTable entity="plates" entityId={plate.id} canEdit={canEditTags} />
```

- [ ] **Step 7: Typecheck + visual smoke**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS. (Manual: open one of each detail page; the Tags table renders and an editor can add/remove a tag.)

- [ ] **Step 8: Commit**

```bash
cd frontend && git add src/features/screening-assay/components/protocol-detail.tsx \
  src/features/research-organization/components/project-detail.tsx \
  src/features/screening-assay/components/run-detail.tsx \
  src/features/screen-campaign/components/sections/header-strip.tsx \
  src/features/inventory/components/batch-detail.tsx \
  src/features/inventory/components/plate-detail.tsx
git commit -m "feat(tagging): mount TagTable on protocol/project/run/campaign/batch/plate detail"
```

---

## PHASE 5 — Frontend list tag-filters

Each list mirrors the Protocol/Project template: `const [tagFilter, setTagFilter] = useState<TagFilterValue>({ tagIds: [], tagLogic: "any" });`, render `<TagFilter value={tagFilter} onChange={setTagFilter} />` in the toolbar, and pass `{ tags: tagFilter.tagIds, tagLogic: tagFilter.tagLogic }` into the list data hook. Each data hook gains an `options?: { tags?: string[]; tagLogic?: "any" | "all" }` param that (a) joins the query key and (b) adds `params.tags` / `params.tag_logic` to the request — copy the exact shape from `use-protocols.ts` (lines 34–48). Imports: `{ TagFilter } from "@/features/tagging/components/tag-filter"`, `{ TagFilterValue } from "@/features/tagging/components/tag-filter"`.

### Task 9: Run list filter (per-protocol Runs tab)

**Files:** Modify `frontend/src/features/screening-assay/components/run-list.tsx` + its data hook (the `useRuns`/run-counts hook it calls).

- [ ] **Step 1:** Add the `useState<TagFilterValue>` + `<TagFilter>` in the run-list toolbar; pass `{ tags, tagLogic }` to the run hook.
- [ ] **Step 2:** In the run data hook, add the `options` param; build `params.tags`/`params.tag_logic` (request URL `/api/v1/protocols/${protocolId}/runs`); add tags to the query key. (Copy `use-protocols.ts` shape.)
- [ ] **Step 3:** Typecheck: `cd frontend && pnpm tsc --noEmit` → PASS. Manual: tag a run, filter the Runs tab.
- [ ] **Step 4:** Commit: `git commit -m "feat(tagging): tag filter on the per-protocol run list"`

### Task 10: Campaign list filter (per-project)

**Files:** Modify `frontend/src/features/screen-campaign/components/campaign-list.tsx` + its `useCampaigns` hook.

- [ ] **Step 1:** Add `TagFilter` state + mount in the campaign-list toolbar (after line 92); pass `{ tags, tagLogic }` to `useCampaigns`.
- [ ] **Step 2:** In `useCampaigns`, add `options` param; add `params.tags`/`params.tag_logic` to the `/api/v1/campaigns` request (alongside `project_id`); add to query key.
- [ ] **Step 3:** Typecheck → PASS. Manual smoke.
- [ ] **Step 4:** Commit: `git commit -m "feat(tagging): tag filter on the per-project campaign list"`

### Task 11: Global batch list filter

**Files:** Modify `frontend/src/features/inventory/components/batch-list.tsx` (`GlobalBatchList`, add a toolbar before the DataGrid at line ~212) + the `useBatchesGlobal` hook / `BatchGlobalParams` type.

- [ ] **Step 1:** Add `TagFilter` state + a toolbar row above the grid in `GlobalBatchList`; pass `{ tags, tagLogic }` into `useBatchesGlobal`.
- [ ] **Step 2:** Extend `BatchGlobalParams` with `tags?: string[]; tagLogic?: "any" | "all"`; in the hook, add `params.tags`/`params.tag_logic` to the `/api/v1/batches` request; add to query key.
- [ ] **Step 3:** Typecheck → PASS. Manual smoke.
- [ ] **Step 4:** Commit: `git commit -m "feat(tagging): tag filter on the global batch list"`

### Task 12: Plate list filter

**Files:** Modify `frontend/src/features/inventory/components/plate-list.tsx` (join the existing type/status/format filter bar, ~line 202) + the `usePlates` hook.

- [ ] **Step 1:** Add `TagFilter` state + mount it in the existing filter bar; pass `{ tags, tagLogic }` into `usePlates`.
- [ ] **Step 2:** Extend `usePlates` params with `tags`/`tagLogic`; add `params.tags`/`params.tag_logic` to the `/api/v1/plates` request; add to query key.
- [ ] **Step 3:** Typecheck → PASS. Manual smoke.
- [ ] **Step 4:** Commit: `git commit -m "feat(tagging): tag filter on the registered-plate list"`

---

## PHASE 6 — Frontend cross-entity browse page

### Task 13: `/tags` browse page + hook + nav + admin drill-in

**Files:**
- Create: `frontend/src/app/(dashboard)/tags/page.tsx`
- Create: `frontend/src/features/tagging/components/tag-browse.tsx`
- Create: `frontend/src/features/tagging/hooks/use-tag-entities.ts`
- Modify: `frontend/src/shared/lib/navigation.ts` (nav entry)
- Modify: `frontend/src/features/tagging/components/tag-list.tsx` (link tag rows to `/tags?tag=<id>`)

- [ ] **Step 1: Write the browse data hook**

Create `frontend/src/features/tagging/hooks/use-tag-entities.ts`. Per the orval convention (CLAUDE.md), **do not hand-roll the DTO shape** — alias the generated `TaggedEntityResponse` (produced by the Task 6 Step 8 regen):
```typescript
"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import type { TaggedEntityResponse } from "@/shared/lib/api/model";
import { useQuery } from "@tanstack/react-query";

/** A tagged entity row from the cross-entity browse endpoint. */
export type TaggedEntity = TaggedEntityResponse;

export function useTagEntities(tagId: string | undefined, types?: string[]) {
  return useQuery({
    queryKey: ["tag-entities", tagId, types ?? null],
    enabled: !!tagId,
    queryFn: () =>
      customInstance<TaggedEntity[]>({
        url: `/api/v1/tags/${tagId}/entities`,
        method: "GET",
        ...(types?.length ? { params: { types } } : {}),
      }),
  });
}
```
> The generated type's field names follow the API (`entity_type`, `entity_id`, `label`). If orval emits a different exact name (e.g. it dedupes to `TaggedEntityResponse`), import that name — check `src/shared/lib/api/model/index.ts` after regen.

- [ ] **Step 2: Write the browse component**

Create `frontend/src/features/tagging/components/tag-browse.tsx`. It uses `TagFilter` to pick a tag (single-tag v1: uses `tagIds[0]`), reads an optional `?tag=` query param, groups results by `entity_type`, and links each row to the entity's detail route.

```tsx
"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { TagFilter, type TagFilterValue } from "@/features/tagging/components/tag-filter";
import { useTagEntities, type TaggedEntity } from "@/features/tagging/hooks/use-tag-entities";

/** Maps an entity_type to its detail route prefix. */
const ROUTE_PREFIX: Record<string, string> = {
  Molecule: "/compounds",
  Protocol: "/assays/protocols",
  Project: "/projects",
  Collection: "/collections",
  Run: "/assays/runs",
  Campaign: "/campaigns",
  Batch: "/inventory/batches",
  Plate: "/inventory/plates",
};

function hrefFor(row: TaggedEntity): string {
  const prefix = ROUTE_PREFIX[row.entity_type] ?? "";
  return prefix ? `${prefix}/${row.entity_id}` : "#";
}

export function TagBrowse() {
  const params = useSearchParams();
  const initialTag = params.get("tag");
  const [filter, setFilter] = useState<TagFilterValue>({
    tagIds: initialTag ? [initialTag] : [],
    tagLogic: "any",
  });
  const activeTag = filter.tagIds[0];
  const { data, isLoading } = useTagEntities(activeTag);

  const grouped = useMemo(() => {
    const out = new Map<string, TaggedEntity[]>();
    for (const row of data ?? []) {
      const list = out.get(row.entity_type) ?? [];
      list.push(row);
      out.set(row.entity_type, list);
    }
    return [...out.entries()];
  }, [data]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">Browse by tag</h1>
        <TagFilter value={filter} onChange={setFilter} />
      </div>
      {!activeTag && <p className="text-muted-foreground">Pick a tag to see what carries it.</p>}
      {activeTag && isLoading && <p className="text-muted-foreground">Loading…</p>}
      {activeTag && !isLoading && grouped.length === 0 && (
        <p className="text-muted-foreground">Nothing carries this tag yet.</p>
      )}
      {grouped.map(([type, rows]) => (
        <section key={type} className="space-y-1">
          <h2 className="text-sm font-medium text-muted-foreground">
            {type} ({rows.length})
          </h2>
          <ul className="divide-y rounded-md border">
            {rows.map((row) => (
              <li key={`${row.entity_type}:${row.entity_id}`}>
                <Link href={hrefFor(row)} className="block px-3 py-2 hover:bg-accent">
                  {row.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
```
> Verify each `ROUTE_PREFIX` value against the actual app routes (e.g. confirm molecule detail is `/compounds/<id>`; the FE recon noted molecule list, runs at `/assays/runs/[id]`, plates at `/inventory/plates/[id]`). Fix any prefix that doesn't match a real route.

- [ ] **Step 3: Write the page**

Create `frontend/src/app/(dashboard)/tags/page.tsx`:
```tsx
import { TagBrowse } from "@/features/tagging/components/tag-browse";

export default function TagBrowsePage() {
  return <TagBrowse />;
}
```

- [ ] **Step 4: Add the nav entry**

In `frontend/src/shared/lib/navigation.ts`, add a viewer-facing entry (e.g. under the Discovery group, reusing the `Tag` icon already imported):
```typescript
{ title: "Browse by Tag", href: "/tags", icon: Tag },
```

- [ ] **Step 5: Admin drill-in**

In `frontend/src/features/tagging/components/tag-list.tsx`, wrap each tag's display (the `TagChip` / name cell, ~line 74) in a link to the browse page:
```tsx
<Link href={`/tags?tag=${tag.id}`}>
  <TagChip tag={tag} />
</Link>
```
(Import `Link from "next/link"`. Keep the existing rename/merge/delete actions intact.)

- [ ] **Step 6: Typecheck + manual**

Run: `cd frontend && pnpm tsc --noEmit` → PASS.
Manual: visit `/tags`, pick a tag, confirm grouped results link out; from `/admin/tags`, click a tag → lands on `/tags?tag=<id>` pre-filtered.

- [ ] **Step 7: Commit**

```bash
cd frontend && git add src/app/\(dashboard\)/tags/page.tsx \
  src/features/tagging/components/tag-browse.tsx \
  src/features/tagging/hooks/use-tag-entities.ts \
  src/shared/lib/navigation.ts \
  src/features/tagging/components/tag-list.tsx
git commit -m "feat(tagging): cross-entity /tags browse page + admin drill-in"
```

---

## PHASE 7 — End-to-end test

### Task 14: Playwright — tag → filter → browse across types

**Files:** Create `frontend/tests/e2e/tagging-expansion.spec.ts` (match the existing Playwright config/location).

- [ ] **Step 1: Write the E2E spec**

Cover the headline journey: tag a Batch, filter the inventory batch list by that tag, then open `/tags` for the tag and confirm the Batch appears alongside a same-tag entity of another type.
```typescript
import { test, expect } from "@playwright/test";

test("tag a batch, filter inventory, browse across types", async ({ page }) => {
  // 1. Open a batch detail, add a tag "e2e-tag".
  // 2. Open a project detail, add the same tag.
  // 3. Inventory batch list → TagFilter → select "e2e-tag" → only the batch row shows.
  // 4. Visit /tags?tag=... (or pick in the browse picker) → assert a "Batch" group and a
  //    "Project" group both list the tagged entities.
  // Fill in selectors per existing e2e helpers (auth/setup) in frontend/tests/e2e.
  await page.goto("/inventory");
  // ...follow existing e2e patterns for auth + navigation + selectors...
  expect(true).toBeTruthy(); // replace with real assertions
});
```
> Flesh out selectors using the existing E2E helpers (auth bootstrap, data setup) already in `frontend/tests/e2e/`. Keep it to the one cross-cutting journey; per-surface behavior is covered by the backend API tests.

- [ ] **Step 2: Run the E2E suite**

Run: `cd frontend && pnpm playwright test tagging-expansion`
Expected: PASS (after wiring real selectors).

- [ ] **Step 3: Commit**

```bash
cd frontend && git add tests/e2e/tagging-expansion.spec.ts
git commit -m "test(tagging): e2e tag → filter → cross-entity browse"
```

---

## Final verification

- [ ] **Backend full suite:** `cd backend && uv run pytest tests/integration/test_tagging_expansion.py tests/api/test_tagging_expansion_filters.py tests/api/test_tag_browse.py tests/integration/test_tagging.py tests/api/test_tags.py -q` → all PASS.
- [ ] **Frontend typecheck + lint:** `cd frontend && pnpm tsc --noEmit && pnpm lint` → PASS.
- [ ] **Migration round-trips:** `cd backend && uv run alembic downgrade -1 && uv run alembic upgrade head` → clean.
- [ ] Update `docs/implementation-status.md` if it tracks tagging coverage.

---

## Notes / deferred (from spec §12)

- **Run label** = `protocol.name · run_date` (runs have no name); requires the protocol join in the browse query (done in Task 6).
- **Batch filter on the global list only**; per-molecule batch list gets the detail editor, not a filter.
- **Browse v1 is single-tag** (drives off `tagIds[0]`); multi-tag AND/OR and cursor pagination are deferred — the endpoint caps at `limit=200`.
- **Admin drill-in** links tag rows to the browse page (usage-count column is a separate, deferred concern).
