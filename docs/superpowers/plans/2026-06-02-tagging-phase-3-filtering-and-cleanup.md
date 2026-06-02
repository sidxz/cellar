# Tagging — Phase 3: Filtering Integration + Legacy Column Cleanup

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make tags a first-class filter — a `tag` criterion in the molecule advanced-search composer (so it round-trips through SavedSearch) and `tags`/`tag_logic` params on the project/collection/protocol list endpoints — then retire the legacy `molecules.tags` column and its read/write path now that the tagging system is the single source of truth.

**Architecture:** Filtering reuses the Phase-1 link tables via one shared `tag_filter_subquery(link_model, attr, tag_ids, match_all)` helper that builds an `id IN (subquery)` clause (mirrors the existing `_collection_clause`). The cleanup removes all 9 backend readers/writers of `Molecule.tags` (audited) and drops the column in migration 048 — the frontend has **no** functional dependency on the old path (confirmed: no component reads `molecule.tags` or sends `add_tags`/`remove_tags`), so there is no UI regression.

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 async, FastAPI, Alembic, pytest + testcontainers.

**Spec:** `docs/superpowers/specs/2026-06-02-tagging-design.md` §6 (filtering), §7 (migration landmines), §5.5 (migration 048). Builds on Phases 1–2.

**Branch:** `kvt`.

> **Scope note — outward-facing API change:** Tasks R1–R3 remove `tags` from `MoleculeResponse` and remove `add_tags`/`remove_tags` from the `PATCH /molecules/{id}` body. This is a deliberate, spec-mandated contract change (tags now flow exclusively through the Phase-2 `/{entity}/{id}/tags` API). The audit confirmed no frontend component uses these fields; stale orval types are regenerated in Phase 5.

---

## File Structure

### New
| Path | Responsibility |
|------|----------------|
| `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_filter.py` | `tag_filter_subquery` — shared `Select` of entity ids carrying given tags (any/all). |
| `backend/alembic/versions/048_drop_molecules_tags.py` | Drop the legacy `molecules.tags` column. |
| `backend/tests/integration/test_tag_filtering.py` | Composer `tag` criterion + per-entity list-filter integration tests. |

### Modified — filtering (additive)
| Path | Change |
|------|--------|
| `…/chemical_registration/_field_clauses.py` | Add `_tag_clause`. |
| `…/chemical_registration/search_query_composer.py` | Dispatch `type: "tag"` (top level + group recursion + `__all__`). |
| `interface/routes/projects.py`, `…/collections.py`, `…/protocols.py` | Add `tags`/`tag_logic` query params. |
| `application/research_organization/get_project.py`, `…/get_collection.py`, `application/screening/get_protocol.py` | Add `tags`/`tag_logic` to the list queries. |
| `…/research_organization/project_repository.py`, `…/collection_repository.py`, `…/screening_assay/protocol_repository.py` | Apply the tag filter in `find_by_workspace` (+ protocol `find_by_project`). |

### Modified — cleanup (subtractive)
| Path | Change |
|------|--------|
| `domain/chemical_registration/molecule.py` | Remove `tags` field/param + `update_tags`. |
| `domain/chemical_registration/events.py` | Remove `MoleculeTagsUpdated`. |
| `…/chemical_registration/molecule_mapping.py` | Stop reading `model.tags`. |
| `…/chemical_registration/molecule_repository.py` | Stop writing `model.tags`. |
| `…/chemical_registration/models.py` | Remove the `tags` column. |
| `interface/routes/molecules.py` | Remove `MoleculeResponse.tags` + `add_tags`/`remove_tags` body fields. |
| `application/chemical_registration/update_molecule.py` | Remove `add_tags`/`remove_tags` + the `update_tags` call. |
| `application/chemical_registration/merge_service.py` | Remove the `tags` snapshot entry. |
| `tests/unit/domain/chemical_registration/test_molecule.py` + affected API/unit tests | Remove old-tag tests/fixtures. |

---

## Task F1: Tag filter helper + composer `tag` criterion

**Files:**
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_filter.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_field_clauses.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/search_query_composer.py`
- Test: `backend/tests/integration/test_tag_filtering.py`

- [ ] **Step 1: Write the shared subquery helper**

Create `backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_filter.py`:

```python
"""Shared tag-filter subquery builder, reused by the search composer and the
per-entity list repositories. Returns a Select of entity ids that carry the
given tags (``match_all=False`` = any of them; ``match_all=True`` = all of them).
"""

