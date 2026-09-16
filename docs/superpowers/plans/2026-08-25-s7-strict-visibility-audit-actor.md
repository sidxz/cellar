# S7 — Strict Org Visibility + Admin Bypass + Audit Actor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plates (and org-owned groups/loans/insights) become visible only to their owner org — plus plates on active loan to the caller's org — with workspace admins seeing everything; the per-org `plates_private` opt-in is deleted; every audit row written by the catch-all handler is attributed to the authenticated user instead of a nil SYSTEM actor.

**Architecture:** `PlateVisibilityService.excluded_org_ids()` keeps its exclusion-set contract for its ~24 call sites but computes "every directory org except mine" (empty for admins/system) from a new application-layer `OrgDirectoryPort`, satisfied by the existing Duar `OrgDirectory`. `plates_private` is removed end-to-end (migration 066). A `ContextVar` set in `get_auth` carries the actor id to `AuditRecordingService.handle_event`. The FE hides org selectors and the policy button for non-admins.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2 async / Alembic / Lagom / pytest (testcontainers Postgres for `tests/api`) · Next.js 16 / React 19 / TanStack Query / vitest / biome · orval-generated types.

**Spec:** `docs/superpowers/specs/2026-08-25-plate-tracker-revamp-spec.md` §3 (Visibility) and §4 (Audit actor). Previous spec for context: `docs/superpowers/specs/2026-08-10-inventory-plate-org-loans-spec.md` §5.

## Global Constraints

- Backend commands run from `backend/` with `uv run …`; any `pytest` run that touches `tests/api` or `tests/integration` needs `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock` in the environment (Docker Desktop exposes no `/var/run/docker.sock` on this Mac; testcontainers errors with `Invalid response from docker daemon: key "ApiVersion"` without it); frontend commands run from `frontend/` with the full pnpm path `/Users/sidx/Library/pnpm/pnpm` (bare `pnpm` is broken on this machine).
- Layer rules (CLAUDE.md): Application never imports Infrastructure/Interface. The new port lives in `application/shared/`; the Duar adapter stays in `infrastructure/duar/`.
- Commit with explicit pathspecs: `git commit -m "…" -- <paths>`; `git add <new files>` first for untracked files. Every commit message ends with the two trailer lines shown in Task 1 Step 6.
- Hidden == 404 for plate/loan reads; 403 for org-scoped reads (tree, insights) of a foreign org. Do not change those status codes.
- NULL `owner_org_id` plates stay visible to everyone (unchanged).
- Never loosen a hidden-plate assertion to make a test pass; switch the *caller* to a non-admin fixture instead.
- `docs/` is gitignored; the spec and plan files are force-added (`git add -f`).
- Lint gates are scoped to the files a task touches: `uv run ruff check <changed files>` and `/Users/sidx/Library/pnpm/pnpm biome check <changed files>` must exit 0. Never run ruff/biome `--fix`/`--write` repo-wide — `pnpm lint` and repo-wide ruff are red on `main` for pre-existing reasons (`docs/backlog/preexisting-test-lint-failures-main.md`).
- Tests failing in the BASE baseline (`.superpowers/sdd/2026-08-25-s7-strict-visibility-audit-actor/baseline-*.txt`) are pre-existing: do not fix or adjust them; report them.

---

### Task 1: `OrgDirectoryPort` + strict `PlateVisibilityService` (unit-tested)

**Files:**
- Create: `backend/src/cellar/application/shared/org_directory.py`
- Modify: `backend/src/cellar/application/inventory/plate_visibility.py` (whole file)
- Modify: `backend/tests/unit/application/test_plate_visibility.py` (whole file)
- Modify: `backend/tests/unit/test_export_plate_layout.py:56-64`

**Interfaces:**
- Produces: `OrgDirectoryPort` Protocol with `async def list_orgs(self) -> Sequence[OrgRef]` where `OrgRef` has `.id: uuid.UUID`.
- Produces: `PlateVisibilityService(org_directory: OrgDirectoryPort | None = None, loan_repo: PlateLoanRepository | None = None)`; `excluded_org_ids(workspace_id, auth) -> set[UUID]` = `set()` when `auth is None or auth.is_admin`, else `{o.id for o in directory} - {auth.org_id}`; raises `RuntimeError` when a non-admin caller arrives and no directory is wired. `borrowed_plate_ids`, `can_view`, `can_view_owner` unchanged.

- [ ] **Step 1: Write the failing unit tests**

Replace the whole of `backend/tests/unit/application/test_plate_visibility.py` with:

```python
"""Unit tests for PlateVisibilityService — strict org scoping (spec 2026-08-25 §3)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.domain.inventory.enums import PlateType
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.shared.value_objects import Barcode
from tests.fakes.fake_auth import FakeAuth


class _FakeOrgDirectory:
    """Static OrgDirectoryPort — a fixed set of org ids."""

    def __init__(self, org_ids: set[uuid.UUID] | None = None) -> None:
        self._orgs = [SimpleNamespace(id=i) for i in (org_ids or set())]

    async def list_orgs(self):
        return self._orgs


def _make_plate(owner_org_id: uuid.UUID | None) -> RegisteredPlate:
    return RegisteredPlate.register(
        workspace_id=uuid.uuid4(),
        owner_org_id=owner_org_id,
        barcode=Barcode(value=f"PLT-{uuid.uuid4().hex[:8]}"),
        plate_label="Test Plate",
        format=PlateFormat.F96,
        plate_type=PlateType.MOTHER,
        registered_by=uuid.uuid4(),
    )


class TestExcludedOrgIds:
    async def test_auth_none_is_empty_set(self) -> None:
        service = PlateVisibilityService(_FakeOrgDirectory({uuid.uuid4()}))

        assert await service.excluded_org_ids(uuid.uuid4(), None) == set()

    async def test_admin_is_empty_set(self) -> None:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgDirectory({org_a, org_b}))
        auth = FakeAuth(role="admin", org_id=org_a)

        assert await service.excluded_org_ids(uuid.uuid4(), auth) == set()

    async def test_editor_excludes_every_other_org(self) -> None:
        org_a, org_b, org_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgDirectory({org_a, org_b, org_c}))
        auth = FakeAuth(role="editor", org_id=org_a)

        assert await service.excluded_org_ids(uuid.uuid4(), auth) == {org_b, org_c}

    async def test_editor_without_org_excludes_all(self) -> None:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgDirectory({org_a, org_b}))
        auth = FakeAuth(role="editor", org_id=None)

        assert await service.excluded_org_ids(uuid.uuid4(), auth) == {org_a, org_b}

    async def test_no_directory_fails_closed_for_editor(self) -> None:
        service = PlateVisibilityService()
        auth = FakeAuth(role="editor", org_id=uuid.uuid4())

        with pytest.raises(RuntimeError):
            await service.excluded_org_ids(uuid.uuid4(), auth)

    async def test_no_directory_is_fine_for_admin_and_system(self) -> None:
        service = PlateVisibilityService()

        assert await service.excluded_org_ids(uuid.uuid4(), None) == set()
        assert await service.excluded_org_ids(uuid.uuid4(), FakeAuth(role="admin")) == set()


class TestCanView:
    def test_null_owner_always_viewable(self) -> None:
        service = PlateVisibilityService(_FakeOrgDirectory())
        plate = _make_plate(owner_org_id=None)

        assert service.can_view(plate, FakeAuth(), {uuid.uuid4()}) is True

    def test_owner_in_excluded_not_viewable(self) -> None:
        org_b = uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgDirectory())
        plate = _make_plate(owner_org_id=org_b)

        assert service.can_view(plate, FakeAuth(), {org_b}) is False

    def test_owner_not_in_excluded_is_viewable(self) -> None:
        org_a = uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgDirectory())
        plate = _make_plate(owner_org_id=org_a)

        assert service.can_view(plate, FakeAuth(org_id=org_a), set()) is True

    def test_borrowed_plate_viewable_despite_exclusion(self) -> None:
        org_b = uuid.uuid4()
        service = PlateVisibilityService(_FakeOrgDirectory())
        plate = _make_plate(owner_org_id=org_b)

        assert service.can_view(plate, FakeAuth(), {org_b}, borrowed={plate.id}) is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/application/test_plate_visibility.py -v`
Expected: FAIL — `TypeError`/`AttributeError` (the service still expects a policy repo with `list_private_org_ids`) and `ImportError` is NOT expected (the module exists).

