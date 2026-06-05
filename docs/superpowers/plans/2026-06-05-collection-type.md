# Collection `type` Attribute Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class `type` enum attribute to the `Collection` aggregate so collections can be categorized by their role in the early-discovery screening cascade.

**Architecture:** A new `CollectionType` StrEnum lives in the research-organization domain. The `Collection` aggregate carries `type` (default `generic`), persisted as a `VARCHAR(32)` column with a server default for zero-downtime backfill. The attribute flows through application commands, the REST API, and the frontend (create/edit dialog, dashboard column, detail header badge). No type-driven *behavior* is built — only the data model and display.

**Tech Stack:** Python 3.13 / SQLAlchemy 2.0 async / Alembic / Pydantic v2 / FastAPI (backend); Next.js / React / TypeScript / react-hook-form + zod / AG Grid / vitest (frontend).

**Spec:** `docs/superpowers/specs/2026-06-05-collection-type-design.md`

**Enum values:** `generic` (default), `reference_set`, `library`, `hit_list`, `series`, `distribution_set`.

---

## File Structure

**Backend — create:**
- `backend/alembic/versions/052_collection_type.py` — migration adding the column.

**Backend — modify:**
- `backend/src/cellar/domain/research_organization/enums.py` — `CollectionType` enum.
- `backend/src/cellar/domain/research_organization/collection.py` — `type` field on aggregate.
- `backend/src/cellar/domain/research_organization/events.py` — `type` on `CollectionCreated`.
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/models.py` — ORM column.
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/collection_repository.py` — mapping both directions.
- `backend/src/cellar/application/research_organization/create_collection.py` — command field.
- `backend/src/cellar/application/research_organization/update_collection.py` — command field.
- `backend/src/cellar/application/research_organization/close_campaign.py` — emit `hit_list`.
- `backend/src/cellar/interface/routes/collections.py` — request/response schemas + wiring.

**Backend — tests:**
- `backend/tests/unit/domain/research_organization/test_collection.py`
- `backend/tests/api/test_collections.py`

**Frontend — modify:**
- `frontend/src/features/research-organization/types/index.ts` — union type, labels, interfaces.
- `frontend/src/features/research-organization/components/create-collection-dialog.tsx` — Type select.
- `frontend/src/features/research-organization/components/collection-list.tsx` — dashboard column.
- `frontend/src/features/research-organization/components/collection/collection-header.tsx` — detail badge.
- `frontend/src/features/research-organization/components/collection-detail.tsx` — pass `type` to header.

**Frontend — tests:**
- `frontend/src/features/research-organization/components/collection/collection-header.test.tsx`

---

## Task 1: Domain — `CollectionType` enum

**Files:**
- Modify: `backend/src/cellar/domain/research_organization/enums.py`
- Test: `backend/tests/unit/domain/research_organization/test_collection.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/unit/domain/research_organization/test_collection.py` (top-level, after the existing imports add the import, and append this test class at end of file):

```python
from cellar.domain.research_organization.enums import CollectionType


class TestCollectionType:
    def test_values(self) -> None:
        assert CollectionType.GENERIC.value == "generic"
        assert CollectionType.REFERENCE_SET.value == "reference_set"
        assert CollectionType.LIBRARY.value == "library"
        assert CollectionType.HIT_LIST.value == "hit_list"
        assert CollectionType.SERIES.value == "series"
        assert CollectionType.DISTRIBUTION_SET.value == "distribution_set"

    def test_constructable_from_string(self) -> None:
        assert CollectionType("library") is CollectionType.LIBRARY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/domain/research_organization/test_collection.py::TestCollectionType -v`
Expected: FAIL with `ImportError` / `AttributeError: CollectionType`.

- [ ] **Step 3: Add the enum**

In `backend/src/cellar/domain/research_organization/enums.py`, add this class after `CollectionVisibility` (around line 22):

```python
class CollectionType(StrEnum):
    GENERIC = "generic"
    REFERENCE_SET = "reference_set"
    LIBRARY = "library"
    HIT_LIST = "hit_list"
    SERIES = "series"
    DISTRIBUTION_SET = "distribution_set"
```

Then add `"CollectionType",` to the `__all__` list (keep alphabetical — place it after `"CollectionBooleanOp"` is not present in `__all__`; insert between `"CampaignStatus"` and `"ChannelSourceKind"`):