from __future__ import annotations

import uuid

from sqlalchemy import distinct, func, select
from sqlalchemy.sql import Select


def tag_filter_subquery(
    link_model: type,
    entity_id_attr: str,
    tag_ids: list[uuid.UUID],
    *,
    match_all: bool,
) -> Select:
    col = getattr(link_model, entity_id_attr)
    unique_ids = list(dict.fromkeys(tag_ids))  # dedup, preserve order
    stmt = select(col).where(link_model.tag_id.in_(unique_ids))
    if match_all:
        stmt = stmt.group_by(col).having(
            func.count(distinct(link_model.tag_id)) == len(unique_ids)
        )
    else:
        stmt = stmt.distinct()
    return stmt
```

- [ ] **Step 2: Write the failing integration test**

Create `backend/tests/integration/test_tag_filtering.py` with the composer test (the per-entity tests are added in F2):

```python
"""Integration tests for tag filtering (composer criterion + list endpoints)."""

from __future__ import annotations

import uuid

from sqlalchemy import select, text

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (
    compose_criteria,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    MoleculeTagLinkRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_repository import (
    SQLAlchemyTagRepository,
)
from cellar.domain.workspace_config.tagging.tag import TagName
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


async def _org_and_molecule(uow: AsyncUnitOfWork, ws: uuid.UUID, reg: str) -> uuid.UUID:
    org_id, mol_id = uuid.uuid4(), uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, "
            "version) VALUES (:id, :ws, :n, 'internal', true, 1)"
        ),
        {"id": org_id, "ws": ws, "n": f"org-{reg}"},
    )
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, "
            "molecule_type, version, originating_org_id) VALUES "
            "(:id, :ws, :r, :r, 'small_molecule', 1, :org)"
        ),
        {"id": mol_id, "ws": ws, "r": reg, "org": org_id},
    )
    return mol_id


class TestComposerTagCriterion:
    async def test_filter_any_and_all(self, uow: AsyncUnitOfWork) -> None:
        ws, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            t1 = await tag_repo.get_or_create(ws, TagName(key="a"), user)
            t2 = await tag_repo.get_or_create(ws, TagName(key="b"), user)
            m1 = await _org_and_molecule(uow, ws, "F-1")
            m2 = await _org_and_molecule(uow, ws, "F-2")
            links = MoleculeTagLinkRepository(uow)
            await links.add(ws, m1, t1.id, user)
            await links.add(ws, m1, t2.id, user)
            await links.add(ws, m2, t1.id, user)
            await uow.commit()

        async with uow:
            any_clause = compose_criteria(
                {"criteria": [{"type": "tag", "tag_ids": [str(t1.id), str(t2.id)], "tag_logic": "any"}]},
                workspace_id=ws,
            )
            all_clause = compose_criteria(
                {"criteria": [{"type": "tag", "tag_ids": [str(t1.id), str(t2.id)], "tag_logic": "all"}]},
                workspace_id=ws,
            )
            neg_clause = compose_criteria(
                {"criteria": [{"type": "tag", "tag_ids": [str(t2.id)], "negate": True}]},
                workspace_id=ws,
            )
            base = select(MoleculeModel.id).where(MoleculeModel.workspace_id == ws)
            any_ids = {r for r in (await uow.session.execute(base.where(any_clause))).scalars()}
            all_ids = {r for r in (await uow.session.execute(base.where(all_clause))).scalars()}
            neg_ids = {r for r in (await uow.session.execute(base.where(neg_clause))).scalars()}
        assert any_ids == {m1, m2}
        assert all_ids == {m1}
        assert neg_ids == {m2}  # m2 does NOT have t2