- [ ] **Step 3: Create the port**

Create `backend/src/cellar/application/shared/org_directory.py`:

```python
"""Org directory port — the application layer's view of the IdP's org list.

Satisfied structurally by ``cellar.infrastructure.duar.org_directory.OrgDirectory``
(its ``OrgSummary`` rows carry ``id``); tests pass a static stub.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol, runtime_checkable


class OrgRef(Protocol):
    @property
    def id(self) -> uuid.UUID: ...


@runtime_checkable
class OrgDirectoryPort(Protocol):
    async def list_orgs(self) -> Sequence[OrgRef]: ...
```

- [ ] **Step 4: Rewrite the service**

Replace the whole of `backend/src/cellar/application/inventory/plate_visibility.py` with:

```python
"""PlateVisibilityService — strict org scoping for plates and org-owned things
(spec 2026-08-25 §3), plus the borrowed-plate read carve-out (loan clause)."""

from __future__ import annotations

import uuid

from cellar.application.auth import AuthContext
from cellar.application.shared.org_directory import OrgDirectoryPort
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.repository import PlateLoanRepository


class PlateVisibilityService:
    """Strict rule: a caller sees plates of their own org (plus plates on
    active loan to it — read surfaces only); workspace admins and system
    calls (``auth is None``) see everything.

    ``excluded_org_ids`` returns "every org in the directory except mine" so
    the existing call sites keep their exclusion-set plumbing unchanged.
    # ponytail: an inclusion scope (visible_owner_org_id | None) would drop
    # the directory dependency; only worth the ~20-site refactor if the
    # directory ever proves unreliable.

    Write-path narrowing is deliberate: Update/MapWells/ChangeStatus/Derive/
    Delete, export, tag verbs, and plate groups never fetch a borrowed set
    and call ``can_view``/``can_view_owner`` with their default (empty), so a
    borrower can SEE a loaned plate but not modify it. Only the read surfaces
    — GetPlate, ListPlates, ListChildren, molecule->plates read model — pass
    a real one.
    """

    def __init__(
        self,
        org_directory: OrgDirectoryPort | None = None,
        loan_repo: PlateLoanRepository | None = None,
    ) -> None:
        self._org_directory = org_directory
        self._loan_repo = loan_repo

    async def excluded_org_ids(
        self, workspace_id: uuid.UUID, auth: AuthContext | None
    ) -> set[uuid.UUID]:
        """Every directory org id except the caller's own. Empty for system
        calls and workspace admins. Fails closed (raises) when a non-admin
        caller arrives and no directory is wired."""
        if auth is None or auth.is_admin:
            return set()
        if self._org_directory is None:
            raise RuntimeError(
                "PlateVisibilityService needs an org directory for non-admin callers"
            )
        all_ids = {o.id for o in await self._org_directory.list_orgs()}
        return all_ids - {auth.org_id}

    async def borrowed_plate_ids(
        self, workspace_id: uuid.UUID, auth: AuthContext | None
    ) -> set[uuid.UUID]:
        """Plates currently on active loan to the caller's own org (spec §5).
        Empty when there's no loan repo wired, no caller, or the caller has
        no org — system calls never re-admit anything this way."""
        if self._loan_repo is None or auth is None or auth.org_id is None:
            return set()
        return await self._loan_repo.borrowed_plate_ids(workspace_id, auth.org_id)

    def can_view(
        self,
        plate: RegisteredPlate,
        auth: AuthContext | None,
        excluded: set[uuid.UUID],
        borrowed: set[uuid.UUID] | frozenset = frozenset(),
    ) -> bool:
        """Visible iff the owner org isn't excluded, or the plate is on
        active loan to the caller's org (``borrowed`` — read surfaces only)."""
        return self.can_view_owner(plate.owner_org_id, excluded) or plate.id in borrowed

    def can_view_owner(
        self, owner_org_id: uuid.UUID | None, excluded: set[uuid.UUID]
    ) -> bool:
        """Visibility by owner org alone — for org-owned things that aren't
        plates (plate groups). Same rule: hidden iff owner org is excluded.
        No loan carve-out — groups stay strict by design (S3/S4 scope)."""
        return owner_org_id not in excluded
```

- [ ] **Step 5: Fix the export unit test's fake and run both files**

In `backend/tests/unit/test_export_plate_layout.py` replace lines 56-64 (`class _FakeOrgPlatePolicyRepo … def _visibility()`) with:

```python
class _FakeOrgDirectory:
    """No orgs — these tests aren't exercising visibility exclusion."""

    async def list_orgs(self):
        return []


def _visibility() -> PlateVisibilityService:
    return PlateVisibilityService(_FakeOrgDirectory())
```

Run: `cd backend && uv run pytest tests/unit/application/test_plate_visibility.py tests/unit/test_export_plate_layout.py -v && uv run ruff check src/cellar/application/shared/org_directory.py src/cellar/application/inventory/plate_visibility.py tests/unit/application/test_plate_visibility.py tests/unit/test_export_plate_layout.py`
Expected: all PASS; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/application/shared/org_directory.py
git commit -m "feat(inventory): strict org visibility — excluded set = every directory org but mine; admins/system see all

PlateVisibilityService now takes an OrgDirectoryPort (application-layer
protocol satisfied by the Duar OrgDirectory) instead of the policy repo.
Fails closed when a non-admin caller has no directory wired.

Spec: docs/superpowers/specs/2026-08-25-plate-tracker-revamp-spec.md §3

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- backend/src/cellar/application/shared/org_directory.py backend/src/cellar/application/inventory/plate_visibility.py backend/tests/unit/application/test_plate_visibility.py backend/tests/unit/test_export_plate_layout.py
```

---

### Task 2: Wire the port through DI (24 construction sites)

**Files:**
- Modify: `backend/src/cellar/infrastructure/di/_core.py` (imports + one guarded `container.define` inside `register_core`, after the `TemporalSettings` define at ~line 98)
- Modify: `backend/src/cellar/infrastructure/di/_inventory.py` (17 single-line `PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow))` sites at lines 523, 549, 558, 567, 576, 584, 594, 604, 625, 634, 643, 659, 670, 681, 692, 703, 714, 734 — `SQLAlchemyOrgPlatePolicyRepository` import stays: lines 533/537 still use it for the policy use cases, and lines 623/657/668/679/690/701/712 pass it as a genuine loan-use-case argument — leave those alone)
- Modify: `backend/src/cellar/infrastructure/di/_screening.py:195` (drop import), `:870-878` (`_plate_visibility` helper), 4 callers inside `register_screening` (`_reg_plate_query_with_visibility`, `_reg_plate_cmd_with_visibility`, `_map_wells`, `_export_plate_layout`)
- Modify: `backend/src/cellar/infrastructure/di/_workspace_config.py:72` (drop import), `:391`
- Modify: `backend/src/cellar/infrastructure/temporal/activities/plate_registration.py:30` (drop import), `:99-102`
- Modify: `backend/src/cellar/interface/dependencies/_inventory.py:92` (drop import), `:254-256`
- Modify: `backend/tests/integration/inventory/test_plate_loan_repository.py:322`

**Interfaces:**
- Consumes: `OrgDirectoryPort` (Task 1), `PlateVisibilityService(org_directory, loan_repo)` (Task 1).
- Produces: the DI container resolves `OrgDirectoryPort` (guarded, so `create_container(overrides={OrgDirectoryPort: stub})` wins — Task 3 relies on this).

- [ ] **Step 1: Register the port in `register_core`**

In `backend/src/cellar/infrastructure/di/_core.py` add imports (keep the existing import ordering — application imports before infrastructure ones):

```python
from cellar.application.shared.org_directory import OrgDirectoryPort
from cellar.infrastructure.duar.org_directory import OrgDirectory
from cellar.infrastructure.duar.settings import DuarSettings
```

and, at the end of `register_core` (after `container.define(TemporalSettings, Singleton(TemporalSettings))`):

```python
    # Org directory port (strict plate visibility, spec 2026-08-25 §3) —
    # guarded so create_container(overrides={OrgDirectoryPort: stub}) can
    # pre-register a stub for API tests. Lazy: DuarSettings is only read on
    # first resolve, so workers/tests that never resolve it need no env.
    # ponytail: routes still use the module singleton in
    # interface/dependencies/_core.py (its own 5-min cache); unify if the
    # double fetch ever matters.
    if OrgDirectoryPort not in container.defined_types:
        container.define(
            OrgDirectoryPort,
            Singleton(
                lambda: OrgDirectory(
                    base_url=DuarSettings().url, service_key=DuarSettings().service_key
                )
            ),
        )