```python
__all__ = [
    "CampaignDecision",
    "CampaignStatus",
    "ChannelSourceKind",
    "CollectionBooleanOp",
    "CollectionType",
    "CollectionVisibility",
    "HitCall",
    "ProjectStatus",
    "QualifierHandling",
    "SearchVisibility",
    "SelectionRule",
    "ValueQualifier",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/domain/research_organization/test_collection.py::TestCollectionType -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd backend
git add src/cellar/domain/research_organization/enums.py tests/unit/domain/research_organization/test_collection.py
git commit -m "feat(research-org): add CollectionType enum"
```

---

## Task 2: Domain — `type` field on `Collection` aggregate

**Files:**
- Modify: `backend/src/cellar/domain/research_organization/collection.py`
- Modify: `backend/src/cellar/domain/research_organization/events.py`
- Test: `backend/tests/unit/domain/research_organization/test_collection.py`

- [ ] **Step 1: Write the failing tests**

Append to `TestCollectionType` is not the right home — add a new class at the end of `test_collection.py`:

```python
class TestCollectionTypeOnAggregate:
    def test_defaults_to_generic(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        collection = Collection.create(workspace_id=ws_id, name="C", created_by=user_id)
        assert collection.type is CollectionType.GENERIC

    def test_factory_accepts_explicit_type(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        collection = Collection.create(
            workspace_id=ws_id,
            name="C",
            created_by=user_id,
            type=CollectionType.LIBRARY,
        )
        assert collection.type is CollectionType.LIBRARY

    def test_created_event_carries_type(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        collection = Collection.create(
            workspace_id=ws_id,
            name="C",
            created_by=user_id,
            type=CollectionType.HIT_LIST,
        )
        events = collection.collect_events()
        assert isinstance(events[0], CollectionCreated)
        assert events[0].type == "hit_list"

    def test_update_changes_type(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        collection = Collection.create(workspace_id=ws_id, name="C", created_by=user_id)
        collection.update(type=CollectionType.SERIES)
        assert collection.type is CollectionType.SERIES

    def test_update_omitting_type_leaves_it_unchanged(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        collection = Collection.create(
            workspace_id=ws_id, name="C", created_by=user_id, type=CollectionType.LIBRARY
        )
        collection.update(name="renamed")
        assert collection.type is CollectionType.LIBRARY

    def test_frozen_collection_rejects_type_change(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        collection = Collection.create(workspace_id=ws_id, name="C", created_by=user_id)
        collection.freeze(derived_from_campaign_id=uuid.uuid4())
        with pytest.raises(CollectionFrozenError):
            collection.update(type=CollectionType.HIT_LIST)
```

Add the needed import at the top of the test file if not already present:

```python
from cellar.domain.shared.errors import CollectionFrozenError, ValidationError
```