```

> Note: `tag_ids` arrive as strings from JSON; SQLAlchemy compares them against `Uuid` columns fine, but if a comparison fails, coerce with `uuid.UUID(...)` inside `_tag_clause`.

- [ ] **Step 3: Run to verify it fails**

Run (Docker up; up to 600000 ms): `uv run pytest tests/integration/test_tag_filtering.py -v`
Expected: FAIL — `ValueError: Unknown criterion type: tag`.

- [ ] **Step 4: Add `_tag_clause`**

In `_field_clauses.py`, add these imports (near the existing model imports):

```python
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import (
    MoleculeTagLinkModel,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_filter import (
    tag_filter_subquery,
)
```

and add this clause builder (next to `_collection_clause`):

```python
def _tag_clause(criterion: dict[str, Any]) -> ColumnElement:
    """Filter molecules to those carrying the given tag ids (any/all).

    Workspace scoping is already enforced by the outer molecule query (and a
    molecule can only link to tags in its own workspace), so no extra join.
    """
    raw_ids = criterion["tag_ids"]
    if not raw_ids:
        msg = "tag criterion requires at least one tag_id"
        raise ValueError(msg)
    tag_ids = [uuid.UUID(str(t)) for t in raw_ids]
    match_all = criterion.get("tag_logic", "any") == "all"
    return MoleculeModel.id.in_(
        tag_filter_subquery(MoleculeTagLinkModel, "molecule_id", tag_ids, match_all=match_all)
    )
```

- [ ] **Step 5: Register `tag` in the composer**

In `search_query_composer.py`:
- Import `_tag_clause` alongside the other `_field_clauses` imports.
- In the main dispatch chain in `compose_criteria`, add (e.g. after the `keyword_list` branch):
  ```python
  elif ctype == "tag":
      clause = _tag_clause(criterion)
  ```
- In `_group_clause`'s recursive dispatch, add the same branch:
  ```python
  elif ctype == "tag":
      clause = _tag_clause(sub)
  ```
- If the module has an `__all__`, add `"_tag_clause"`.

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/integration/test_tag_filtering.py -v`
Expected: PASS (the any/all/negate assertions hold).

- [ ] **Step 7: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/tagging/tag_filter.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_field_clauses.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/search_query_composer.py \
        backend/tests/integration/test_tag_filtering.py
git commit -m "feat(tagging): tag search criterion + shared filter subquery"
```

---

## Task F2: `tags`/`tag_logic` on project/collection/protocol lists

**Files:**
- Modify routes: `interface/routes/{projects,collections,protocols}.py`
- Modify queries: `application/research_organization/get_project.py`, `…/get_collection.py`, `application/screening/get_protocol.py`
- Modify repos: `…/research_organization/{project_repository,collection_repository}.py`, `…/screening_assay/protocol_repository.py`
- Test: append to `backend/tests/integration/test_tag_filtering.py`

For EACH of the three entities, the change is the same shape:
1. **Query dataclass** — add `tags: list[uuid.UUID] | None = None` and `tag_logic: str = "any"`.
2. **Repository `find_by_workspace`** — add params `tags: list[uuid.UUID] | None = None, tag_logic: str = "any"`, and before ordering/pagination:
   ```python
   if tags:
       stmt = stmt.where(
           <EntityModel>.id.in_(
               tag_filter_subquery(<EntityTagLinkModel>, "<entity>_id", tags, match_all=tag_logic == "all")
           )
       )
   ```
   (import `tag_filter_subquery` from `…tagging.tag_filter` and the link model from `…tagging.models`).
3. **Use case** — pass `tags=input.tags, tag_logic=input.tag_logic` through to the repo call.
4. **Route** — add `tags: list[uuid.UUID] | None = Query(default=None)` and `tag_logic: str = Query(default="any")`, and thread them into the query.

Per-entity specifics:
- **Projects:** `ProjectTagLinkModel`, `"project_id"`; `ProjectModel`; `project_repository.find_by_workspace`.
- **Collections:** `CollectionTagLinkModel`, `"collection_id"`; `CollectionModel`; `collection_repository.find_by_workspace` (apply the tag filter alongside the existing `project_ids` filter, before the cursor/order clauses).
- **Protocols:** `ProtocolTagLinkModel`, `"protocol_id"`; `ProtocolModel`. Apply to BOTH `find_by_workspace` and `find_by_project` (the route dispatches to `ListProtocolsByProject` when `project_id` is set — add `tags`/`tag_logic` to `ListProtocolsByProjectQuery` and `find_by_project` too, so the filter works in both paths).

- [ ] **Step 1: Write the failing integration tests**

Append to `backend/tests/integration/test_tag_filtering.py`:

```python
from cellar.infrastructure.persistence.sqlalchemy.research_organization.project_repository import (
    SQLAlchemyProjectRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_repository import (
    SQLAlchemyCollectionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    get_tag_link_repository,
)
from cellar.domain.workspace_config.tagging.tag import TaggableEntityType


async def _insert_project(uow: AsyncUnitOfWork, ws: uuid.UUID, name: str) -> uuid.UUID:
    pid = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, name, version) "
            "VALUES (:id, :ws, :n, 1)"
        ),
        {"id": pid, "ws": ws, "n": name},
    )
    return pid