```

- [ ] **Step 2: Sweep the 17 single-line sites in `infrastructure/di/_inventory.py`**

Run from `backend/`:

```bash
sed -i '' 's/PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow))/PlateVisibilityService(c[OrgDirectoryPort])/g' src/cellar/infrastructure/di/_inventory.py
```

Add `from cellar.application.shared.org_directory import OrgDirectoryPort` to that file's imports. Verify every remaining `PlateVisibilityService(` line no longer mentions the policy repo:

Run: `grep -n 'PlateVisibilityService(' src/cellar/infrastructure/di/_inventory.py | grep -c SQLAlchemyOrgPlatePolicyRepository`
Expected: `0`

- [ ] **Step 3: `_screening.py` helper takes the container**

Replace the helper (lines ~870-878) with:

```python
    def _plate_visibility(c: Container, uow: AsyncUnitOfWork) -> PlateVisibilityService:
        # Loan repo wired uniformly across this section (Task 7 / spec §5):
        # only GetPlate/ListPlates/ListChildren actually consume a borrowed
        # set, but the arg is inert for the write paths below (they never
        # call borrowed_plate_ids or pass a non-default `borrowed` to
        # can_view) — one shape for the whole section beats a special case.
        return PlateVisibilityService(c[OrgDirectoryPort], SQLAlchemyPlateLoanRepository(uow))
```

Change its four callers from `visibility = _plate_visibility(uow)` to `visibility = _plate_visibility(c, uow)`. Add the `OrgDirectoryPort` import; delete the now-unused `SQLAlchemyOrgPlatePolicyRepository` import at line 195 (confirm with `grep -n SQLAlchemyOrgPlatePolicyRepository src/cellar/infrastructure/di/_screening.py` → no hits).

- [ ] **Step 4: The remaining four sites**

`infrastructure/di/_workspace_config.py:391`:
```python
        visibility = PlateVisibilityService(c[OrgDirectoryPort])
```
(add the import; delete the `SQLAlchemyOrgPlatePolicyRepository` import at line 72 if nothing else in the file uses it).

`infrastructure/temporal/activities/plate_registration.py:99-102` — worker has no caller identity, so no directory is needed:
```python
        # No caller identity in a worker — auth=None below makes
        # PlateVisibilityService short-circuit to an empty exclusion set
        # without consulting a directory, so this never restricts the
        # pipeline's own writes (and none is wired here on purpose).
        visibility = PlateVisibilityService()
```
(delete the `SQLAlchemyOrgPlatePolicyRepository` import at line 30).

`interface/dependencies/_inventory.py:254-256`:
```python
        PlateVisibilityService(container[OrgDirectoryPort], SQLAlchemyPlateLoanRepository(uow)),
```
(add the import; delete the policy-repo import at line 92 if unused — check with grep).

`tests/integration/inventory/test_plate_loan_repository.py:322` — the test uses `FakeAuth(role="admin")`, which never consults the directory:
```python
        PlateVisibilityService(),
```
(the `SQLAlchemyOrgPlatePolicyRepository` import on line 20 stays — line 321 still passes it to `ApproveLoanItems`).

- [ ] **Step 5: Verify nothing constructs the service the old way, lint, and boot the container**

Run: `grep -rn 'PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository' src tests`
Expected: no output.

Run: `uv run ruff check src/cellar/infrastructure/di src/cellar/infrastructure/temporal/activities/plate_registration.py src/cellar/interface/dependencies/_inventory.py tests/integration/inventory/test_plate_loan_repository.py && uv run python -c "from cellar.infrastructure.di.container import create_container; from cellar.infrastructure.persistence.settings import DatabaseSettings; from cellar.application.shared.org_directory import OrgDirectoryPort; c = create_container(DatabaseSettings(database_url='postgresql+asyncpg://u:p@localhost:5432/x', _env_file=None)); print(OrgDirectoryPort in c.defined_types)"`
Expected: ruff clean; prints `True`.

Run: `uv run pytest tests/unit -q`
Expected: all pass (no unit test constructs the service the old way any more).

- [ ] **Step 6: Commit**

```bash
git commit -m "refactor(di): resolve PlateVisibilityService's org directory from the container

OrgDirectoryPort registered (guarded) in register_core; all 24 construction
sites swapped; the Temporal worker and the admin-only integration test pass
no directory (auth=None/admin never consult it).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- backend/src/cellar/infrastructure/di/_core.py backend/src/cellar/infrastructure/di/_inventory.py backend/src/cellar/infrastructure/di/_screening.py backend/src/cellar/infrastructure/di/_workspace_config.py backend/src/cellar/infrastructure/temporal/activities/plate_registration.py backend/src/cellar/interface/dependencies/_inventory.py backend/tests/integration/inventory/test_plate_loan_repository.py
```

---

### Task 3: API test fixtures + rewrite the hidden-plate tests to strict semantics

**Files:**
- Modify: `backend/tests/api/conftest.py:30-60, 160-175`
- Modify: `backend/tests/api/test_org_directory.py:11`
- Modify: `backend/tests/api/test_registered_plates.py`, `test_plate_groups.py`, `test_plate_loans.py`, `test_plate_insights.py`, `test_plate_import.py`, `test_tag_browse.py`, `test_tags.py`

**Interfaces:**
- Consumes: `OrgDirectoryPort` container override (Task 2).
- Produces: `STUB_ORG_DIRECTORY` (module constant in conftest) listing `ORG_ID`, `AUTH_ORG_ID`, `OTHER_ORG_ID`.

Fixtures you will use (already in conftest): `client` = **admin** in `AUTH_ORG_ID`; `editor_client_own_org` = editor in `AUTH_ORG_ID`; `editor_client_other_org` = editor in `OTHER_ORG_ID`.

- [ ] **Step 1: One stub directory for both the route dep and the container**

In `backend/tests/api/conftest.py`, add top-level imports `from cellar.application.shared.org_directory import OrgDirectoryPort` and `from cellar.infrastructure.duar.org_directory import OrgSummary`, then after the `OTHER_ORG_ID = uuid.uuid4()` line add:

```python
class _StubOrgDirectory:
    """Static Duar org directory — every org id the API tests use, so the
    strict visibility rule ("every other org is excluded") sees all of them.
    Never makes HTTP calls."""

    async def list_orgs(self) -> list[OrgSummary]:
        return [
            OrgSummary(id=ORG_ID, slug="abbvie", name="AbbVie", is_public=False),
            OrgSummary(id=AUTH_ORG_ID, slug="tamu", name="TAMU", is_public=False),
            OrgSummary(id=OTHER_ORG_ID, slug="partner", name="Partner", is_public=False),
        ]


STUB_ORG_DIRECTORY = _StubOrgDirectory()
```

In `_create_test_app` change the container line to:

```python
    container = create_container(
        db_settings, overrides={OrgDirectoryPort: STUB_ORG_DIRECTORY, **(overrides or {})}
    )
```

and replace the inner `_StubOrgDirectory` block (lines ~164-172) with just:

```python
    # Stub the Duar org directory for the /api/v1/orgs route too.
    app.dependency_overrides[get_org_directory] = lambda: STUB_ORG_DIRECTORY
```

(keep the `get_org_directory` import; remove the now-duplicate inner imports).

Update `backend/tests/api/test_org_directory.py:11` to expect the three entries in that order:

```python
    assert resp.json() == [
        {"id": str(ORG_ID), "slug": "abbvie", "name": "AbbVie"},
        {"id": str(AUTH_ORG_ID), "slug": "tamu", "name": "TAMU"},
        {"id": str(OTHER_ORG_ID), "slug": "partner", "name": "Partner"},
    ]
```
(import `AUTH_ORG_ID, OTHER_ORG_ID` from `tests.api.conftest` alongside `ORG_ID`).

Run: `uv run pytest tests/api/test_org_directory.py -q`
Expected: PASS.

- [ ] **Step 2: Add the admin-sees-all test (fails until the rewrite lands — it passes already, actually: confirm)**

Append to `TestVisibility` (the class holding `test_private_org_excluded_from_list_and_get_for_other_org_caller`) in `backend/tests/api/test_registered_plates.py`:

```python
    async def test_strict_by_default_admin_sees_all_editor_sees_own_org_only(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        """No policy row, no toggle: a foreign org's plate is hidden from a
        non-admin caller and visible to a workspace admin."""
        reg = await _register(client, owner_org_id=str(OTHER_ORG_ID))
        assert reg.status_code == 201, reg.text
        plate_id = reg.json()["id"]

        admin_get = await client.get(f"/api/v1/plates/{plate_id}")
        assert admin_get.status_code == 200, admin_get.text
        admin_list = await client.get("/api/v1/plates", params={"owner_org_id": str(OTHER_ORG_ID)})
        assert plate_id in {p["id"] for p in admin_list.json()}

        editor_get = await editor_client_own_org.get(f"/api/v1/plates/{plate_id}")
        assert editor_get.status_code == 404, editor_get.text
        editor_list = await editor_client_own_org.get("/api/v1/plates")
        assert plate_id not in {p["id"] for p in editor_list.json()}
```

Run: `uv run pytest tests/api/test_registered_plates.py -q -k strict_by_default`
Expected: PASS (Tasks 1-2 already made the rule live).

- [ ] **Step 3: Rewrite every test that used `plates_private` — the rule**

Apply this rule, verbatim, to the tests listed in Step 4:

1. Delete the module-level `_set_plates_private` helper (in `test_registered_plates.py`, `test_plate_groups.py`, `test_plate_insights.py`, `test_plate_import.py`, `test_tag_browse.py`, `test_tags.py`). In `test_plate_loans.py` keep `_set_policy` **unchanged** (its `"plates_private": False,` line stays until Task 4 removes the field — the PUT body still requires it).
2. Delete every `await _set_plates_private(...)` / `_set_policy(client, OTHER_ORG_ID, plates_private=True)` call, the `assert policy.status_code == 200` that follows it, and the `try:`/`finally:` that only existed to reset the flag (dedent the body).
3. Every request that asserted **hidden** (404 / 403 / "not in list") through `client` (admin) now goes through `editor_client_own_org` (add the fixture to the test signature). Setup calls that *create* things via `client` are unchanged — admins may register into any org.
4. Every request that asserted **visible for the owner org** through `editor_client_other_org` is unchanged.
5. Where a comment says "admin included — no admin bypass" (`test_plate_groups.py:176`, `test_plate_insights.py`), flip it: assert `client` (admin) gets **200** and `editor_client_own_org` gets **403**.
6. Rename tests whose name says `private` to say `foreign_org` (e.g. `test_private_org_excluded_from_list_and_get_for_other_org_caller` → `test_foreign_org_plate_hidden_from_editor_visible_to_owner_org`). Keep everything else about the assertion strength.

Worked example — `test_registered_plates.py:168-195` becomes:

```python
    async def test_foreign_org_plate_hidden_from_editor_visible_to_owner_org(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
    ) -> None:
        reg = await _register(client, owner_org_id=str(OTHER_ORG_ID))
        assert reg.status_code == 201, reg.text
        plate_id = reg.json()["id"]

        # editor in AUTH_ORG_ID — a different org than the plate's owner —
        # so the plate is excluded from list and 404s on direct GET.
        listed = await editor_client_own_org.get("/api/v1/plates")
        assert listed.status_code == 200, listed.text
        assert plate_id not in {p["id"] for p in listed.json()}

        got = await editor_client_own_org.get(f"/api/v1/plates/{plate_id}")
        assert got.status_code == 404, got.text

        # `editor_client_other_org` is OTHER_ORG_ID — the plate's own org —
        # so it stays visible in both list and direct GET.
        got_own = await editor_client_other_org.get(f"/api/v1/plates/{plate_id}")
        assert got_own.status_code == 200, got_own.text
        assert got_own.json()["id"] == plate_id

        listed_own = await editor_client_other_org.get("/api/v1/plates")
        assert listed_own.status_code == 200, listed_own.text
        assert plate_id in {p["id"] for p in listed_own.json()}
```

Worked example — `test_plate_groups.py:168-186` becomes:

```python
    async def test_foreign_org_tree_forbidden_for_editor_ok_for_admin_and_member(
        self,
        client: AsyncClient,
        editor_client_own_org: AsyncClient,
        editor_client_other_org: AsyncClient,
    ) -> None:
        await _mk_group(client, f"Frn-{uuid.uuid4().hex[:6]}", owner_org_id=str(OTHER_ORG_ID))
        # Editor of another org -> 403 (org existence is public, contents are not)
        resp = await editor_client_own_org.get(f"/api/v1/plate-groups/tree?org_id={OTHER_ORG_ID}")
        assert resp.status_code == 403
        # Workspace admin -> bypass
        resp = await client.get(f"/api/v1/plate-groups/tree?org_id={OTHER_ORG_ID}")
        assert resp.status_code == 200
        # Member still sees it
        resp = await editor_client_other_org.get(f"/api/v1/plate-groups/tree?org_id={OTHER_ORG_ID}")
        assert resp.status_code == 200
```

- [ ] **Step 4: Apply the rule to this exact list**

| File | Tests |
|---|---|
| `test_registered_plates.py` | `test_private_org_excluded_from_list_and_get_for_other_org_caller` (:168), `test_explicit_owner_org_filter_cannot_disclose_private_org` (:197 — the hidden list goes through `editor_client_own_org`), `test_children_exclude_private_org_child` (:216), `test_children_of_invisible_parent_404` (:241), `test_export_private_plate_404_foreign_200_own_org` (:252), `test_update_and_delete_private_plate_404_foreign_200_own_org` (:270), `test_map_wells_change_status_derive_404_for_foreign_org` (:293), `test_derive_from_private_org_plate_inherits_owner_and_stays_private` (:323), `test_molecule_plates_excludes_private_org_plate` (:358) |
| `test_plate_groups.py` | `test_private_org_tree_forbidden_for_non_members` (:168), `test_hidden_group_404s_for_other_org` (:230) |
| `test_plate_loans.py` | `test_private_owner_org_loan_visibility` (:509), `test_borrowed_plate_visible_then_hidden_after_return` (:543), `test_my_org_filter_includes_borrowed_foreign_plate` (:607), `test_explicit_foreign_org_filter_not_widened` (:629) |
| `test_plate_insights.py` | `test_private_org_forbidden_for_non_members_member_ok` (:103) — rule 5 applies |
| `test_plate_import.py` | `test_validate_hidden_plate_reports_same_shape_as_true_miss_for_foreign_org` (:51), `test_validate_matches_for_own_org` (:84) |
| `test_tag_browse.py` | `test_tagged_private_plate_excluded_for_foreign_org_visible_for_own_org` (:136) |
| `test_tags.py` | `test_get_and_assign_404_for_foreign_org` (:159), `test_set_and_unassign_404_for_foreign_org_200_for_own_org` (:180) |

For the loan tests: the `unrelated` client built with `_client_as(database_url, workspace_id, org_id=uuid.uuid4())` is already a non-admin foreign org and stays as is; only drop the policy calls and, where `client` asserted hidden, switch to `editor_client_own_org`.

Run: `uv run pytest tests/api/test_registered_plates.py tests/api/test_plate_groups.py tests/api/test_plate_loans.py tests/api/test_plate_insights.py tests/api/test_plate_import.py tests/api/test_tag_browse.py tests/api/test_tags.py tests/api/test_org_plate_policies.py -q`
Expected: all PASS. (`test_org_plate_policies.py` still passes here — the field is deleted in Task 4.)

Run: `grep -rn 'plates_private' tests/api | grep -v test_org_plate_policies.py`
Expected: exactly one hit — `test_plate_loans.py` line `"plates_private": False,` inside `_set_policy` (Task 4 removes it).

- [ ] **Step 5: Commit**

```bash
git commit -m "test(api): strict visibility — stub directory lists every test org; hidden-plate tests use a non-admin caller

Drops the plates_private toggling helpers; admins now pass the 403 gates
(tree/insights) and see foreign-org plates, editors do not.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- backend/tests/api/conftest.py backend/tests/api/test_org_directory.py backend/tests/api/test_registered_plates.py backend/tests/api/test_plate_groups.py backend/tests/api/test_plate_loans.py backend/tests/api/test_plate_insights.py backend/tests/api/test_plate_import.py backend/tests/api/test_tag_browse.py backend/tests/api/test_tags.py
```

---

### Task 4: Delete `plates_private` end-to-end (migration 066)

**Files:**
- Create: `backend/alembic/versions/066_drop_plates_private.py`
- Modify: `backend/src/cellar/domain/inventory/org_plate_policy.py:1, 22, 33, 44, 54, 63`
- Modify: `backend/src/cellar/domain/inventory/repository.py:280` (drop `list_private_org_ids`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/org_plate_policy_repository.py:37-43, 53, 67, 75`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/models.py:194, 204`
- Modify: `backend/src/cellar/application/inventory/org_plate_policy.py:39, 95`
- Modify: `backend/src/cellar/interface/routes/org_plate_policies.py:1, 27, 37, 46, 75`
- Modify: `backend/tests/unit/test_org_plate_policy.py:23, 28-35, 48`
- Modify: `backend/tests/api/test_org_plate_policies.py:28, 44, 77, 85, 94`
- Modify: `backend/tests/api/test_plate_loans.py:43` (delete `"plates_private": False,` from `_set_policy`)

**Interfaces:**
- Produces: `OrgPlatePolicy(require_approval, confirmation, default_due_days)` only; `SetOrgPlatePolicyBody` has three fields and still `extra: "forbid"` (so a client still sending `plates_private` gets 422).

- [ ] **Step 1: Update the unit + API tests first**

`backend/tests/unit/test_org_plate_policy.py`: delete line 23 (`assert policy.plates_private is False`) and line 48 (`assert policy.plates_private is False  # unchanged`); replace `test_update_flips_plates_private_and_emits_event` (lines 28-35) with:

```python
    def test_update_emits_event(self) -> None:
        policy = OrgPlatePolicy.create_default(workspace_id=uuid.uuid4(), org_id=uuid.uuid4())
        policy.update(require_approval=False)
        assert policy.require_approval is False

        events = policy.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], OrgPlatePolicySet)
        assert events[0].org_id == policy.org_id
```

`backend/tests/api/test_plate_loans.py`: delete the `"plates_private": False,` line from `_set_policy` (line 43).

`backend/tests/api/test_org_plate_policies.py`: delete `"plates_private": False,` from `_body` (line 28), `plates_private=True,` (line 77), and the three `assert data["plates_private"] …` / `assert fetched["plates_private"] …` lines (44, 85, 94). Add to `TestSetOrgPlatePolicy`:

```python
    async def test_put_rejects_removed_plates_private_field(self, client: AsyncClient) -> None:
        """The toggle is gone (spec 2026-08-25 §3); extra=forbid keeps stale clients honest."""
        resp = await client.put(
            f"/api/v1/org-plate-policies/{uuid.uuid4()}", json=_body(plates_private=True)
        )
        assert resp.status_code == 422, resp.text
```

Run: `uv run pytest tests/unit/test_org_plate_policy.py tests/api/test_org_plate_policies.py -q`
Expected: the new 422 test FAILS (200 today); the others pass.

- [ ] **Step 2: Domain, protocol, repository, model, use case, route**

`domain/inventory/org_plate_policy.py`: docstrings drop "/visibility"; remove the `plates_private: bool = False` parameter (line 33), `self.plates_private = plates_private` (44), the word from the `update` docstring (54), and `"plates_private"` from the tuple on line 63.

`domain/inventory/repository.py`: delete line 280 (`async def list_private_org_ids…`).

`org_plate_policy_repository.py`: delete `list_private_org_ids` (lines 37-43) and the three `plates_private=…`/`model.plates_private = …` lines (53, 67, 75).

`models.py`: delete line 204 (`plates_private` column); docstring on 194 → `"""Per-org plate loan policy within a workspace."""`.

`application/inventory/org_plate_policy.py`: delete `plates_private: bool` (39) and `plates_private=input.plates_private,` (95).

`interface/routes/org_plate_policies.py`: delete `plates_private: bool` from both models (27, 46), `plates_private=p.plates_private,` (37), `plates_private=body.plates_private,` (75); module docstring → `"""Org plate policy endpoints — per-org plate loan config."""`.

Run: `grep -rn 'plates_private\|list_private_org_ids' src`
Expected: no output.

- [ ] **Step 3: Migration 066**

Create `backend/alembic/versions/066_drop_plates_private.py`:

```python
"""066 — drop org_plate_policies.plates_private (spec 2026-08-25 §3)

Plate visibility is strict for every org (own plates + plates on loan to
me; workspace admins see all), so the per-org opt-in privacy flag is gone.

Revision ID: 066_drop_plates_private
Revises: 065_target_mirror_columns
"""

import sqlalchemy as sa
from alembic import op

revision = "066_drop_plates_private"
down_revision = "065_target_mirror_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("org_plate_policies", "plates_private")


def downgrade() -> None:
    op.add_column(
        "org_plate_policies",
        sa.Column("plates_private", sa.Boolean(), nullable=False, server_default="false"),
    )
```

- [ ] **Step 4: Run the affected suites**

Run: `uv run ruff check <the files you changed> && uv run pytest tests/unit/test_org_plate_policy.py tests/api/test_org_plate_policies.py tests/api/test_plate_loans.py tests/api/test_kiosk.py -q`
Expected: ruff clean; all PASS (the API suite runs migrations up to head 066 against the testcontainer).

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/066_drop_plates_private.py
git commit -m "feat(inventory)!: drop OrgPlatePolicy.plates_private — visibility is strict for every org (migration 066)

PUT /org-plate-policies/{org_id} no longer accepts plates_private (422).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- backend/alembic/versions/066_drop_plates_private.py backend/src/cellar/domain/inventory/org_plate_policy.py backend/src/cellar/domain/inventory/repository.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/org_plate_policy_repository.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/models.py backend/src/cellar/application/inventory/org_plate_policy.py backend/src/cellar/interface/routes/org_plate_policies.py backend/tests/unit/test_org_plate_policy.py backend/tests/api/test_org_plate_policies.py backend/tests/api/test_plate_loans.py
```

---

### Task 5: Actor `ContextVar` → audit catch-all attributes the user

**Files:**
- Create: `backend/src/cellar/application/shared/actor_context.py`
- Modify: `backend/src/cellar/interface/dependencies/_core.py:174-190` (`get_auth`)
- Modify: `backend/src/cellar/application/audit/audit_recording_service.py:107-118` (`handle_event`)
- Modify: `backend/tests/unit/application/audit/test_audit_recording_service.py:56-60, 138-161`

**Interfaces:**
- Produces: `set_current_actor(user_id: UUID | None) -> None`, `current_actor() -> UUID | None` in `cellar.application.shared.actor_context`.
- `handle_event` actor rule: `event.user_id` if present and not the nil UUID → else `current_actor()` → else nil UUID; `actor_type = USER` iff an actor was resolved, else `SYSTEM`.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/unit/application/audit/test_audit_recording_service.py` add next to `FakeRegisteredEvent`:

```python
@dataclass(frozen=True, kw_only=True)
class FakeBareEvent(DomainEvent):
    """An event that carries no actor at all (the inventory shape)."""

    workspace_id: uuid.UUID = uuid.UUID(int=0)
```

and add the import `from cellar.application.shared.actor_context import set_current_actor`. Change the existing `test_handle_event_creates_audit_operation` assertion `assert op.actor_type == ActorType.SYSTEM` to:

```python
        assert op.user_id == user_id
        assert op.actor_type == ActorType.USER
```

Append to the same class:

```python
    async def test_handle_event_without_user_id_uses_request_actor(
        self, service: AuditRecordingService, repo: FakeAuditRepository
    ) -> None:
        actor = uuid.uuid4()
        set_current_actor(actor)
        try:
            await service.handle_event(
                FakeBareEvent(aggregate_id=uuid.uuid4(), aggregate_type="PlateLoan")
            )
        finally:
            set_current_actor(None)

        op = repo.saved[0]
        assert op.user_id == actor
        assert op.actor_type == ActorType.USER

    async def test_handle_event_without_any_actor_is_system_nil(
        self, service: AuditRecordingService, repo: FakeAuditRepository
    ) -> None:
        await service.handle_event(
            FakeBareEvent(aggregate_id=uuid.uuid4(), aggregate_type="PlateLoan")
        )

        op = repo.saved[0]
        assert op.user_id == uuid.UUID(int=0)
        assert op.actor_type == ActorType.SYSTEM

    async def test_handle_event_nil_user_id_falls_through_to_request_actor(
        self, service: AuditRecordingService, repo: FakeAuditRepository
    ) -> None:
        """A nil user_id on the event means 'unknown', not 'the nil user'."""
        actor = uuid.uuid4()
        set_current_actor(actor)
        try:
            await service.handle_event(
                FakeRegisteredEvent(aggregate_id=uuid.uuid4(), aggregate_type="molecule")
            )
        finally:
            set_current_actor(None)

        assert repo.saved[0].user_id == actor
```

Run: `uv run pytest tests/unit/application/audit/test_audit_recording_service.py -q`
Expected: FAIL — `ImportError` on `actor_context`.

- [ ] **Step 2: Create the context module**

Create `backend/src/cellar/application/shared/actor_context.py`:

```python
"""Current-actor context — the authenticated user id for the running request.

Set once per request by the interface layer (next to the logging-context
binding in ``get_auth``); read by side-effect handlers that run after commit
without an ``auth`` in hand (the audit catch-all). A ``ContextVar`` is
task-local, so concurrent requests never see each other's actor, and a
worker/kiosk path that never calls ``get_auth`` reads ``None``.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_current_actor_id: ContextVar[uuid.UUID | None] = ContextVar("current_actor_id", default=None)


def set_current_actor(user_id: uuid.UUID | None) -> None:
    _current_actor_id.set(user_id)


def current_actor() -> uuid.UUID | None:
    return _current_actor_id.get()
```

- [ ] **Step 3: Set it in `get_auth`, read it in `handle_event`**

`interface/dependencies/_core.py` — add `from cellar.application.shared.actor_context import set_current_actor` and change the body of `get_auth` to:

```python
    raw_user_id = getattr(auth, "user_id", None)
    workspace_id = getattr(auth, "workspace_id", None)
    user_id = str(raw_user_id) if raw_user_id is not None else None
    workspace_id = str(workspace_id) if workspace_id is not None else None
    bind_user_context(user_id=user_id, workspace_id=workspace_id)
    set_current_actor(raw_user_id if isinstance(raw_user_id, uuid.UUID) else None)
    request.state.user_id = user_id
    request.state.workspace_id = workspace_id
    return auth
```
(add `import uuid` to the module if absent).

`application/audit/audit_recording_service.py` — add `from cellar.application.shared.actor_context import current_actor`, a module constant `_NIL_USER = uuid.UUID(int=0)`, and change the start of `handle_event` to:

```python
        event_user = getattr(event, "user_id", None)
        actor_id = event_user if event_user not in (None, _NIL_USER) else current_actor()
        operation = AuditOperation(
            id=uuid.uuid4(),
            workspace_id=getattr(event, "workspace_id", uuid.UUID(int=0)),
            operation_type=_infer_operation_type(event),
            user_id=actor_id if actor_id is not None else _NIL_USER,
            actor_type=ActorType.USER if actor_id is not None else ActorType.SYSTEM,
```
(the rest of the `AuditOperation(...)` call and the entry are unchanged). Update the method docstring's last sentence to: `Actor = the event's own user_id when set, else the request's current actor (set by get_auth), else the nil SYSTEM user.`

- [ ] **Step 4: Run the tests + an API-level proof**

Run: `uv run pytest tests/unit/application/audit -q && uv run ruff check src/cellar/application/shared/actor_context.py src/cellar/interface/dependencies/_core.py src/cellar/application/audit/audit_recording_service.py tests/unit/application/audit/test_audit_recording_service.py`
Expected: PASS, ruff clean.

Append to `backend/tests/api/test_registered_plates.py` (class `TestVisibility` or a new `TestAudit` class at the end of the file):

```python
class TestAuditActor:
    async def test_plate_registration_audit_row_names_the_caller(
        self, client: AsyncClient, api_app: FastAPI, user_id: uuid.UUID
    ) -> None:
        reg = await _register(client)
        assert reg.status_code == 201, reg.text
        plate_id = reg.json()["id"]

        audit = await client.get(
            "/api/v1/audit", params={"entity_type": "RegisteredPlate", "entity_id": plate_id}
        )
        assert audit.status_code == 200, audit.text
        rows = audit.json()["items"]
        assert rows, "expected at least one audit row for the registered plate"
        assert {r["performed_by"] for r in rows} == {str(user_id)}
```
(`user_id` is the existing conftest fixture feeding `fake_auth`; add `from fastapi import FastAPI` if the file doesn't import it yet. `items` is the page key of `PaginatedResponse` — `backend/src/cellar/interface/pagination.py:42`.)

Run: `uv run pytest tests/api/test_registered_plates.py -q -k audit_row_names`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/shared/actor_context.py
git commit -m "fix(audit): attribute catch-all audit rows to the request's user instead of a nil SYSTEM actor

get_auth sets a task-local current actor next to the logging context;
handle_event uses event.user_id, else the current actor, else nil/SYSTEM.
Fixes nil-actor rows for every inventory event (plates, groups, loans).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- backend/src/cellar/application/shared/actor_context.py backend/src/cellar/interface/dependencies/_core.py backend/src/cellar/application/audit/audit_recording_service.py backend/tests/unit/application/audit/test_audit_recording_service.py backend/tests/api/test_registered_plates.py
```

---

### Task 6: Frontend — admin-only org selectors, policy dialog without the switch, audit entity filter, regenerated types

**Files:**
- Modify: `frontend/src/shared/lib/api/model/orgPlatePolicyResponse.ts`, `frontend/src/shared/lib/api/model/setOrgPlatePolicyBody.ts` (via orval regen, or by hand if the backend can't be started)
- Modify: `frontend/src/features/inventory/components/org-plate-policy-dialog.tsx` (remove Switch + state + field)
- Modify: `frontend/src/features/inventory/components/org-plate-policy-dialog.test.tsx:11`
- Modify: `frontend/src/features/inventory/hooks/use-org-plate-policy.test.tsx:11, 60, 75`
- Modify: `frontend/src/features/inventory/components/plate-list.tsx:236-240, 294-310`
- Modify: `frontend/src/features/inventory/components/plate-group-dashboard.tsx:89-107`
- Modify: `frontend/src/features/audit/components/audit-list.tsx:17-27`
- Modify: `frontend/src/features/inventory/components/request-loan-dialog.tsx` (Lend-to select, Task 8 backend)

**Interfaces:**
- Consumes: `useCurrentUser()` → `me.is_admin: boolean` (already served by `/api/v1/user/me`).

- [ ] **Step 1: Regenerate the orval types**

With the backend running on `:8000` (`make dev-be` from the repo root — it runs `uv run uvicorn cellar.interface.app:app --reload --port 8000` and logs to the Makefile's `LOGDIR`), run from `frontend/`:

`/Users/sidx/Library/pnpm/pnpm generate:api`

Review `git diff src/shared/lib/api/model/` — the only intended change is the removal of `plates_private: boolean;` from `orgPlatePolicyResponse.ts` and `setOrgPlatePolicyBody.ts`. If the regen is impossible in this environment, delete those two lines by hand and say so in the commit body.

- [ ] **Step 2: Update the two FE tests, then the dialog**

`org-plate-policy-dialog.test.tsx:11` — delete `plates_private: true,`.
`use-org-plate-policy.test.tsx` — delete `plates_private: false,` (11) and both `plates_private: true,` lines (60, 75).

Run: `/Users/sidx/Library/pnpm/pnpm vitest run src/features/inventory/components/org-plate-policy-dialog.test.tsx src/features/inventory/hooks/use-org-plate-policy.test.tsx`
Expected: the dialog test may still pass (it doesn't assert on the switch); the hook test FAILS on `toEqual` until the dialog/hook stop sending the field — proceed.

`org-plate-policy-dialog.tsx`: remove the `Switch` import (line 20), `const [platesPrivate, setPlatesPrivate] = useState(false);` (49), `setPlatesPrivate(false);` (63), `setPlatesPrivate(policy.plates_private);` (72), `plates_private: platesPrivate,` (83), and the whole `<div className="flex items-center gap-2"> … Plates private to org … </div>` block (155-162). Docstring on line 37 → `/** Admin dialog to view/edit a single org's plate loan policy. */`.

Run the same vitest command.
Expected: PASS.

- [ ] **Step 3: Admin-only org controls on the Plates list**

In `plate-list.tsx`, after `const { data: me, isError: meFailed } = useCurrentUser();` add:

```tsx
  const isAdmin = me?.is_admin === true;
```

Wrap the "Org Policies" button (lines 236-239) in `{isAdmin ? ( … ) : null}` and wrap the org `<Select value={filterOrg} …>` block (lines 294-310) in `{isAdmin ? ( … ) : null}`. Non-admins keep `filterOrg === MY_ORG`, so `ownerOrgId` resolves to their own org exactly as before. Update the `MY_ORG`/`ALL_ORGS` comment lines to say the selector is admin-only.

- [ ] **Step 4: Admin-only org selector on Plate Groups (Insights shares it)**

In `plate-group-dashboard.tsx`, add `const isAdmin = me?.is_admin === true;` after the `useCurrentUser()` line and wrap the org `<Select …>` inside `<PageHeader>` (lines 90-107) in `{isAdmin ? ( … ) : null}`. The default-to-my-org effect is unchanged; the Insights tab already receives `orgId` from this state.

- [ ] **Step 5: Audit entity filter entries**

In `audit-list.tsx` extend `ENTITY_TYPE_OPTIONS` (values are the backend `aggregate_type` strings):

```ts
  { value: "RegisteredPlate", label: "Plate" },
  { value: "PlateGroup", label: "Plate Group" },
  { value: "PlateLoan", label: "Plate Loan" },
```
(insert after the `run` entry).

- [ ] **Step 5b: "Lend to" select on the loan request dialog (Task 8 backend)**

In `request-loan-dialog.tsx` add state `const [borrowerOrgId, setBorrowerOrgId] = useState<string>("");` and read `const { data: orgs } = useOrgs();` (`@/shared/hooks/use-orgs`). Render, above the due-date field, a labeled `<Select>` "Borrower organization" whose first item is `<SelectItem value="">My organization (self-checkout)</SelectItem>` — if the shadcn Select rejects an empty value in this repo, use the sentinel `"__mine__"` — followed by one item per org from `orgs` **except** the caller's own (`orgId` prop). In `handleSubmit`, when a foreign org is selected add `body.borrower_org_id = borrowerOrgId`. Change the primary button label to `Lend` when a foreign org is selected, else keep `Request`. Reset `borrowerOrgId` when the dialog closes (the existing reset effect). `RequestLoanBody.borrower_org_id` exists after Step 1's regen (or add the optional field to the generated `requestLoanBody.ts` by hand if regen was impossible, and say so).

Add one test to `request-loan-dialog.test.tsx` following its existing mocking style: selecting a foreign org and submitting sends `borrower_org_id` in the POST body; the default submission sends none.

- [ ] **Step 6: Type-check, lint, test**

Run from `frontend/`:
`/Users/sidx/Library/pnpm/pnpm tsc --noEmit && /Users/sidx/Library/pnpm/pnpm biome check src/features/inventory/components/org-plate-policy-dialog.tsx src/features/inventory/components/org-plate-policy-dialog.test.tsx src/features/inventory/hooks/use-org-plate-policy.test.tsx src/features/inventory/components/plate-list.tsx src/features/inventory/components/plate-group-dashboard.tsx src/features/audit/components/audit-list.tsx src/features/inventory/components/request-loan-dialog.tsx src/features/inventory/components/request-loan-dialog.test.tsx; echo "biome exit=$?" && /Users/sidx/Library/pnpm/pnpm vitest run src/features/inventory src/features/audit`
Expected: tsc clean, `biome exit=0` (repo-wide `pnpm lint` is red on main for pre-existing reasons — judge only the touched files, by exit code), tests PASS.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(frontend): org selectors and Org Policies are admin-only; drop the plates-private switch; audit filter knows plates/groups/loans

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- frontend/src/shared/lib/api/model/orgPlatePolicyResponse.ts frontend/src/shared/lib/api/model/setOrgPlatePolicyBody.ts frontend/src/features/inventory/components/org-plate-policy-dialog.tsx frontend/src/features/inventory/components/org-plate-policy-dialog.test.tsx frontend/src/features/inventory/hooks/use-org-plate-policy.test.tsx frontend/src/features/inventory/components/plate-list.tsx frontend/src/features/inventory/components/plate-group-dashboard.tsx frontend/src/features/audit/components/audit-list.tsx frontend/src/features/inventory/components/request-loan-dialog.tsx frontend/src/features/inventory/components/request-loan-dialog.test.tsx frontend/src/shared/lib/api/model/requestLoanBody.ts
```
(If the orval regen touched other generated files, include them in the pathspec only when the diff is the additive/no-op kind CLAUDE.md describes; otherwise revert them.)

---

### Task 7: Full backend suite, spec sync note, tracking

**Files:**
- Modify: `docs/superpowers/specs/2026-08-25-plate-tracker-revamp-spec.md` (status line + appended sync note)

- [ ] **Step 1: Run the whole backend suite once**

Run: `cd backend && uv run pytest -q`
Expected: green except the pre-existing failures recorded in `docs/backlog/preexisting-test-lint-failures-main.md` — compare against that file; anything not listed there is yours to fix before continuing.

- [ ] **Step 2: Sync note**

Change the spec's status line to `**Status:** APPROVED 2026-08-25 · S7 shipped` and append at the end of the file:

```markdown
## S7 sync note (YYYY-MM-DD) — shipped reality vs. §3/§4

- Excluded set is computed from `OrgDirectoryPort` (application protocol) resolved via the Lagom container (`register_core`, guarded for test overrides); the `/api/v1/orgs` route still uses the interface-layer `OrgDirectory` singleton — two instances, two 5-min caches (ponytail-marked).
- `PlateVisibilityService()` with no directory is legal for auth=None/admin callers (Temporal worker, admin-only integration test) and raises `RuntimeError` otherwise.
- Migration 066 drops `plates_private`; `PUT /org-plate-policies/{org}` returns 422 if a client still sends it.
- Audit actor precedence: `event.user_id` (non-nil) → request `current_actor()` → nil/SYSTEM. Kiosk and worker paths stay SYSTEM by design.
- FE: org selectors on Plates / Plate Groups (+Insights) and the Org Policies button render only for `me.is_admin`.
- Deviations: <list any, or "none">
```
(fill in the date and the deviations line from what actually happened).

- [ ] **Step 3: Commit + tracking**

```bash
git add -f docs/superpowers/specs/2026-08-25-plate-tracker-revamp-spec.md docs/superpowers/plans/2026-08-25-s7-strict-visibility-audit-actor.md
git commit -m "docs(spec): S7 sync note — strict visibility, admin bypass, audit actor shipped

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- docs/superpowers/specs/2026-08-25-plate-tracker-revamp-spec.md docs/superpowers/plans/2026-08-25-s7-strict-visibility-audit-actor.md
```

Then post a progress comment on the tracking issue (from the repo root):

```bash
gh issue comment 71 --body "S7 (plate tracker revamp, spec 2026-08-25) shipped: strict org visibility with admin bypass, plates_private removed (migration 066), audit catch-all now attributes the calling user. Commits: $(git log --oneline -6 --format='%h %s' | sed 's/^/- /' | tr '\n' ' ')"
```

---

### Task 8: Owner-initiated lending (`borrower_org_id` on the loan request) — **execute right after Task 3, before Task 4**

Added 2026-08-25 (ledger Ruling R6, confirmed by the user): under strict visibility a non-admin cannot request a loan on a plate it cannot see, so cross-org loans are created by the **owner** org ("lend to X"). Same-org self-checkout is unchanged.

**Files:**
- Modify: `backend/src/cellar/application/inventory/plate_loans.py:53-61` (command), `:108-127` (constructor), `:129-141` (borrower derivation), `:229-250` (post-resolution guard + approval)
- Modify: `backend/src/cellar/interface/routes/plate_loans.py:108-115` (`RequestLoanBody`), `:137-145` (command construction)
- Modify: `backend/src/cellar/infrastructure/di/_inventory.py` (the `RequestPlateLoan(...)` factory — pass `c[OrgDirectoryPort]`)
- Modify: `backend/tests/api/test_plate_loans.py` (new class `TestOwnerLends`)

**Interfaces:**
- Consumes: `OrgDirectoryPort` (`cellar.application.shared.org_directory`), `PlateLoan.request(auto_approved=...)`, `PlateLoan.approve_items(item_ids, *, approved_by)`, `PlateLoan.eligible_item_ids(target)`, `PlateLoan.confirm_checkout(item_ids)`.
- Produces: `POST /api/v1/plate-loans` accepts optional `borrower_org_id`; semantics below. Task 6 adds the FE select that sends it.

Semantics (spec §3 addendum):
1. `borrower_org_id` omitted or equal to the caller's org → today's behaviour (borrower-initiated request; items `requested`, or `approved`/`checked_out` per the owner policy collapse).
2. `borrower_org_id` ≠ caller's org → **owner-initiated lend**: allowed only if the caller is a workspace admin or every requested plate is owned by the caller's org (non-admin foreign plates are already hidden → 404 by the existing resolution); the borrower org must exist in the org directory (else 422 `Unknown borrower organization`); the loan starts `requested` and is immediately approved by the caller (`approve_items(..., approved_by=requested_by)` → `approved_by` set, `PlateLoanItemsApproved` emitted); if the owner policy's `confirmation` is `none`, items go straight to `checked_out` (same collapse as self-serve).

- [ ] **Step 1: Write the failing API tests**

Append to `backend/tests/api/test_plate_loans.py` (after `TestOwnershipOrg`; `_mk_plate`, `_mk_loan`, `_set_policy`, `_client_as`, `AUTH_ORG_ID`, `OTHER_ORG_ID`, `ORG_ID` already exist in the module — import `ORG_ID` from `tests.api.conftest` if it isn't imported yet):

```python
class TestOwnerLends:
    """Ruling R6: cross-org loans are created by the owner org."""

    async def test_owner_editor_lends_to_other_org_items_approved(
        self, client: AsyncClient, editor_client_own_org: AsyncClient, user_id: uuid.UUID
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")  # owner = AUTH_ORG
        loan = await _mk_loan(
            editor_client_own_org, plate_ids=[plate["id"]], borrower_org_id=str(OTHER_ORG_ID)
        )
        assert loan["owner_org_id"] == str(AUTH_ORG_ID)
        assert loan["borrower_org_id"] == str(OTHER_ORG_ID)
        assert [i["status"] for i in loan["items"]] == ["approved"]
        assert loan["approved_by"] == str(user_id)

    async def test_lend_with_confirmation_none_checks_out(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        await _set_policy(client, AUTH_ORG_ID, require_approval=True, confirmation="none")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(
            editor_client_own_org, plate_ids=[plate["id"]], borrower_org_id=str(OTHER_ORG_ID)
        )
        assert [i["status"] for i in loan["items"]] == ["checked_out"]

    async def test_lend_to_unknown_org_rejected(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        resp = await editor_client_own_org.post(
            "/api/v1/plate-loans",
            json={"plate_ids": [plate["id"]], "borrower_org_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 422, resp.text
        assert "Unknown borrower organization" in resp.text

    async def test_non_owner_editor_cannot_lend_foreign_plate(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        plate = await _mk_plate(
            client, f"PL-{uuid.uuid4().hex[:8]}", owner_org_id=str(OTHER_ORG_ID)
        )
        resp = await editor_client_own_org.post(
            "/api/v1/plate-loans",
            json={"plate_ids": [plate["id"]], "borrower_org_id": str(ORG_ID)},
        )
        assert resp.status_code == 404, resp.text  # hidden == missing

    async def test_admin_can_lend_any_orgs_plate(self, client: AsyncClient) -> None:
        plate = await _mk_plate(
            client, f"PL-{uuid.uuid4().hex[:8]}", owner_org_id=str(OTHER_ORG_ID)
        )
        loan = await _mk_loan(client, plate_ids=[plate["id"]], borrower_org_id=str(ORG_ID))
        assert loan["owner_org_id"] == str(OTHER_ORG_ID)
        assert loan["borrower_org_id"] == str(ORG_ID)
        assert [i["status"] for i in loan["items"]] == ["approved"]

    async def test_borrower_org_id_equal_to_own_org_is_a_plain_request(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        loan = await _mk_loan(
            editor_client_own_org, plate_ids=[plate["id"]], borrower_org_id=str(AUTH_ORG_ID)
        )
        assert loan["borrower_org_id"] == str(AUTH_ORG_ID)
        assert [i["status"] for i in loan["items"]] == ["requested"]  # default policy: approval required
```

Run: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_plate_loans.py -q -k TestOwnerLends`
Expected: FAIL — `422` from `extra: "forbid"` on `borrower_org_id` for every test.

- [ ] **Step 2: Command + constructor**

In `backend/src/cellar/application/inventory/plate_loans.py` add `borrower_org_id: uuid.UUID | None = None` to `RequestPlateLoanCommand` (after `group_id`), add `from cellar.application.shared.org_directory import OrgDirectoryPort` to the imports, and give `RequestPlateLoan.__init__` a new **last** parameter `org_directory: OrgDirectoryPort` stored as `self._org_directory`.

- [ ] **Step 3: Borrower derivation + owner-lend guard + approval**

Replace lines 133-135 (the `borrower_org_id = auth.org_id …` block) with:

```python
        caller_org_id = auth.org_id if auth is not None else None
        if caller_org_id is None:
            return Failure(ValidationError("Caller has no organization — loans require an org"))
        borrower_org_id = input.borrower_org_id or caller_org_id
        owner_initiated = borrower_org_id != caller_org_id
```

After `owner_org_id = owner_org_ids.pop()` (inside the `async with self._uow:` block) insert:

```python
            if owner_initiated:
                # Ruling R6: lending is an owner-org (or admin) act. Non-admin
                # callers only ever reach here with their own org's plates
                # (foreign plates are hidden → 404 above), so this guard is
                # the admin-vs-owner line, not a visibility check.
                if not (auth is not None and (auth.is_admin or owner_org_id == caller_org_id)):
                    raise AuthorizationError("Only the owner organization can lend its plates")
                known = {o.id for o in await self._org_directory.list_orgs()}
                if borrower_org_id not in known:
                    return Failure(ValidationError("Unknown borrower organization"))
```

Replace the block from `loan = PlateLoan.request(` through the self-serve `loan.confirm_checkout(...)` with:

```python
            loan = PlateLoan.request(
                workspace_id=input.workspace_id,
                owner_org_id=owner_org_id,
                borrower_org_id=borrower_org_id,
                requested_by=input.requested_by,
                plate_ids=[p.id for p in plates],
                auto_approved=not policy.require_approval and not owner_initiated,
                due_date=due,
                notes=input.notes,
            )
            if owner_initiated:
                # The owner is lending: it approves its own loan on creation.
                loan.approve_items(
                    loan.eligible_item_ids(LoanItemStatus.APPROVED), approved_by=input.requested_by
                )
            if policy.confirmation == LoanConfirmationMode.NONE and (
                owner_initiated or not policy.require_approval
            ):
                # No separate checkout confirmation step, so approved items
                # go straight to checked-out (self-serve and owner-lend alike).
                loan.confirm_checkout(loan.eligible_item_ids(LoanItemStatus.CHECKED_OUT))
```

(`AuthorizationError` is in `cellar.domain.shared.errors`; import it if the module doesn't already.)

- [ ] **Step 4: Route + DI**

`interface/routes/plate_loans.py`: add `borrower_org_id: uuid.UUID | None = None` to `RequestLoanBody` (after `group_id`) and `borrower_org_id=body.borrower_org_id,` to the `RequestPlateLoanCommand(...)` construction.

`infrastructure/di/_inventory.py`: in the factory that builds `RequestPlateLoan(...)`, pass `c[OrgDirectoryPort]` as the new last argument (`OrgDirectoryPort` is already imported there since Task 2).

- [ ] **Step 5: Run + lint**

Run: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_plate_loans.py tests/api/test_kiosk.py -q && uv run ruff check src/cellar/application/inventory/plate_loans.py src/cellar/interface/routes/plate_loans.py src/cellar/infrastructure/di/_inventory.py tests/api/test_plate_loans.py`
Expected: all PASS (the six new tests + every existing loan/kiosk test), ruff clean.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(inventory): owner-initiated lending — borrower_org_id on loan requests (auto-approved by the lender)

Under strict visibility a borrower can't see foreign plates, so cross-org
loans are created by the owner org (or an admin) naming the borrower.
Borrower must exist in the org directory; same-org requests unchanged.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HeExFT5oQrec5VbwQafNfu" -- backend/src/cellar/application/inventory/plate_loans.py backend/src/cellar/interface/routes/plate_loans.py backend/src/cellar/infrastructure/di/_inventory.py backend/tests/api/test_plate_loans.py
```