(The file already imports `ValidationError`; extend that line to include `CollectionFrozenError`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/domain/research_organization/test_collection.py::TestCollectionTypeOnAggregate -v`
Expected: FAIL — `Collection.create() got an unexpected keyword argument 'type'`.

- [ ] **Step 3: Add `type` to the `CollectionCreated` event**

In `backend/src/cellar/domain/research_organization/events.py`, change the `CollectionCreated` dataclass (lines 21-23):

```python
@dataclass(frozen=True, kw_only=True)
class CollectionCreated(DomainEvent):
    name: str
    type: str
```

- [ ] **Step 4: Add `type` to the aggregate**

In `backend/src/cellar/domain/research_organization/collection.py`:

Update the import on line 8:

```python
from cellar.domain.research_organization.enums import CollectionType, CollectionVisibility
```

In `__init__`, add the parameter (after `visibility`, around line 35) and store it. The new signature gains:

```python
        type: CollectionType = CollectionType.GENERIC,
```

and inside the body, after `self.visibility = visibility` (line 52):

```python
        self.type = type
```

In `create()`, add the parameter (after `visibility`, around line 66):

```python
        type: CollectionType = CollectionType.GENERIC,
```

pass it into the constructor call (after `visibility=visibility,`):

```python
            type=type,
```

and add `type` to the `CollectionCreated` event payload (after `name=collection.name,`):

```python
                type=collection.type.value,
```

In `update()`, add the parameter (after `visibility`, around line 94):

```python
        type: CollectionType | None = None,
```

and inside the body, after the `visibility` block (after line 114 `self.visibility = visibility`):

```python
        if type is not None:
            self.type = type
```

(The frozen-guard at the top of `update()` already raises before reaching here, so frozen collections reject type changes for free.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/domain/research_organization/test_collection.py -v`
Expected: PASS (all collection domain tests, including the new class).

- [ ] **Step 6: Commit**

```bash
cd backend
git add src/cellar/domain/research_organization/collection.py src/cellar/domain/research_organization/events.py tests/unit/domain/research_organization/test_collection.py
git commit -m "feat(research-org): add type field to Collection aggregate"
```

---

## Task 3: Persistence — ORM column + repository mapping

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/models.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/collection_repository.py`
- Create: `backend/alembic/versions/052_collection_type.py`
- Create: `backend/tests/integration/research_organization/test_collection_type_persistence.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/integration/research_organization/test_collection_type_persistence.py`. This mirrors the `uow: AsyncUnitOfWork` fixture pattern used by `test_collection_frozen_membership.py` in the same directory (repo constructed as `SQLAlchemyCollectionRepository(uow)` inside an `async with uow:` block):

```python
"""Round-trip the Collection.type attribute through the repository."""

from __future__ import annotations

import uuid

from cellar.domain.research_organization.collection import Collection
from cellar.domain.research_organization.enums import CollectionType
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (
    SQLAlchemyCollectionRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class TestCollectionTypePersistence:
    async def test_type_round_trips(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            coll = Collection.create(
                workspace_id=ws_id,
                name="Kinase Library",
                created_by=uuid.uuid4(),
                type=CollectionType.LIBRARY,
            )
            await repo.save(coll)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            loaded = await repo.find_by_id_in_workspace(ws_id, coll.id)

        assert loaded is not None
        assert loaded.type is CollectionType.LIBRARY

    async def test_default_type_is_generic(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            coll = Collection.create(
                workspace_id=ws_id, name="Ad-hoc", created_by=uuid.uuid4()
            )
            await repo.save(coll)
            await uow.commit()

        async with uow:
            repo = SQLAlchemyCollectionRepository(uow)
            loaded = await repo.find_by_id_in_workspace(ws_id, coll.id)

        assert loaded is not None
        assert loaded.type is CollectionType.GENERIC
```

> The `uow` fixture is the shared async-DB fixture used across
> `tests/integration/research_organization/`. Open
> `test_collection_frozen_membership.py` to confirm the exact import paths
> (`AsyncUnitOfWork`, `SQLAlchemyCollectionRepository`) — they are copied from
> there verbatim above.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/research_organization/test_collection_type_persistence.py -v`
Expected: FAIL — column `type` does not exist / `CollectionModel` has no attribute `type`.

- [ ] **Step 3: Add the ORM column**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/models.py`, inside `CollectionModel` (after the `visibility` column, around line 93):

```python
    type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="generic")
```

- [ ] **Step 4: Map `type` in the repository (both directions)**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/collection_repository.py`:

Update the import for `CollectionType` — find the existing line that imports `CollectionVisibility` (used in `_to_domain`) and extend it. It is currently imported via the collection module; add:

```python
from cellar.domain.research_organization.enums import CollectionType
```

(If `CollectionVisibility` is imported from `...collection`, leave that import as-is and add the new `CollectionType` import from `...enums`.)

In `_to_domain` (around line 43, after `visibility=CollectionVisibility(model.visibility),`):

```python
            type=CollectionType(model.type),
```

In `_to_model` (around line 66, after `visibility=aggregate.visibility.value,`):

```python
            type=aggregate.type.value,
```

In `_update_model` (around line 77, after `model.visibility = aggregate.visibility.value`):

```python
        model.type = aggregate.type.value
```

- [ ] **Step 5: Create the Alembic migration**

Create `backend/alembic/versions/052_collection_type.py`:

```python
"""collection type attribute

Adds a ``type`` column to ``collections`` categorizing each collection by its
role in the screening cascade (generic | reference_set | library | hit_list |
series | distribution_set). Existing rows backfill to ``generic`` via the
server default.

Revision ID: 052_collection_type
Revises: 051_protocol_run_targets_m2m
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "052_collection_type"
down_revision = "051_protocol_run_targets_m2m"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collections",
        sa.Column(
            "type",
            sa.String(length=32),
            nullable=False,
            server_default="generic",
        ),
    )


def downgrade() -> None:
    op.drop_column("collections", "type")
```

- [ ] **Step 6: Apply the migration to the test/dev DB**

Run: `cd backend && uv run alembic upgrade head`
Expected: applies `052_collection_type` with no error. (If the integration suite spins up its own schema via metadata `create_all`, this step still validates the migration is well-formed; run `uv run alembic upgrade head` then `uv run alembic downgrade -1` then `uv run alembic upgrade head` to confirm reversibility.)

- [ ] **Step 7: Run the integration test to verify it passes**

Run: `cd backend && uv run pytest tests/integration/research_organization/test_collection_type_persistence.py -v`
Expected: PASS (2 passed).

- [ ] **Step 8: Commit**

```bash
cd backend
git add src/cellar/infrastructure/persistence/sqlalchemy/research_organization/models.py src/cellar/infrastructure/persistence/sqlalchemy/research_organization/collection_repository.py alembic/versions/052_collection_type.py tests/integration/research_organization/test_collection_type_persistence.py
git commit -m "feat(research-org): persist Collection.type with migration 052"
```

---

## Task 4: Application — thread `type` through commands

**Files:**
- Modify: `backend/src/cellar/application/research_organization/create_collection.py`
- Modify: `backend/src/cellar/application/research_organization/update_collection.py`
- Modify: `backend/src/cellar/application/research_organization/close_campaign.py`
- Test: `backend/tests/unit/domain/research_organization/test_collection.py` is domain-only; application behavior is covered by the API tests in Task 5 and the campaign-close assertion below.

- [ ] **Step 1: Write the failing test (campaign close emits `hit_list`)**

The integration test `tests/integration/application/research_organization/test_close_campaign.py::test_close_campaign_integration` already loads the published collection into a variable `coll` and asserts it is frozen (around lines 273-277):

```python
    assert coll is not None
    assert coll.is_frozen is True
    assert coll.derived_from_campaign_id == campaign.id
```

Immediately after that block, add the type assertion (and add `from cellar.domain.research_organization.enums import CollectionType` to the file's imports):

```python
    assert coll.type is CollectionType.HIT_LIST
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/integration/application/research_organization/test_close_campaign.py::test_close_campaign_integration -v`
Expected: FAIL — `coll.type` is `CollectionType.GENERIC`, not `HIT_LIST`.

- [ ] **Step 3: Set `type=HIT_LIST` in `close_campaign.py`**

In `backend/src/cellar/application/research_organization/close_campaign.py`, add this import near the other research-org domain imports:

```python
from cellar.domain.research_organization.enums import CollectionType
```

Then in the `Collection.create(...)` call (around line 236), add `type=CollectionType.HIT_LIST` after `created_by=input.user_id,`:

```python
                coll = Collection.create(
                    workspace_id=campaign.workspace_id,
                    name=f"Hits — {campaign.name}",
                    description=(f'Frozen output of campaign "{campaign.name}"'),
                    project_id=campaign.project_id,
                    created_by=input.user_id,
                    type=CollectionType.HIT_LIST,
                )
```

- [ ] **Step 4: Add `type` to `CreateCollectionCommand`**

In `backend/src/cellar/application/research_organization/create_collection.py`:

Update the domain import on line 14 to also bring in `CollectionType`:

```python
from cellar.domain.research_organization.collection import Collection, CollectionVisibility
from cellar.domain.research_organization.enums import CollectionType
```

Add the command field (after `visibility: str = "private"`, line 27):

```python
    type: str = "generic"
```

Pass it into `Collection.create` (after `visibility=CollectionVisibility(input.visibility),`, line 54):

```python
                type=CollectionType(input.type),
```

- [ ] **Step 5: Add `type` to `UpdateCollectionCommand`**

In `backend/src/cellar/application/research_organization/update_collection.py`:

Add the `CollectionType` import (after the existing collection import on line 16):

```python
from cellar.domain.research_organization.enums import CollectionType
```

Add the command field (after `visibility: str | object = UNSET`, line 29):

```python
    type: str | object = UNSET
```

Add to the `fields` builder (after the `visibility` block, around line 68):

```python
            if input.type is not UNSET:
                fields["type"] = CollectionType(input.type)
```

- [ ] **Step 6: Run the campaign-close test to verify it passes**

Run: `cd backend && uv run pytest <path-to-close-campaign-test> -v`
Expected: PASS.

- [ ] **Step 7: Run the full research-org application/integration suite**

Run: `cd backend && uv run pytest tests/unit/domain/research_organization tests/integration/research_organization -v`
Expected: PASS (no regressions).

- [ ] **Step 8: Commit**

```bash
cd backend
git add src/cellar/application/research_organization/create_collection.py src/cellar/application/research_organization/update_collection.py src/cellar/application/research_organization/close_campaign.py tests/
git commit -m "feat(research-org): thread Collection.type through commands; campaign emits hit_list"
```

---

## Task 5: API — request/response schemas + wiring

**Files:**
- Modify: `backend/src/cellar/interface/routes/collections.py`
- Test: `backend/tests/api/test_collections.py`

- [ ] **Step 1: Write the failing API tests**

`backend/tests/api/test_collections.py` groups tests into classes (`TestCreateCollection`, `TestUpdateCollection`, …) whose async methods take `self, client: AsyncClient` and hit the `/api/v1/collections` prefix. Add a new class at the end of the file:

```python
class TestCollectionTypeAttribute:
    async def test_create_defaults_type_generic(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/collections", json={"name": "Ad-hoc set"})
        assert resp.status_code == 201
        assert resp.json()["type"] == "generic"

    async def test_create_with_explicit_type(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/collections", json={"name": "Kinase Lib", "type": "library"}
        )
        assert resp.status_code == 201
        assert resp.json()["type"] == "library"

    async def test_patch_type(self, client: AsyncClient) -> None:
        created = await client.post("/api/v1/collections", json={"name": "X"})
        cid = created.json()["id"]
        resp = await client.patch(
            f"/api/v1/collections/{cid}", json={"type": "series"}
        )
        assert resp.status_code == 200
        assert resp.json()["type"] == "series"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/api/test_collections.py::TestCollectionTypeAttribute -v`
Expected: FAIL — response has no `type` key (KeyError on `resp.json()["type"]`).

- [ ] **Step 3: Add `type` to `CollectionResponse`**

In `backend/src/cellar/interface/routes/collections.py`, in `CollectionResponse` (after `visibility: str`, line 63):

```python
    type: str
```

and in `from_domain` (after `visibility=coll.visibility.value,`, line 79):

```python
            type=coll.type.value,
```

- [ ] **Step 4: Add `type` to the request bodies**

In `CreateCollectionBody` (after `visibility: str = "private"`, line 91):

```python
    type: str = "generic"
```

In `UpdateCollectionBody` (after `visibility: str | None = None`, line 99):

```python
    type: str | None = None
```

- [ ] **Step 5: Wire the bodies into the commands**

In the `create_collection` route handler, in the `CreateCollectionCommand(...)` construction (after `visibility=body.visibility,`, line 239):

```python
        type=body.type,
```

In the `update_collection` route handler, in the `UpdateCollectionCommand(...)` construction (after the `visibility=...` line 260):

```python
        type=body.type if "type" in provided else UNSET,
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/api/test_collections.py -v`
Expected: PASS (existing + 3 new).

- [ ] **Step 7: Commit**

```bash
cd backend
git add src/cellar/interface/routes/collections.py tests/api/test_collections.py
git commit -m "feat(research-org): expose Collection.type over the REST API"
```

---

## Task 6: Frontend — regenerate orval + types

**Files:**
- Modify: `frontend/src/features/research-organization/types/index.ts`

- [ ] **Step 1: Regenerate the orval model from the live OpenAPI**

With the backend running on `:8000`:

Run: `cd frontend && pnpm generate:api`
Expected: `frontend/src/shared/lib/api/model/` updates; review the diff to confirm `CollectionResponse` gained `type` and no unrelated schema was removed. (Per CLAUDE.md, regen is additive but review the diff; orval never prunes `model/index.ts`.)

- [ ] **Step 2: Add the union type + label map + interface fields**

In `frontend/src/features/research-organization/types/index.ts`, add after the `SearchVisibility` type (around line 17):

```typescript
export type CollectionType =
  | "generic"
  | "reference_set"
  | "library"
  | "hit_list"
  | "series"
  | "distribution_set";

export const COLLECTION_TYPE_LABELS: Record<CollectionType, string> = {
  generic: "Generic",
  reference_set: "Reference Set",
  library: "Library",
  hit_list: "Hit List",
  series: "Series",
  distribution_set: "Distribution Set",
};

export const COLLECTION_TYPE_OPTIONS: { value: CollectionType; label: string }[] = [
  { value: "generic", label: "Generic" },
  { value: "reference_set", label: "Reference Set" },
  { value: "library", label: "Library" },
  { value: "hit_list", label: "Hit List" },
  { value: "series", label: "Series" },
  { value: "distribution_set", label: "Distribution Set" },
];
```

In the `Collection` interface (after `visibility: "private" | "shared";`, line 62):

```typescript
  type: CollectionType;
```

In `CreateCollectionInput` (after `visibility?: "private" | "shared";`, line 142):

```typescript
  type?: CollectionType;
```

In `UpdateCollectionInput` (after `visibility?: "private" | "shared";`, line 150):

```typescript
  type?: CollectionType;
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS (no type errors introduced — components don't yet reference `type`, so this should be clean).

- [ ] **Step 4: Commit**

```bash
cd frontend
git add src/features/research-organization/types/index.ts src/shared/lib/api/model/
git commit -m "feat(research-org): add CollectionType to frontend types + regen orval"
```

---

## Task 7: Frontend — Type select in the create/edit dialog

**Files:**
- Modify: `frontend/src/features/research-organization/components/create-collection-dialog.tsx`

- [ ] **Step 1: Add `type` to the form schema + defaults**

In `create-collection-dialog.tsx`:

Extend the import from `../types` (line 30) to include the options:

```typescript
import { type Collection, COLLECTION_TYPE_OPTIONS } from "../types";
```

In `formSchema` (after the `visibility` line, line 37):

```typescript
  type: z.enum([
    "generic",
    "reference_set",
    "library",
    "hit_list",
    "series",
    "distribution_set",
  ]),
```

In `makeDefaultValues` return (after `visibility: "private",`, line 51):

```typescript
    type: "generic",
```

In `toFormValues` return (after `visibility: collection.visibility ?? "private",`, line 60):

```typescript
    type: collection.type ?? "generic",
```

- [ ] **Step 2: Add `type` to the submit payload**

In `onSubmit` (in the `payload` object, after `visibility: values.visibility,`, line 117):

```typescript
      type: values.type,
```

- [ ] **Step 3: Render the Type select**

In the JSX, add a new field block immediately after the Visibility block (after line 184, the closing `</div>` of the visibility group):

```tsx
            <div className="grid gap-2">
              <Label>Type</Label>
              <Controller
                name="type"
                control={form.control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {COLLECTION_TYPE_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
```

- [ ] **Step 4: Typecheck + lint**

Run: `cd frontend && pnpm tsc --noEmit && pnpm biome check src/features/research-organization/components/create-collection-dialog.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd frontend
git add src/features/research-organization/components/create-collection-dialog.tsx
git commit -m "feat(research-org): collection Type select in create/edit dialog"
```

---

## Task 8: Frontend — Type column on the collection dashboard

**Files:**
- Modify: `frontend/src/features/research-organization/components/collection-list.tsx`

- [ ] **Step 1: Import the label map**

In `collection-list.tsx`, add to the imports from `../types` (find the existing `import type { Collection } ...` and convert/extend it):

```typescript
import { type Collection, COLLECTION_TYPE_LABELS } from "../types";
```

- [ ] **Step 2: Add the Type column**

In the `columnDefs` array, insert a new column after the `Visibility` column block (after line 90, the closing `},` of the Visibility column):

```tsx
      {
        headerName: "Type",
        field: "type",
        width: 130,
        cellRenderer: (params: ICellRendererParams<Collection>) => (
          <Badge variant="outline">
            {COLLECTION_TYPE_LABELS[params.value as keyof typeof COLLECTION_TYPE_LABELS] ??
              params.value}
          </Badge>
        ),
      },
```

- [ ] **Step 3: Typecheck + lint**

Run: `cd frontend && pnpm tsc --noEmit && pnpm biome check src/features/research-organization/components/collection-list.tsx`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
cd frontend
git add src/features/research-organization/components/collection-list.tsx
git commit -m "feat(research-org): Type column on the collection dashboard"
```

---

## Task 9: Frontend — Type badge on the detail header

**Files:**
- Modify: `frontend/src/features/research-organization/components/collection/collection-header.tsx`
- Modify: `frontend/src/features/research-organization/components/collection-detail.tsx`
- Test: `frontend/src/features/research-organization/components/collection/collection-header.test.tsx`

- [ ] **Step 1: Write the failing test**

In `collection-header.test.tsx`, add `type: "library"` to `baseCollection` (after `is_frozen: false,`, line 25):

```typescript
  type: "library" as const,
```

and add a new test inside the `describe` block:

```typescript
  it("renders the collection type badge", () => {
    render(<CollectionHeader collection={baseCollection} projectName="Mtb-TB" />);
    expect(screen.getByText("Library")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/collection/collection-header.test.tsx`
Expected: FAIL — `Unable to find an element with the text: Library` (and a TS error that `type` is not on `CollectionHeaderData`).

- [ ] **Step 3: Add `type` to `CollectionHeaderData` + render the badge**

In `collection-header.tsx`:

Add the import at the top (after the existing imports, e.g. after line 7):

```typescript
import { type CollectionType, COLLECTION_TYPE_LABELS } from "../../types";
```

Add to `CollectionHeaderData` (after `is_frozen?: boolean;`, line 18):

```typescript
  type?: CollectionType;
```

Render the badge in the meta strip — add immediately after the visibility `</Badge>` (after line 50):

```tsx
          {collection.type && (
            <Badge variant="outline" className="text-xs">
              {COLLECTION_TYPE_LABELS[collection.type]}
            </Badge>
          )}
```

- [ ] **Step 4: Pass `type` from `collection-detail.tsx`**

In `collection-detail.tsx`, find the object literal passed as `collection={{ ... }}` to `CollectionHeader` (around lines 193-202, which sets `name`, `visibility`, `molecule_count`, `is_frozen`). Add:

```typescript
                type: collection.type,
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/collection/collection-header.test.tsx`
Expected: PASS (all header tests, including the new one).

- [ ] **Step 6: Typecheck + lint**

Run: `cd frontend && pnpm tsc --noEmit && pnpm biome check src/features/research-organization/components/collection`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd frontend
git add src/features/research-organization/components/collection/collection-header.tsx src/features/research-organization/components/collection/collection-header.test.tsx src/features/research-organization/components/collection-detail.tsx
git commit -m "feat(research-org): Type badge on the collection detail header"
```

---

## Task 10: Full verification

- [ ] **Step 1: Backend — full research-org suite + lint**

Run: `cd backend && uv run pytest tests/unit/domain/research_organization tests/integration/research_organization tests/api/test_collections.py -v && uv run ruff check src/cellar/domain/research_organization src/cellar/application/research_organization src/cellar/interface/routes/collections.py`
Expected: all PASS, no lint errors.

- [ ] **Step 2: Frontend — typecheck + targeted tests + lint**

Run: `cd frontend && pnpm tsc --noEmit && pnpm vitest run src/features/research-organization && pnpm biome check src/features/research-organization`
Expected: all PASS.

- [ ] **Step 3: Manual smoke (optional but recommended)**

Start backend + frontend, open the Collections page:
- Create a collection → Type select defaults to "Generic"; pick "Library" → dashboard shows a "Library" badge in the Type column.
- Open the detail → header shows the "Library" badge.
- Close a publishing campaign → its emitted "Hits — …" collection shows type "Hit List".

- [ ] **Step 4: Push the branch**

```bash
git push
```

---

## Notes for the implementer

- **`type` shadows the Python builtin** in domain/command signatures. This matches the existing codebase style (`id`, `input` are used the same way), so ruff's builtin-shadow rules are already configured to allow it. Do not rename to `collection_type` — the spec and API field are `type`.
- **Frozen collections** reject *all* edits via the existing guard at the top of `Collection.update()`; the `type` change is blocked for free. No separate guard needed.
- **Campaign-published** collections are created with `type=hit_list`; **boolean-composed** collections keep the `generic` default (no change to `compose_collections.py`).
- **No type-driven behavior** is in scope — only data model + display. The enum *enables* future behavior (reference-set controls, library import flows, distribution-set export, series SAR hooks) without committing to it now.