class TestProjectListTagFilter:
    async def test_filters_projects_by_tag(self, uow: AsyncUnitOfWork) -> None:
        ws, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws, TagName(key="flagged"), user)
            p1 = await _insert_project(uow, ws, "P-tagged")
            await _insert_project(uow, ws, "P-untagged")
            links = get_tag_link_repository(TaggableEntityType.PROJECT, uow)
            await links.add(ws, p1, tag.id, user)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyProjectRepository(uow)
            rows = await repo.find_by_workspace(ws, tags=[tag.id], tag_logic="any")
        assert {p.id for p in rows} == {p1}
```

> Confirm the exact `INSERT INTO projects` required columns (run `\d projects` or read the model). If projects need more NOT-NULL columns, add the minimal set (mirror the Phase-1/2 molecule helper approach). Add an analogous `TestCollectionListTagFilter` once the projects test passes (collections insert needs only `name`-equivalent NOT-NULL columns + `version`). Protocols may be verified via the same repo-level pattern or deferred to the route's API test if protocol insert is heavy — at minimum cover projects + collections at the repo level.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/integration/test_tag_filtering.py::TestProjectListTagFilter -v`
Expected: FAIL — `find_by_workspace() got an unexpected keyword argument 'tags'`.

- [ ] **Step 3: Implement the three entities (query + repo + use case + route)**

Apply the 4-part shape above to projects, then collections, then protocols. Keep each entity's edit small and run the relevant test after each. Use `tag_filter_subquery` everywhere (no bespoke SQL).

- [ ] **Step 4: Run the filtering tests + a broad smoke**

Run: `uv run pytest tests/integration/test_tag_filtering.py -v`
Expected: PASS (composer + project/collection [+ protocol] filters).
Then: `uv run pytest tests/integration/test_research_organization.py -q` (confirm existing list behavior unbroken).

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/interface/routes/projects.py \
        backend/src/cellar/interface/routes/collections.py \
        backend/src/cellar/interface/routes/protocols.py \
        backend/src/cellar/application/research_organization/get_project.py \
        backend/src/cellar/application/research_organization/get_collection.py \
        backend/src/cellar/application/screening/get_protocol.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/project_repository.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/research_organization/collection_repository.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/protocol_repository.py \
        backend/tests/integration/test_tag_filtering.py
git commit -m "feat(tagging): tags/tag_logic filter on project/collection/protocol lists"
```

---

> **Cleanup execution order — do these READERS-FIRST so every commit stays green: R2 → R1 → R3.**
> `Molecule.update_tags` mutates `self.tags`, and `update_molecule.py` calls `update_tags`, so removing the domain field/method *before* its callers would break the build for a commit. Therefore implement **R2 first** (remove every reader/writer — mapper, application, API, merge snapshot; the domain `tags` field + `update_tags` method remain temporarily but become dead code, so the suite stays green), **then R1** (delete the now-unused domain field/method/event + their domain tests), **then R3** (drop the ORM column + migration 048). After R2 the full unit/app/API suite is green; after R1 it's still green; after R3 the integration suite is green through migration 048. (The tasks are numbered by layer for readability but executed bottom-up.)

## Task R1: Remove legacy tags from the Molecule domain (run AFTER R2)

**Files:**
- Modify: `domain/chemical_registration/molecule.py`, `domain/chemical_registration/events.py`
- Modify: `tests/unit/domain/chemical_registration/test_molecule.py`

- [ ] **Step 1: Confirm the blast radius**

Run `grep -rn "MoleculeTagsUpdated" backend/src backend/tests` and `grep -rn "update_tags" backend/src backend/tests` — these must catch **every** importer/caller across all layers (e.g. an event-handler registration, an `events.py` `__all__`, or an `__init__` re-export), not just the domain module, so nothing dangles after removal. Then `grep -rn "\.tags" backend/src/cellar/domain/chemical_registration/ backend/tests/unit/domain/chemical_registration/` for the field references.
Because **R2 already ran**, the only remaining references should be the definitions themselves: `molecule.py` constructor param + `self.tags` (~117, ~151) + the `update_tags` method (~479-500); `events.py` `MoleculeTagsUpdated` (~49-51); and `test_molecule.py` (~231/236, ~882-936). If the grep surfaces any OTHER live caller/importer of `update_tags`/`MoleculeTagsUpdated` (a handler, registry, or `__all__`), R2 missed it — remove it here (or go back and fix R2) so nothing dangles.

- [ ] **Step 2: Remove from the domain**

In `domain/chemical_registration/molecule.py`:
- Remove the `tags: list[str] | None = None` constructor parameter and the `self.tags: list[str] = list(tags) if tags else []` initialization line.
- Remove the entire `update_tags(self, *, added=..., removed=...)` method.
- Remove the now-unused `MoleculeTagsUpdated` import if present.

In `domain/chemical_registration/events.py`: remove the `MoleculeTagsUpdated` dataclass.

- [ ] **Step 3: Remove the old-tag domain tests**

In `tests/unit/domain/chemical_registration/test_molecule.py`: remove the `tags=[...]` constructor argument + `mol.tags` assertions (~231/236) and the five `update_tags` test methods (~882-936). (The new tag behavior is covered by the tagging suites — do not re-add equivalents here.)

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/unit/domain/chemical_registration/test_molecule.py -q` → PASS.
Run: `grep -rn "update_tags\|MoleculeTagsUpdated\|self.tags\|\.tags" backend/src/cellar/domain/chemical_registration/` → no matches.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/domain/chemical_registration/molecule.py \
        backend/src/cellar/domain/chemical_registration/events.py \
        backend/tests/unit/domain/chemical_registration/test_molecule.py
git commit -m "refactor(tagging): remove legacy Molecule.tags field + update_tags"
```

---

## Task R2: Remove legacy tags from mapper, application, and API

**Files:**
- Modify: `…/chemical_registration/molecule_mapping.py`, `…/chemical_registration/molecule_repository.py`
- Modify: `application/chemical_registration/update_molecule.py`, `application/chemical_registration/merge_service.py`
- Modify: `interface/routes/molecules.py`
- Modify: affected tests (API + application)

- [ ] **Step 1: Persistence mapper**

- In `molecule_mapping.py`: remove `tags=model.tags,` from the `Molecule(...)` construction (the column still exists in the DB until R3, but is no longer read).
- In `molecule_repository.py`: remove the `model.tags = aggregate.tags if aggregate.tags else None` line from `_set_optional_fields`.

- [ ] **Step 2: Application**

- In `update_molecule.py`: remove `add_tags`/`remove_tags` from `UpdateMoleculeCommand` and remove the `if input.add_tags or input.remove_tags: mol.update_tags(...)` block.
- In `merge_service.py`: remove the `"tags": list(molecule.tags),` entry from `_build_snapshot`.

- [ ] **Step 3: API**

In `interface/routes/molecules.py`:
- Remove the `tags: list[str]` field from `MoleculeResponse` and the `tags=mol.tags,` line in its `from_domain`.
- Remove `add_tags`/`remove_tags` from the `UpdateMoleculeBody` and from the `UpdateMoleculeCommand(...)` construction in the PATCH handler.

- [ ] **Step 4: Fix affected tests**

Run: `grep -rn "add_tags\|remove_tags\|\"tags\"\|'tags'\|\.tags" backend/tests/api backend/tests/unit/application/chemical_registration` — update any test that asserts `MoleculeResponse.tags`, sends `add_tags`/`remove_tags`, or asserts the merge snapshot `tags` key. Remove those assertions/inputs (the behavior is gone; tag operations are tested via the tagging suites).

- [ ] **Step 5: Verify**

Run: `uv run pytest tests/unit/application/chemical_registration tests/api/test_molecules.py -q` → PASS.
Run: `grep -rn "mol\.tags\|molecule\.tags\|\.tags=" backend/src/cellar/application backend/src/cellar/interface` → no molecule-tags matches remain.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(tagging): drop legacy molecule tags from mapper/app/API"
```

---

## Task R3: Remove the ORM column + migration 048

**Files:**
- Modify: `…/chemical_registration/models.py`
- Create: `backend/alembic/versions/048_drop_molecules_tags.py`

- [ ] **Step 1: Remove the ORM column**

In `…/chemical_registration/models.py`: remove the `tags: Mapped[list | None] = mapped_column(JSON)` line from `MoleculeModel`. (After R1/R2 nothing reads or writes it; now the ORM model and the soon-to-be-dropped DB column are removed together.)

- [ ] **Step 2: Write migration 048**

Create `backend/alembic/versions/048_drop_molecules_tags.py`:

```python
"""048 — drop the legacy molecules.tags column.

Superseded by the tagging system (tags registry + per-entity link tables,
migration 047). All backend readers/writers were removed in Phase 3.

Revision ID: 048_drop_molecules_tags
Revises: 047_tagging
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "048_drop_molecules_tags"
down_revision = "047_tagging"


def upgrade() -> None:
    op.drop_column("molecules", "tags")


def downgrade() -> None:
    op.add_column(
        "molecules",
        sa.Column("tags", postgresql.JSON(), nullable=True),
    )
```

- [ ] **Step 3: Verify the migration chain + apply**

Run: `uv run alembic history` — confirm `048_drop_molecules_tags` is head, chaining off `047_tagging`.
If a dev DB is available: `uv run alembic upgrade head` → `Running upgrade 047_tagging -> 048_drop_molecules_tags`; then `uv run alembic downgrade -1 && uv run alembic upgrade head` (clean up/down/up). Otherwise the integration tests (which migrate to head) will exercise it.

- [ ] **Step 4: Full regression**

Run (Docker up; up to 600000 ms):
- `uv run pytest tests/integration -q` — all integration tests pass (they now migrate through 048; molecule round-trips work without the column).
- `uv run pytest tests/unit -q` — all unit tests pass (incl. the FK-coverage guard).
- `uv run pytest tests/api -q` — all API tests pass (MoleculeResponse no longer has `tags`).

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/models.py \
        backend/alembic/versions/048_drop_molecules_tags.py
git commit -m "feat(tagging): migration 048 — drop legacy molecules.tags column"
```

---

## Phase 3 Done — Definition of Done

- [ ] `uv run pytest tests/integration/test_tag_filtering.py -v` → pass (composer + per-entity filters).
- [ ] `uv run pytest tests/integration -q`, `tests/unit -q`, `tests/api -q` → all green (no regressions; FK-coverage guard still passes after the column drop).
- [ ] `uv run alembic upgrade head` clean; `molecules.tags` column gone; no backend reference to `Molecule.tags` remains (`grep`).

**Delivered:** tags are filterable through the molecule advanced search (round-tripping via SavedSearch with no schema change) and via `tags`/`tag_logic` on the project/collection/protocol lists; the legacy `molecules.tags` column and its read/write path are fully retired — the tagging system is now the single source of truth.

**Next:** Phase 4 (admin: rename/merge/delete) and Phase 5 (frontend: chips, editor, filter control, management page + orval regen to drop the stale `tags`/`add_tags`/`remove_tags` types).

---

## Implementation Notes — execution findings (2026-06-02)

- **F2** also threaded `tags`/`tag_logic` through `application/screening/manage_protocol.py` (where `ListProtocolsByProjectQuery` + the protocol use cases live) — one more file than the plan listed. Protocols filter on both `find_by_workspace` and `find_by_project`; the by-project path is wired but its dedicated repo test was deferred (identical helper to the tested by-workspace path).
- **R3** removed the Phase-1 `TestBackfill` class from `tests/integration/test_tagging.py` — necessary (it wrote to the now-dropped `molecules.tags`) and safe: migration `047_tagging` + `tagging/backfill_sql.py` remain intact (the backfill is frozen migration history that already ran).
- **Entity-insert test columns:** raw-SQL inserts need `status` (projects), `protocol_type`/`protocol_version` (protocols) — Python-side defaults without server defaults.

**Pre-existing branch failures (NOT caused by the tagging work — proven by running the full integration suite at the pre-tagging baseline `5554e342`, where they already fail):**
- `tests/api/test_molecules.py`: `test_register_disclosed_molecule` (reg-prefix `CC-` vs `CV-` config), `test_tested_molecule_returns_count` (missing `dose_response_curves.intercept_values` column), `test_project_scoped_count` (missing `projects.visibility` column) — schema-drift / config issues.
- `tests/integration/test_backfill_bemis_murcko.py`: `test_backfill_populates_null_rows`, `test_backfill_idempotent` — the test asserts a **global** NULL-`bemis_murcko_smiles` count (`backfill_batch` is called without a `workspace_id`), so any molecule-inserting test contaminates it. **Root-cause fix (optional, separate):** scope the test to its own workspace — `backfill_batch(session, workspace_id=ws_id)` and assert within `ws_id`. (The tagging tests are among many contaminators but not the originators; cleaning up only tagging rows would not fix the test.)

**Final state:** 5 implementation commits (`f0c6ff9f`…`4e96d26c`); migration 048 is the single alembic head; `molecules.tags` gone, no backend reference remains. Targeted regression at HEAD: unit **2594 passed**; integration **211 passed** (+2 pre-existing bemis); api **252 passed** (+3 pre-existing). Reviewed READY.
