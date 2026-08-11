# S3 — PlateGroup Hierarchy + Tree Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PlateGroup open hierarchy (domain → API) with visibility enforced from day one, plus a react-d3-tree dashboard page with full group management — preceded by the six-item S2 cleanup batch.

**Architecture:** New `PlateGroup` aggregate (inventory context, adjacency-list tree), `group_id` on `RegisteredPlate`, seven use cases wired through the existing `PlateVisibilityService`, `/api/v1/plate-groups` routes, orval regen, hand-written TanStack hooks, and a new `/inventory/plate-groups` page (org selector → react-d3-tree → details panel + management dialogs).

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2 async / Alembic (next migration: **062**) / dry-python returns; Next.js 16 / React 19 / TanStack Query v5 / shadcn/ui / react-d3-tree (new dep).

**Spec:** `docs/superpowers/specs/2026-08-10-inventory-plate-org-loans-spec.md` §4.1–4.2, §5, §8–§11, §14-S3.

## Global Constraints

- **Visibility from the start (spec §5):** the groups tree and every group/plate operation must consume `PlateVisibilityService.excluded_org_ids`. Hidden == missing: a group/plate hidden by org privacy returns 404 exactly like a nonexistent one. Org-scoped tree read for a private org by a non-member returns **403** (spec §5 wording: "member-only → 403 otherwise"). No admin bypass (matches S2 semantics).
- **Group invariants (spec §4.2):** parent in same workspace + same owner org; no cycles (validated on reparent); name unique per `(workspace_id, owner_org_id, parent_group_id)` with `NULLS NOT DISTINCT` (raw-SQL index, migration-049 style). A plate belongs to ≤1 group; **plate.owner_org_id must equal group.owner_org_id**.
- **Owner org:** `plate_groups.owner_org_id` is **NOT NULL** (groups are net-new, always owned; decision recorded in Task 3). Creation defaults to `auth.org_id`; non-admins cannot create for another org (same guard as `RegisterPlate`).
- **Layer rules:** Domain imports nothing app/infra; use cases start with `require_*` guards; routes never contain guards; response DTOs colocated in route files with `from_domain`. Railway: use cases return `Result[..., DomainError]`.
- **Orval:** regenerate in the same change as any route/DTO change; never hand-roll a mirror type; alias generated types for domain names.
- **UI rules:** names never UUIDs (org picker by name, plates by barcode/label); explicit confirm gestures, no autosave; count badges next to (not inside) action buttons.
- **Test commands:** backend `uv run pytest tests/unit -x -q` (fast) / `uv run pytest tests/api/test_plate_groups.py -x -q` (needs `make up`); frontend `pnpm exec vitest run <file>` and `pnpm exec biome check <files>` — judge by exit code, never piped output (`pnpm test`/`pnpm lint` crash under Node 25).
- **Commits:** always `git commit -m "..." -- <explicit paths>` (the working tree carries the user's unrelated Sentinel-SDK bump in `frontend/package.json`/`pnpm-lock.yaml`/`next-env.d.ts` — NEVER sweep those in, except Task 8 which deliberately adds react-d3-tree to package.json/lockfile and must commit those two files' react-d3-tree hunks via the same files but only after the dep add; see Task 8 Step 1 note).
- **Baseline failures:** backend full suite has 10 documented pre-existing failures (`docs/backlog/pre-existing-test-failures.md`); FE suite is green. Never "fix" a baseline failure inside S3 tasks.

---

### Task 1: Backend cleanup batch (S2 triage items a, c, f + enum-typed PlateResponse)

**Files:**
- Modify: `backend/src/cellar/application/inventory/registered_plates.py` (DeletePlate conflict message, ~line 514)
- Modify: `backend/src/cellar/interface/routes/org_plate_policies.py` (`confirmation` typed as enum)
- Modify: `backend/src/cellar/interface/routes/registered_plates.py` (`PlateResponse.format/plate_type/status` typed as enums)
- Modify: `backend/tests/api/test_org_plate_policies.py` (PUT test varies all four fields)
- Modify (only if they assert the old strings): `backend/tests/api/test_registered_plates.py`

**Interfaces:**
- Consumes: existing `LoanConfirmationMode`, `PlateFormat`, `PlateType`, `PlateStatus` StrEnums.
- Produces: OpenAPI now emits enum schemas for `OrgPlatePolicyResponse.confirmation` and `PlateResponse.format/plate_type/status` — Task 2's orval regen depends on this. JSON wire values are unchanged (StrEnums serialize to their values).

- [ ] **Step 1: Drop the child count from DeletePlate's conflict message** (the count is a visibility oracle — it counts children the caller may not be allowed to see). In `backend/src/cellar/application/inventory/registered_plates.py` replace:

```python
            children = await self._repo.find_children(input.workspace_id, input.plate_id)
            if children:
                return Failure(
                    ConflictError(
                        f"Cannot delete plate '{plate.barcode.value}': "
                        f"it has {len(children)} child plate(s)"
                    )
                )
```

with:

```python
            children = await self._repo.find_children(input.workspace_id, input.plate_id)
            if children:
                # No count: it would tally children the caller may not see
                # (private-org daughters), leaking existence through arithmetic.
                return Failure(
                    ConflictError(
                        f"Cannot delete plate '{plate.barcode.value}': it has child plates"
                    )
                )
```

Then `grep -rn "child plate(s)" backend/tests/` and update any assertion on the old message to the new string.

- [ ] **Step 2: Type `confirmation` as the enum in the policy response.** In `backend/src/cellar/interface/routes/org_plate_policies.py`:

```python
class OrgPlatePolicyResponse(BaseModel):
    org_id: uuid.UUID
    require_approval: bool
    confirmation: LoanConfirmationMode
    default_due_days: int | None = None
    plates_private: bool
    version: int

    @classmethod
    def from_domain(cls, p: OrgPlatePolicy) -> OrgPlatePolicyResponse:
        return cls(
            org_id=p.org_id,
            require_approval=p.require_approval,
            confirmation=p.confirmation,
            default_due_days=p.default_due_days,
            plates_private=p.plates_private,
            version=p.version,
        )
```

(Only two edits: the field annotation `str` → `LoanConfirmationMode`, and `p.confirmation.value` → `p.confirmation`. `LoanConfirmationMode` is already imported in this file.)

- [ ] **Step 3: Type `PlateResponse` enum fields as enums** (root-cause enablement for Task 2's clean `RegisteredPlate = PlateResponse` alias — orval currently generates `plate_type: string` because the backend says `str`). In `backend/src/cellar/interface/routes/registered_plates.py`, change `PlateResponse`:

```python
class PlateResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    barcode: str
    plate_label: str
    format: PlateFormat
    plate_type: PlateType
    well_map: dict[str, WellEntryModel] | None = None
    status: PlateStatus
    storage_location_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None
    parent_plate_id: uuid.UUID | None = None
    registered_by: uuid.UUID
    notes: str | None = None
    owner_org_id: uuid.UUID | None = None
```

and in `from_domain` pass the enums straight through: `format=p.format`, `plate_type=p.plate_type`, `status=p.status` (drop the three `.value` calls). `PlateFormat` is already imported from `cellar.domain.screening_assay.enums` in this file; `PlateStatus`/`PlateType` are already imported from `cellar.domain.inventory.enums`. Leave `MoleculePlateResponse` alone (it's fed by a read-model row of plain strings).

- [ ] **Step 4: Extend the policy PUT test to vary all four fields** (S4 consumes `require_approval`/`confirmation`/`default_due_days`; today only `plates_private` is ever round-tripped). In `backend/tests/api/test_org_plate_policies.py`, inside `TestSetOrgPlatePolicy`, replace `test_put_as_admin_flips_plates_private` with:

```python
    async def test_put_as_admin_round_trips_all_fields(
        self, client: AsyncClient, api_app: FastAPI
    ) -> None:
        org_id = uuid.uuid4()
        body = _body(
            require_approval=False,
            confirmation="none",
            default_due_days=30,
            plates_private=True,
        )
        resp = await client.put(f"/api/v1/org-plate-policies/{org_id}", json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["require_approval"] is False
        assert data["confirmation"] == "none"
        assert data["default_due_days"] == 30
        assert data["plates_private"] is True
        assert data["version"] == 1  # first PUT is an INSERT

        got = await client.get(f"/api/v1/org-plate-policies/{org_id}")
        assert got.status_code == 200
        fetched = got.json()
        assert fetched["require_approval"] is False
        assert fetched["confirmation"] == "none"
        assert fetched["default_due_days"] == 30
        assert fetched["plates_private"] is True
        # Sanity for the no-hidden-write test's counter: a real PUT DOES create a row.
        assert await _policy_row_count(api_app, org_id) == 1
```

Keep every other test in the file unchanged. If another test in the file references the removed test name, update it.

- [ ] **Step 5: Run the touched suites.**

Run: `cd backend && uv run pytest tests/unit -x -q` — expect pass (no unit test asserts the old strings; if one does, update it).
Run (requires `make up` infra): `cd backend && uv run pytest tests/api/test_org_plate_policies.py tests/api/test_registered_plates.py -q` — expect pass.

- [ ] **Step 6: Commit.**

```bash
git commit -m "fix(backend): S2 triage — countless delete-conflict message, enum-typed policy/plate responses, 4-field policy PUT test" -- backend/src/cellar/application/inventory/registered_plates.py backend/src/cellar/interface/routes/org_plate_policies.py backend/src/cellar/interface/routes/registered_plates.py backend/tests/api/test_org_plate_policies.py backend/tests/api/test_registered_plates.py
```

(Drop `backend/tests/api/test_registered_plates.py` from the pathspec if it needed no change.)

---

### Task 2: Frontend cleanup batch (orval regen + items b, d, e)

**Files:**
- Regenerate: `frontend/src/shared/lib/api/model/**`, `frontend/src/shared/lib/api/endpoints.ts` (orval, backend live on :8000)
- Modify: `frontend/src/features/inventory/components/plate-list.tsx` (/me error fallback)
- Modify: `frontend/src/features/inventory/hooks/use-org-plate-policy.ts` (invalidate plates on save)
- Modify: `frontend/src/features/inventory/hooks/query-keys.ts` (centralize `PLATES_KEY`)
- Modify: `frontend/src/features/inventory/hooks/use-plates.ts` (import `PLATES_KEY`; type from generated model)
- Modify: `frontend/src/features/inventory/types/plates.ts` (alias generated types, delete hand-rolled shapes)
- Modify: `frontend/src/features/inventory/components/org-plate-policy-dialog.tsx` (typed `confirmation`, drop cast)
- Tests: existing `use-plates.test.tsx`, `org-plate-policy-dialog.test.tsx`, `use-current-user.test.tsx` must stay green; extend `use-plates.test.tsx` per Step 5.

**Interfaces:**
- Consumes: Task 1's enum-typed OpenAPI.
- Produces: `RegisteredPlate` is now `export type RegisteredPlate = PlateResponse`; `PlateType`/`PlateStatus` in `types/plates.ts` are aliases of the generated unions; `PLATES_KEY` lives in `features/inventory/hooks/query-keys.ts`. Tasks 7–9 import all of these.

- [ ] **Step 1: Regenerate orval.** Backend must be serving `:8000`:

```bash
make up            # idempotent — Postgres/Valkey up + migrations
make dev-be        # backend on :8000 (backgrounds itself; logs via make logs-dev)
# wait until: curl -sf http://localhost:8000/openapi.json >/dev/null
cd frontend && pnpm generate:api
make stop          # stop dev servers again (leave infra up)
```

Review the diff: expect `orgPlatePolicyResponse.ts` to gain `confirmation: LoanConfirmationMode` and `plateResponse.ts` to gain `format: PlateFormat; plate_type: PlateType; status: PlateStatus` (generated unions). The regen rewrites the whole `model/` dir — additive changes only is the expected shape; investigate anything that *removes* a type you didn't expect.

- [ ] **Step 2: Centralize `PLATES_KEY` and invalidate it on policy save.** In `frontend/src/features/inventory/hooks/query-keys.ts` add:

```ts
export const PLATES_KEY = ["plates"] as const;
```

In `frontend/src/features/inventory/hooks/use-plates.ts` delete the local `const PLATES_KEY = ["plates"];` and import it: `import { PLATES_KEY } from "./query-keys";` (keep every usage identical — the crud-hooks factory takes it as before; `as const` readonly tuples are accepted by TanStack keys, spread/copy with `[...PLATES_KEY]` only if a mutable-array type error appears).

In `frontend/src/features/inventory/hooks/use-org-plate-policy.ts`:

```ts
import { PLATES_KEY } from "./query-keys";
// ... inside useSetOrgPlatePolicy's onSuccess:
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: orgPlatePolicyKey(orgId) });
      // Privacy flips change which plates other users' lists contain.
      qc.invalidateQueries({ queryKey: PLATES_KEY });
      showSuccess("Org plate policy updated");
    },
```

- [ ] **Step 3: Alias the generated types; delete the hand-rolled mirrors.** In `frontend/src/features/inventory/types/plates.ts` replace the hand-rolled `PlateType`, `PlateStatus`, and `RegisteredPlate` definitions with aliases (keep `plateTypeLabels`, `plateStatusLabels`, `WellMapping`, and any other local-only types exactly as they are):

```ts
import type {
  PlateResponse,
  PlateStatus as GeneratedPlateStatus,
  PlateType as GeneratedPlateType,
} from "@/shared/lib/api/model";

/** Generated from the backend OpenAPI — do not redefine shapes here (CLAUDE.md). */
export type RegisteredPlate = PlateResponse;
export type PlateType = GeneratedPlateType;
export type PlateStatus = GeneratedPlateStatus;
```

If the generated model exports value-side const objects (orval's `export const PlateType = {...} as const` pattern) and any runtime code iterates the hand-rolled union values, re-export the const too: `export { PlateType as PlateTypeValues } from "@/shared/lib/api/model";` — check usages first; skip if nobody iterates.

Then fix compile fallout: run `cd frontend && pnpm exec tsc --noEmit`. Expected fallout class: fields that were `X | null` are now `X | null | undefined` (generated optionals) — call sites using `p.storage_location_id ?? null` style already tolerate it; adjust the few that don't (prefer `?? null` at the use site over widening types). `plateTypeLabels[plate.plate_type]` keeps type-checking because the alias preserves the union.

- [ ] **Step 4: Type the policy dialog's `confirmation` state; drop the cast.** In `frontend/src/features/inventory/components/org-plate-policy-dialog.tsx`:

```ts
import { LoanConfirmationMode } from "@/shared/lib/api/model";
// state:
const [confirmation, setConfirmation] = useState<LoanConfirmationMode>(
  LoanConfirmationMode.admin_confirm,
);
// on save — pass `confirmation` directly, delete the
// `as (typeof CONFIRMATION_OPTIONS)[number]["value"]` cast.
```

Keep `CONFIRMATION_OPTIONS` for labels but derive its `value` type from the enum: `value: LoanConfirmationMode`. When loading an existing policy into state, `setConfirmation(policy.confirmation)` now type-checks with no cast (generated response is the union after Step 1). Note the previous default state was `"kiosk_scan"` — preserve whatever default the dialog currently uses when no policy row exists (it hydrates from the GET's server default `admin_confirm` anyway; do not change observable behavior).

- [ ] **Step 5: /me failure must not permanently gate the plates list.** In `frontend/src/features/inventory/components/plate-list.tsx`:

```ts
const { data: me, isError: meFailed } = useCurrentUser();
// "My org" needs /me. If /me failed, fall back to un-filtered (All orgs)
// rather than gating the list forever behind a query that will never run.
const ownerOrgId =
  filterOrg === MY_ORG
    ? meFailed
      ? undefined
      : (me?.org_id ?? undefined)
    : filterOrg === ALL_ORGS
      ? undefined
      : filterOrg;
const { data: plates, isLoading, error } = usePlates(
  { ...filters, owner_org_id: ownerOrgId },
  { enabled: filterOrg !== MY_ORG || me !== undefined || meFailed },
);

useEffect(() => {
  if (meFailed && filterOrg === MY_ORG) {
    showError("Could not resolve your organization — showing all orgs");
  }
}, [meFailed, filterOrg]);
```

(`showError` from `@/shared/lib/toast`; add the import. `useEffect` from react if not already imported.)

Extend `frontend/src/features/inventory/hooks/use-plates.test.tsx` — or, if the gating test lives in a `plate-list` test, that file — with one test: mock `customInstance` so `GET /api/v1/user/me` rejects and `GET /api/v1/plates` resolves `[]`; render the list (or call the hook wiring) and assert the plates request **was** issued (the list is not permanently gated). Follow the existing mock pattern in that file (`vi.mock("@/shared/lib/api/custom-instance", ...)` + fresh `QueryClient` with `retry: false`).

- [ ] **Step 6: Verify.**

Run: `cd frontend && pnpm exec tsc --noEmit` — exit 0.
Run: `cd frontend && pnpm exec vitest run src/features/inventory src/shared/hooks` — all pass.
Run: `cd frontend && pnpm exec biome check src/features/inventory` — exit 0.

- [ ] **Step 7: Commit** (explicit paths; do NOT include `frontend/package.json`/`pnpm-lock.yaml` — the working tree carries the user's unrelated SDK bump there):

```bash
git add frontend/src/shared/lib/api
git commit -m "fix(frontend): S2 triage — /me error fallback, policy-save invalidates plates, generated-type aliases (orval regen)" -- frontend/src/shared/lib/api frontend/src/features/inventory
```

---

### Task 3: PlateGroup domain aggregate + `RegisteredPlate.group_id`

**Files:**
- Create: `backend/src/cellar/domain/inventory/plate_group.py`
- Modify: `backend/src/cellar/domain/inventory/events.py` (four new events)
- Modify: `backend/src/cellar/domain/inventory/registered_plate.py` (`group_id` field + `assign_to_group`)
- Test: `backend/tests/unit/test_plate_group.py` (new), `backend/tests/unit/test_registered_plate.py` (extend)

**Interfaces:**
- Consumes: `AggregateRoot` (`cellar.domain.shared.entity`), `ValidationError`, `DomainEvent` base.
- Produces: `PlateGroup` with `create(...)` / `update(...)` / `move_to(...)`; events `PlateGroupCreated/PlateGroupUpdated/PlateGroupMoved/PlateGroupDeleted`; `RegisteredPlate.group_id: uuid.UUID | None` + `assign_to_group(group_id)`. Task 4 persists these; Task 5 calls them.

**Decisions locked here (record in the module docstring):** `owner_org_id` is required (groups are net-new — no legacy NULL rows to honor, unlike plates). `group_type` is a free optional string ≤100 chars; the FE picker sources suggestions from the `plate_group_type` ControlledVocabulary but the domain does NOT validate membership (no live CV-validation precedent exists anywhere in the codebase — first-consumer status deferred until a real need). `derive()` does NOT copy `group_id` — grouping is manual curation, not lineage.

- [ ] **Step 1: Write failing unit tests** — `backend/tests/unit/test_plate_group.py`:

```python
"""Unit tests for the PlateGroup aggregate."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.inventory.events import (
    PlateGroupCreated,
    PlateGroupMoved,
    PlateGroupUpdated,
)
from cellar.domain.inventory.plate_group import PlateGroup
from cellar.domain.shared.errors import ValidationError

WS = uuid.uuid4()
ORG = uuid.uuid4()
USER = uuid.uuid4()


def _group(**overrides) -> PlateGroup:
    kwargs = dict(
        workspace_id=WS,
        owner_org_id=ORG,
        name="Vendor Library A",
        created_by=USER,
    )
    kwargs.update(overrides)
    return PlateGroup.create(**kwargs)


class TestCreate:
    def test_create_emits_event_and_strips_name(self) -> None:
        g = _group(name="  Vendor Library A  ")
        assert g.name == "Vendor Library A"
        assert g.workspace_id == WS
        assert g.owner_org_id == ORG
        assert g.parent_group_id is None
        assert g.group_type is None
        assert g.version == 1
        events = g.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], PlateGroupCreated)
        assert events[0].name == "Vendor Library A"
        assert events[0].owner_org_id == ORG

    def test_create_with_parent_and_type(self) -> None:
        parent_id = uuid.uuid4()
        g = _group(parent_group_id=parent_id, group_type="vendor", description="desc")
        assert g.parent_group_id == parent_id
        assert g.group_type == "vendor"
        assert g.description == "desc"

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _group(name="   ")

    def test_overlong_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _group(name="x" * 301)

    def test_overlong_group_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _group(group_type="x" * 101)


class TestUpdate:
    def test_update_fields_and_event(self) -> None:
        g = _group()
        g.clear_events()
        g.update(name="Renamed", group_type="screening", description=None)
        assert g.name == "Renamed"
        assert g.group_type == "screening"
        assert g.description is None
        events = g.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], PlateGroupUpdated)

    def test_update_untouched_fields_keep_values(self) -> None:
        g = _group(group_type="vendor", description="keep me")
        g.clear_events()
        g.update(name="Renamed")
        assert g.group_type == "vendor"
        assert g.description == "keep me"

    def test_update_empty_name_rejected(self) -> None:
        g = _group()
        with pytest.raises(ValidationError):
            g.update(name="  ")


class TestMove:
    def test_move_to_new_parent_emits_event(self) -> None:
        g = _group()
        g.clear_events()
        new_parent = uuid.uuid4()
        g.move_to(new_parent)
        assert g.parent_group_id == new_parent
        events = g.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], PlateGroupMoved)
        assert events[0].old_parent_group_id is None
        assert events[0].new_parent_group_id == new_parent

    def test_move_to_root(self) -> None:
        g = _group(parent_group_id=uuid.uuid4())
        g.clear_events()
        g.move_to(None)
        assert g.parent_group_id is None

    def test_move_to_self_rejected(self) -> None:
        g = _group()
        with pytest.raises(ValidationError):
            g.move_to(g.id)
```

And append to `backend/tests/unit/test_registered_plate.py` (match that file's existing style for constructing plates — reuse its helpers/factories if present):

```python
class TestGroupAssignment:
    def test_assign_and_clear_group(self) -> None:
        plate = _make_plate()  # use the file's existing plate factory/helper
        gid = uuid.uuid4()
        plate.assign_to_group(gid)
        assert plate.group_id == gid
        plate.assign_to_group(None)
        assert plate.group_id is None

    def test_derive_does_not_copy_group(self) -> None:
        plate = _make_plate()
        plate.assign_to_group(uuid.uuid4())
        child = plate.derive(
            barcode=Barcode(value="CHILD-001"),
            plate_label="child",
            plate_type=PlateType.DAUGHTER,
            registered_by=uuid.uuid4(),
        )
        assert child.group_id is None
```

(If `test_registered_plate.py` has no shared factory, construct the plate inline exactly as its neighboring tests do.)

- [ ] **Step 2: Run to verify failure.**

Run: `cd backend && uv run pytest tests/unit/test_plate_group.py -q`
Expected: FAIL — `ModuleNotFoundError`/`ImportError` (plate_group does not exist).

- [ ] **Step 3: Implement.** Add to `backend/src/cellar/domain/inventory/events.py` (same dataclass style as the file's existing events):

```python
@dataclass(frozen=True, kw_only=True)
class PlateGroupCreated(DomainEvent):
    name: str
    owner_org_id: uuid.UUID
    parent_group_id: uuid.UUID | None
    created_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class PlateGroupUpdated(DomainEvent):
    name: str


@dataclass(frozen=True, kw_only=True)
class PlateGroupMoved(DomainEvent):
    old_parent_group_id: uuid.UUID | None
    new_parent_group_id: uuid.UUID | None


@dataclass(frozen=True, kw_only=True)
class PlateGroupDeleted(DomainEvent):
    name: str
    owner_org_id: uuid.UUID
```

Create `backend/src/cellar/domain/inventory/plate_group.py`:

```python
"""PlateGroup aggregate — an open, org-owned hierarchy for organizing plates.

Adjacency-list tree: any group may be root, any group may nest. A plate
belongs to at most one group (cross-cutting labels are tags). Invariants that
need sibling/tree knowledge (name uniqueness per parent, no cycles, parent in
same workspace+org) are enforced at the application layer + DB constraints —
the aggregate alone cannot see its siblings.

Decisions:
- ``owner_org_id`` is required. Groups are net-new (no legacy NULL-owner rows
  to honor, unlike plates); an unowned hierarchy has no policy to govern it.
- ``group_type`` is a free optional string. The UI sources suggestions from
  the ``plate_group_type`` ControlledVocabulary, but membership is not
  domain-validated (no live CV-validation precedent in this codebase).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.inventory.events import (
    PlateGroupCreated,
    PlateGroupMoved,
    PlateGroupUpdated,
)
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError

MAX_NAME_LEN = 300
MAX_GROUP_TYPE_LEN = 100


def _validated_name(name: str) -> str:
    cleaned = name.strip() if name else ""
    if not cleaned:
        raise ValidationError("Group name must not be empty")
    if len(cleaned) > MAX_NAME_LEN:
        raise ValidationError(f"Group name must be at most {MAX_NAME_LEN} characters")
    return cleaned


def _validated_group_type(group_type: str | None) -> str | None:
    if group_type is None:
        return None
    cleaned = group_type.strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_GROUP_TYPE_LEN:
        raise ValidationError(
            f"group_type must be at most {MAX_GROUP_TYPE_LEN} characters"
        )
    return cleaned


class PlateGroup(AggregateRoot):
    """An org-owned node in the plate-organization hierarchy."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        owner_org_id: uuid.UUID,
        name: str,
        parent_group_id: uuid.UUID | None = None,
        group_type: str | None = None,
        description: str | None = None,
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.owner_org_id = owner_org_id
        self.name = _validated_name(name)
        self.parent_group_id = parent_group_id
        self.group_type = _validated_group_type(group_type)
        self.description = description
        self.created_by = created_by

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        owner_org_id: uuid.UUID,
        name: str,
        created_by: uuid.UUID,
        parent_group_id: uuid.UUID | None = None,
        group_type: str | None = None,
        description: str | None = None,
    ) -> PlateGroup:
        group = cls(
            workspace_id=workspace_id,
            owner_org_id=owner_org_id,
            name=name,
            parent_group_id=parent_group_id,
            group_type=group_type,
            description=description,
            created_by=created_by,
        )
        group.register_event(
            PlateGroupCreated(
                aggregate_id=group.id,
                aggregate_type="PlateGroup",
                workspace_id=workspace_id,
                name=group.name,
                owner_org_id=owner_org_id,
                parent_group_id=parent_group_id,
                created_by=created_by,
            )
        )
        return group

    def update(
        self,
        *,
        name: str | None = None,
        group_type: str | None = ...,  # type: ignore[assignment]
        description: str | None = ...,  # type: ignore[assignment]
    ) -> None:
        """Update mutable fields. Uses sentinel ``...`` for optional nullable fields."""
        if name is not None:
            self.name = _validated_name(name)
        if group_type is not ...:
            self.group_type = _validated_group_type(group_type)
        if description is not ...:
            self.description = description
        self.updated_at = datetime.now(UTC)
        self.register_event(
            PlateGroupUpdated(
                aggregate_id=self.id,
                aggregate_type="PlateGroup",
                workspace_id=self.workspace_id,
                name=self.name,
            )
        )

    def move_to(self, new_parent_group_id: uuid.UUID | None) -> None:
        """Reparent (None = make root). Cycle/same-org checks happen in the
        use case — the aggregate can only rule out the trivial self-cycle."""
        if new_parent_group_id == self.id:
            raise ValidationError("A group cannot be its own parent")
        old = self.parent_group_id
        self.parent_group_id = new_parent_group_id
        self.updated_at = datetime.now(UTC)
        self.register_event(
            PlateGroupMoved(
                aggregate_id=self.id,
                aggregate_type="PlateGroup",
                workspace_id=self.workspace_id,
                old_parent_group_id=old,
                new_parent_group_id=new_parent_group_id,
            )
        )
```

In `backend/src/cellar/domain/inventory/registered_plate.py`:
1. Add ctor kwarg `group_id: uuid.UUID | None = None` (right after `template_id`) and `self.group_id = group_id` in the body.
2. Add method (after `move`):

```python
    def assign_to_group(self, group_id: uuid.UUID | None) -> None:
        """Set or clear this plate's group. The plate-org == group-org
        invariant is enforced by the use case, which holds both aggregates."""
        self.group_id = group_id
        self.updated_at = datetime.now(UTC)
```

`register()` and `derive()` intentionally do NOT take/copy `group_id`.

- [ ] **Step 4: Run tests.**

Run: `cd backend && uv run pytest tests/unit/test_plate_group.py tests/unit/test_registered_plate.py -q`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git commit -m "feat(domain): PlateGroup aggregate + RegisteredPlate.group_id" -- backend/src/cellar/domain/inventory/plate_group.py backend/src/cellar/domain/inventory/events.py backend/src/cellar/domain/inventory/registered_plate.py backend/tests/unit/test_plate_group.py backend/tests/unit/test_registered_plate.py
```

---

### Task 4: Persistence — migration 062, ORM, repositories

**Files:**
- Create: `backend/alembic/versions/062_plate_groups.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/models.py` (`PlateGroupModel`; `group_id` on `RegisteredPlateModel`)
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_group_repository.py`
- Modify: `backend/src/cellar/domain/inventory/repository.py` (`PlateGroupRepository` protocol; `group_id` filter on `RegisteredPlateRepository.search`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/registered_plate_repository.py` (persist `group_id`; search filter)
- Test: `backend/tests/integration/inventory/test_plate_group_repository.py` (new)

**Interfaces:**
- Consumes: Task 3's `PlateGroup` aggregate.
- Produces: `PlateGroupRepository` protocol — exact signatures below; `RegisteredPlateRepository.search(..., group_id: uuid.UUID | None = None, ...)`. Task 5 consumes both.

- [ ] **Step 1: Migration.** Create `backend/alembic/versions/062_plate_groups.py`. Open `061_org_plate_policies.py` first and mirror its column-type idiom exactly (UUID/DateTime expressions). Shape:

```python
"""062 — plate_groups table + registered_plates.group_id

Revision ID: 062_plate_groups
Revises: 061_org_plate_policies
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "062_plate_groups"
down_revision = "061_org_plate_policies"
branch_labels = None
depends_on = None

# NULLS NOT DISTINCT (PG15+) is unavailable through sa.UniqueConstraint /
# op.create_index — raw SQL, exactly like migration 049. Needed because
# parent_group_id IS NULL for root groups and two roots must not share a name.
_CREATE_UNIQUE_SQL = """
CREATE UNIQUE INDEX uq_plate_groups_ws_org_parent_name ON plate_groups
    (workspace_id, owner_org_id, parent_group_id, name)
    NULLS NOT DISTINCT;
"""


def upgrade() -> None:
    op.create_table(
        "plate_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("owner_org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("parent_group_id", sa.Uuid(), nullable=True),
        sa.Column("group_type", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["parent_group_id"],
            ["plate_groups.id"],
            name="fk_plate_groups_parent",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_plate_groups_ws_org", "plate_groups", ["workspace_id", "owner_org_id"])
    op.create_index("ix_plate_groups_parent", "plate_groups", ["parent_group_id"])
    op.execute(_CREATE_UNIQUE_SQL)

    op.add_column("registered_plates", sa.Column("group_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_registered_plates_group",
        "registered_plates",
        "plate_groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_reg_plate_group", "registered_plates", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_reg_plate_group", table_name="registered_plates")
    op.drop_constraint("fk_registered_plates_group", "registered_plates", type_="foreignkey")
    op.drop_column("registered_plates", "group_id")
    op.execute("DROP INDEX IF EXISTS uq_plate_groups_ws_org_parent_name")
    op.drop_index("ix_plate_groups_parent", table_name="plate_groups")
    op.drop_index("ix_plate_groups_ws_org", table_name="plate_groups")
    op.drop_table("plate_groups")
```

(If 061 spells UUID columns differently — e.g. `postgresql.UUID(as_uuid=True)` — use that spelling throughout.)

- [ ] **Step 2: ORM.** In `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/models.py`, next to `OrgPlatePolicyModel` and mirroring its mixin usage:

```python
class PlateGroupModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """ORM model for the plate_groups table."""

    __tablename__ = "plate_groups"

    owner_org_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    parent_group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plate_groups.id", ondelete="RESTRICT"), nullable=True
    )
    group_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(nullable=False)
```

(Match the file's exact `Mapped`/`mapped_column` idiom — copy `OrgPlatePolicyModel`'s column style; don't re-declare the unique index in ORM, the migration owns it.) On `RegisteredPlateModel`, add:

```python
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plate_groups.id", ondelete="SET NULL"), nullable=True
    )
```

- [ ] **Step 3: Repository protocol.** In `backend/src/cellar/domain/inventory/repository.py` add (import `PlateGroup` at top with the other domain imports):

```python
@runtime_checkable
class PlateGroupRepository(Protocol):
    """Repository for PlateGroup aggregates."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> PlateGroup | None: ...
    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, owner_org_id: uuid.UUID | None = None
    ) -> list[PlateGroup]: ...
    async def find_children(
        self, workspace_id: uuid.UUID, parent_group_id: uuid.UUID
    ) -> list[PlateGroup]: ...
    async def find_by_name(
        self,
        workspace_id: uuid.UUID,
        owner_org_id: uuid.UUID,
        parent_group_id: uuid.UUID | None,
        name: str,
    ) -> PlateGroup | None: ...
    async def count_plates_by_group(
        self, workspace_id: uuid.UUID
    ) -> dict[uuid.UUID, int]: ...
    async def save(self, aggregate: PlateGroup) -> None: ...
    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None: ...
```

And extend `RegisteredPlateRepository.search` signature with `group_id: uuid.UUID | None = None,` (place after `owner_org_id`).

- [ ] **Step 4: SQLAlchemy repository.** Create `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_group_repository.py`, subclassing the same generic base as `SQLAlchemyOrgPlatePolicyRepository` (open that file and mirror imports/structure):

```python
"""SQLAlchemy repository for PlateGroup aggregates."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from cellar.domain.inventory.plate_group import PlateGroup
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import (
    PlateGroupModel,
    RegisteredPlateModel,
)


class SQLAlchemyPlateGroupRepository(SQLAlchemyRepository[PlateGroup, PlateGroupModel]):
    model_class = PlateGroupModel

    def _to_domain(self, model: PlateGroupModel) -> PlateGroup:
        return PlateGroup(
            id=model.id,
            workspace_id=model.workspace_id,
            owner_org_id=model.owner_org_id,
            name=model.name,
            parent_group_id=model.parent_group_id,
            group_type=model.group_type,
            description=model.description,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
        )

    def _to_model(self, aggregate: PlateGroup) -> PlateGroupModel:
        return PlateGroupModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            owner_org_id=aggregate.owner_org_id,
            name=aggregate.name,
            parent_group_id=aggregate.parent_group_id,
            group_type=aggregate.group_type,
            description=aggregate.description,
            created_by=aggregate.created_by,
            created_at=aggregate.created_at,
            updated_at=aggregate.updated_at,
            version=aggregate.version,
        )

    def _update_model(self, model: PlateGroupModel, aggregate: PlateGroup) -> None:
        model.owner_org_id = aggregate.owner_org_id
        model.name = aggregate.name
        model.parent_group_id = aggregate.parent_group_id
        model.group_type = aggregate.group_type
        model.description = aggregate.description
        model.updated_at = aggregate.updated_at

    async def find_by_workspace(
        self, workspace_id: uuid.UUID, *, owner_org_id: uuid.UUID | None = None
    ) -> list[PlateGroup]:
        stmt = select(PlateGroupModel).where(PlateGroupModel.workspace_id == workspace_id)
        if owner_org_id is not None:
            stmt = stmt.where(PlateGroupModel.owner_org_id == owner_org_id)
        stmt = stmt.order_by(PlateGroupModel.name)
        result = await self._session().execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_children(
        self, workspace_id: uuid.UUID, parent_group_id: uuid.UUID
    ) -> list[PlateGroup]:
        stmt = (
            select(PlateGroupModel)
            .where(
                PlateGroupModel.workspace_id == workspace_id,
                PlateGroupModel.parent_group_id == parent_group_id,
            )
            .order_by(PlateGroupModel.name)
        )
        result = await self._session().execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def find_by_name(
        self,
        workspace_id: uuid.UUID,
        owner_org_id: uuid.UUID,
        parent_group_id: uuid.UUID | None,
        name: str,
    ) -> PlateGroup | None:
        stmt = select(PlateGroupModel).where(
            PlateGroupModel.workspace_id == workspace_id,
            PlateGroupModel.owner_org_id == owner_org_id,
            PlateGroupModel.parent_group_id.is_(None)
            if parent_group_id is None
            else PlateGroupModel.parent_group_id == parent_group_id,
            PlateGroupModel.name == name,
        )
        result = await self._session().execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def count_plates_by_group(
        self, workspace_id: uuid.UUID
    ) -> dict[uuid.UUID, int]:
        stmt = (
            select(RegisteredPlateModel.group_id, func.count())
            .where(
                RegisteredPlateModel.workspace_id == workspace_id,
                RegisteredPlateModel.group_id.is_not(None),
            )
            .group_by(RegisteredPlateModel.group_id)
        )
        result = await self._session().execute(stmt)
        return {row[0]: row[1] for row in result.all()}
```

Adapt method-by-method to the actual base class: if `SQLAlchemyRepository` exposes the session differently than `self._session()` (open `base_repository.py` and check — e.g. `self._uow.session` or `self._session`), use the real accessor everywhere; `find_by_id_in_workspace`/`save`/`delete` come from the base if it provides them (OrgPlatePolicy's repo shows what the base gives you) — implement locally only what the base lacks.

- [ ] **Step 5: Persist `group_id` on plates.** In `registered_plate_repository.py`: add `group_id=model.group_id` to `_to_domain`, `group_id=aggregate.group_id` to `_to_model`, `model.group_id = aggregate.group_id` to `_update_model`, and in `search(...)` accept `group_id: uuid.UUID | None = None` and append `stmt = stmt.where(RegisteredPlateModel.group_id == group_id)` when it's not None (mirror how `owner_org_id` filtering is written in that method).

- [ ] **Step 6: Failing integration tests.** Create `backend/tests/integration/inventory/test_plate_group_repository.py` (mirror `test_registered_plate_repository.py`'s fixtures — `session_factory`, separate `AsyncUnitOfWork` per phase to force real round-trips):

```python
"""Integration tests for SQLAlchemyPlateGroupRepository."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from cellar.domain.inventory.plate_group import PlateGroup
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.shared.enums import PlateFormat
from cellar.domain.inventory.enums import PlateType
from cellar.domain.shared.value_objects import Barcode
from cellar.infrastructure.persistence.sqlalchemy.inventory.plate_group_repository import (
    SQLAlchemyPlateGroupRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.registered_plate_repository import (
    SQLAlchemyRegisteredPlateRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

WS = uuid.uuid4()
ORG = uuid.uuid4()
USER = uuid.uuid4()


def _group(name: str, parent: uuid.UUID | None = None) -> PlateGroup:
    return PlateGroup.create(
        workspace_id=WS, owner_org_id=ORG, name=name, created_by=USER,
        parent_group_id=parent,
    )


async def test_round_trip_and_children(session_factory) -> None:
    root = _group("Root")
    child = _group("Child", parent=root.id)
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateGroupRepository(uow)
        await repo.save(root)
        await repo.save(child)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateGroupRepository(uow)
        loaded = await repo.find_by_id_in_workspace(WS, child.id)
        assert loaded is not None
        assert loaded.parent_group_id == root.id
        kids = await repo.find_children(WS, root.id)
        assert [g.id for g in kids] == [child.id]
        all_org = await repo.find_by_workspace(WS, owner_org_id=ORG)
        assert {g.id for g in all_org} == {root.id, child.id}


async def test_root_name_unique_nulls_not_distinct(session_factory) -> None:
    ws = uuid.uuid4()
    a = PlateGroup.create(workspace_id=ws, owner_org_id=ORG, name="Dup", created_by=USER)
    b = PlateGroup.create(workspace_id=ws, owner_org_id=ORG, name="Dup", created_by=USER)
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateGroupRepository(uow)
        await repo.save(a)
        await uow.commit()
    with pytest.raises(IntegrityError):
        async with AsyncUnitOfWork(session_factory) as uow:
            repo = SQLAlchemyPlateGroupRepository(uow)
            await repo.save(b)
            await uow.commit()


async def test_find_by_name_null_parent(session_factory) -> None:
    ws = uuid.uuid4()
    g = PlateGroup.create(workspace_id=ws, owner_org_id=ORG, name="FindMe", created_by=USER)
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateGroupRepository(uow)
        await repo.save(g)
        await uow.commit()
    async with AsyncUnitOfWork(session_factory) as uow:
        repo = SQLAlchemyPlateGroupRepository(uow)
        found = await repo.find_by_name(ws, ORG, None, "FindMe")
        assert found is not None and found.id == g.id
        assert await repo.find_by_name(ws, ORG, None, "Nope") is None


async def test_plate_group_id_round_trip_and_counts(session_factory) -> None:
    ws = uuid.uuid4()
    g = PlateGroup.create(workspace_id=ws, owner_org_id=ORG, name="G", created_by=USER)
    plate = RegisteredPlate.register(
        workspace_id=ws, owner_org_id=ORG, barcode=Barcode(value=f"PG-{uuid.uuid4().hex[:8]}"),
        plate_label="p1", format=PlateFormat.F96, plate_type=PlateType.ASSAY,
        registered_by=USER,
    )
    plate.assign_to_group(g.id)
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyPlateGroupRepository(uow).save(g)
        await SQLAlchemyRegisteredPlateRepository(uow).save(plate)
        await uow.commit()

    async with AsyncUnitOfWork(session_factory) as uow:
        prepo = SQLAlchemyRegisteredPlateRepository(uow)
        loaded = await prepo.find_by_id_in_workspace(ws, plate.id)
        assert loaded is not None and loaded.group_id == g.id
        counts = await SQLAlchemyPlateGroupRepository(uow).count_plates_by_group(ws)
        assert counts == {g.id: 1}
        filtered = await prepo.search(ws, group_id=g.id)
        assert [p.id for p in filtered] == [plate.id]


async def test_group_delete_sets_plate_group_null(session_factory) -> None:
    ws = uuid.uuid4()
    g = PlateGroup.create(workspace_id=ws, owner_org_id=ORG, name="Doomed", created_by=USER)
    plate = RegisteredPlate.register(
        workspace_id=ws, owner_org_id=ORG, barcode=Barcode(value=f"PG-{uuid.uuid4().hex[:8]}"),
        plate_label="p1", format=PlateFormat.F96, plate_type=PlateType.ASSAY,
        registered_by=USER,
    )
    plate.assign_to_group(g.id)
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyPlateGroupRepository(uow).save(g)
        await SQLAlchemyRegisteredPlateRepository(uow).save(plate)
        await uow.commit()
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyPlateGroupRepository(uow).delete(ws, g.id)
        await uow.commit()
    async with AsyncUnitOfWork(session_factory) as uow:
        loaded = await SQLAlchemyRegisteredPlateRepository(uow).find_by_id_in_workspace(ws, plate.id)
        assert loaded is not None and loaded.group_id is None  # DB SET NULL
```

Fix the test file's constructor/UoW idioms against the real neighboring integration tests (e.g. if `AsyncUnitOfWork` isn't used as an async context manager with `.commit()` inside, or repos take `(uow)` differently — mirror `test_registered_plate_repository.py` exactly; the intent of each test is what's binding, plus: unique-name violation, NULLS NOT DISTINCT on root, SET NULL on delete, counts, search filter).

- [ ] **Step 7: Run migration + tests.**

Run: `make migrate` (or `cd backend && uv run alembic upgrade head`) — applies 062.
Run: `cd backend && uv run pytest tests/integration/inventory/test_plate_group_repository.py -q` — PASS (testcontainers spins its own PG and runs migrations).
Run: `cd backend && uv run alembic downgrade 061_org_plate_policies && uv run alembic upgrade head` against the dev DB — both succeed (downgrade sanity).

- [ ] **Step 8: Commit.**

```bash
git commit -m "feat(persistence): plate_groups table (migration 062), PlateGroup repository, plate group_id" -- backend/alembic/versions/062_plate_groups.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/models.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_group_repository.py backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/registered_plate_repository.py backend/src/cellar/domain/inventory/repository.py backend/tests/integration/inventory/test_plate_group_repository.py
```

---

### Task 5: Application use cases + tree logic + DI wiring

**Files:**
- Create: `backend/src/cellar/application/inventory/plate_groups.py`
- Modify: `backend/src/cellar/application/inventory/plate_visibility.py` (add `can_view_owner`)
- Modify: `backend/src/cellar/application/inventory/registered_plates.py` (`group_id` on `ListPlatesQuery` + pass-through)
- Modify: `backend/src/cellar/infrastructure/di/_inventory.py` (bindings)
- Modify: `backend/src/cellar/interface/dependencies/_inventory.py` (Dep aliases)
- Modify: `backend/src/cellar/interface/dependencies/__init__.py` (export the new Deps — check how existing Deps are exported and mirror)
- Test: `backend/tests/unit/test_plate_group_tree.py` (pure tree/cycle logic)

**Interfaces:**
- Consumes: Task 3 aggregate, Task 4 repos, existing `PlateVisibilityService`, `require_editor/require_workspace_role/require_same_workspace`, `EventDispatcherProtocol`, `UnitOfWork`.
- Produces (Task 6 imports these exact names): commands/queries `CreatePlateGroupCommand{workspace_id, name, created_by, owner_org_id: uuid|None, parent_group_id: uuid|None, group_type: str|None, description: str|None}`, `UpdatePlateGroupCommand{workspace_id, group_id, name: str|None, group_type: str|None|UNSET, description: str|None|UNSET}`, `MovePlateGroupCommand{workspace_id, group_id, new_parent_group_id: uuid|None}`, `DeletePlateGroupCommand{workspace_id, group_id}`, `GetGroupTreeQuery{workspace_id, org_id: uuid|None}`, `AssignPlatesToGroupCommand{workspace_id, group_id, plate_ids: list[uuid]}`, `RemovePlatesFromGroupCommand{workspace_id, group_id, plate_ids: list[uuid]}`; use cases `CreatePlateGroup/UpdatePlateGroup/MovePlateGroup/DeletePlateGroup/GetGroupTree/AssignPlatesToGroup/RemovePlatesFromGroup`; DTO `GroupTreeNode{group: PlateGroup, plate_count: int, children: list[GroupTreeNode]}`; `GetGroupTree` returns `Result[GroupTree, DomainError]` where `GroupTree{org_id: uuid.UUID, roots: list[GroupTreeNode]}`; pure helpers `build_tree(groups, counts) -> list[GroupTreeNode]` and `is_descendant(groups_by_id, ancestor_id, candidate_id) -> bool`.

- [ ] **Step 1: Failing unit tests for the pure tree logic** — `backend/tests/unit/test_plate_group_tree.py`:

```python
"""Unit tests for plate-group tree building + cycle detection (pure logic)."""

from __future__ import annotations

import uuid

from cellar.application.inventory.plate_groups import build_tree, is_descendant
from cellar.domain.inventory.plate_group import PlateGroup

WS = uuid.uuid4()
ORG = uuid.uuid4()
USER = uuid.uuid4()


def _g(name: str, parent: uuid.UUID | None = None) -> PlateGroup:
    return PlateGroup.create(
        workspace_id=WS, owner_org_id=ORG, name=name, created_by=USER,
        parent_group_id=parent,
    )


def test_build_tree_nests_and_counts() -> None:
    root = _g("Root")
    a = _g("A", parent=root.id)
    b = _g("B", parent=root.id)
    leaf = _g("Leaf", parent=a.id)
    nodes = build_tree([root, a, b, leaf], {a.id: 2, leaf.id: 5})
    assert len(nodes) == 1
    assert nodes[0].group.id == root.id
    assert nodes[0].plate_count == 0
    kids = {n.group.name: n for n in nodes[0].children}
    assert set(kids) == {"A", "B"}
    assert kids["A"].plate_count == 2
    assert kids["A"].children[0].group.id == leaf.id
    assert kids["A"].children[0].plate_count == 5


def test_build_tree_orphan_parent_becomes_root() -> None:
    # Parent id points at a group not in the fetched set (e.g. data from
    # another org filter) — tolerate by promoting to root, never crash.
    orphan = _g("Orphan", parent=uuid.uuid4())
    nodes = build_tree([orphan], {})
    assert len(nodes) == 1
    assert nodes[0].group.id == orphan.id


def test_build_tree_sorts_siblings_by_name() -> None:
    b = _g("Beta")
    a = _g("Alpha")
    nodes = build_tree([b, a], {})
    assert [n.group.name for n in nodes] == ["Alpha", "Beta"]


def test_is_descendant() -> None:
    root = _g("Root")
    mid = _g("Mid", parent=root.id)
    leaf = _g("Leaf", parent=mid.id)
    by_id = {g.id: g for g in (root, mid, leaf)}
    assert is_descendant(by_id, root.id, leaf.id) is True
    assert is_descendant(by_id, mid.id, leaf.id) is True
    assert is_descendant(by_id, leaf.id, root.id) is False
    assert is_descendant(by_id, leaf.id, leaf.id) is True  # self counts


def test_is_descendant_tolerates_broken_chain() -> None:
    stray = _g("Stray", parent=uuid.uuid4())  # parent not in map
    by_id = {stray.id: stray}
    assert is_descendant(by_id, uuid.uuid4(), stray.id) is False
```

Run: `cd backend && uv run pytest tests/unit/test_plate_group_tree.py -q` — FAIL (module missing).

- [ ] **Step 2: Add `can_view_owner` to the visibility service.** In `backend/src/cellar/application/inventory/plate_visibility.py`, add alongside `can_view` (and refactor `can_view` to delegate):

```python
    def can_view_owner(
        self, owner_org_id: uuid.UUID | None, excluded: set[uuid.UUID]
    ) -> bool:
        """Visibility by owner org alone — for org-owned things that aren't
        plates (plate groups). Same rule: hidden iff owner org is excluded."""
        return owner_org_id not in excluded
```

and make `can_view` return `self.can_view_owner(plate.owner_org_id, excluded)`.

- [ ] **Step 3: Implement `backend/src/cellar/application/inventory/plate_groups.py`.** Full module (guards first, railway results, hidden==missing 404s, org-scope 403 on tree):

```python
"""PlateGroup use cases — open hierarchy CRUD, tree read model, plate assignment.

Visibility (spec §5): all reads/writes consume PlateVisibilityService's
excluded_org_ids. A group whose owner org is private-and-foreign 404s exactly
like a missing one; the org-scoped tree read 403s for non-members instead
(the org's existence is public via the directory — only its contents are not).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_editor,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.query import Query
from cellar.application.shared.sentinel import UNSET
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.events import PlateGroupDeleted
from cellar.domain.inventory.plate_group import PlateGroup
from cellar.domain.inventory.repository import (
    PlateGroupRepository,
    RegisteredPlateRepository,
)
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Commands / Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class CreatePlateGroupCommand(Command):
    workspace_id: uuid.UUID
    name: str
    created_by: uuid.UUID
    owner_org_id: uuid.UUID | None = None
    parent_group_id: uuid.UUID | None = None
    group_type: str | None = None
    description: str | None = None


@dataclass(frozen=True, kw_only=True)
class UpdatePlateGroupCommand(Command):
    workspace_id: uuid.UUID
    group_id: uuid.UUID
    name: str | None = None
    group_type: str | None | object = UNSET
    description: str | None | object = UNSET


@dataclass(frozen=True, kw_only=True)
class MovePlateGroupCommand(Command):
    workspace_id: uuid.UUID
    group_id: uuid.UUID
    new_parent_group_id: uuid.UUID | None


@dataclass(frozen=True, kw_only=True)
class DeletePlateGroupCommand(Command):
    workspace_id: uuid.UUID
    group_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class AssignPlatesToGroupCommand(Command):
    workspace_id: uuid.UUID
    group_id: uuid.UUID
    plate_ids: list[uuid.UUID]


@dataclass(frozen=True, kw_only=True)
class RemovePlatesFromGroupCommand(Command):
    workspace_id: uuid.UUID
    group_id: uuid.UUID
    plate_ids: list[uuid.UUID]


@dataclass(frozen=True, kw_only=True)
class GetGroupTreeQuery(Query):
    workspace_id: uuid.UUID
    org_id: uuid.UUID | None = None  # None -> caller's own org


# ---------------------------------------------------------------------------
# Tree DTOs + pure helpers (unit-tested directly)
# ---------------------------------------------------------------------------


@dataclass
class GroupTreeNode:
    group: PlateGroup
    plate_count: int
    children: list[GroupTreeNode] = field(default_factory=list)


@dataclass
class GroupTree:
    org_id: uuid.UUID
    roots: list[GroupTreeNode]


def build_tree(
    groups: list[PlateGroup], counts: dict[uuid.UUID, int]
) -> list[GroupTreeNode]:
    """Assemble nested nodes from a flat fetch. A node whose parent isn't in
    the fetched set is promoted to root (defensive — never crash the page)."""
    nodes = {g.id: GroupTreeNode(group=g, plate_count=counts.get(g.id, 0)) for g in groups}
    roots: list[GroupTreeNode] = []
    for g in groups:
        node = nodes[g.id]
        if g.parent_group_id is not None and g.parent_group_id in nodes:
            nodes[g.parent_group_id].children.append(node)
        else:
            roots.append(node)
    for node in nodes.values():
        node.children.sort(key=lambda n: n.group.name.lower())
    roots.sort(key=lambda n: n.group.name.lower())
    return roots


def is_descendant(
    groups_by_id: dict[uuid.UUID, PlateGroup],
    ancestor_id: uuid.UUID,
    candidate_id: uuid.UUID,
) -> bool:
    """True iff candidate is ancestor itself or sits anywhere under it.
    Walks parent pointers; tolerates chains that leave the map."""
    seen: set[uuid.UUID] = set()
    current: uuid.UUID | None = candidate_id
    while current is not None and current not in seen:
        if current == ancestor_id:
            return True
        seen.add(current)
        parent = groups_by_id.get(current)
        current = parent.parent_group_id if parent else None
    return False


def _not_found(group_id: uuid.UUID) -> Failure:
    return Failure(NotFoundError("PlateGroup", str(group_id)))


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------


class CreatePlateGroup:
    """Create a group; owner org defaults to the caller's org."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateGroupRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: CreatePlateGroupCommand, auth: AuthContext | None = None
    ) -> Result[PlateGroup, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        if (
            auth is not None
            and input.owner_org_id is not None
            and input.owner_org_id != auth.org_id
            and not auth.is_admin
        ):
            raise AuthorizationError("Cannot create groups for another organization")

        owner_org_id = input.owner_org_id if input.owner_org_id is not None else (
            auth.org_id if auth else None
        )
        if owner_org_id is None:
            return Failure(
                ValidationError("owner_org_id is required (caller has no organization)")
            )

        async with self._uow:
            if input.parent_group_id is not None:
                parent = await self._repo.find_by_id_in_workspace(
                    input.workspace_id, input.parent_group_id
                )
                if parent is None:
                    return _not_found(input.parent_group_id)
                excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
                if not self._visibility.can_view_owner(parent.owner_org_id, excluded):
                    return _not_found(input.parent_group_id)
                if parent.owner_org_id != owner_org_id:
                    return Failure(
                        ValidationError("Parent group belongs to a different organization")
                    )

            dup = await self._repo.find_by_name(
                input.workspace_id, owner_org_id, input.parent_group_id, input.name.strip()
            )
            if dup is not None:
                return Failure(
                    ConflictError(f"A group named '{input.name.strip()}' already exists here")
                )

            group = PlateGroup.create(
                workspace_id=input.workspace_id,
                owner_org_id=owner_org_id,
                name=input.name,
                created_by=input.created_by,
                parent_group_id=input.parent_group_id,
                group_type=input.group_type,
                description=input.description,
            )
            await self._repo.save(group)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(group)


class UpdatePlateGroup:
    """Rename / retype / redescribe a group."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateGroupRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: UpdatePlateGroupCommand, auth: AuthContext | None = None
    ) -> Result[PlateGroup, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            group = await self._repo.find_by_id_in_workspace(input.workspace_id, input.group_id)
            if group is None:
                return _not_found(input.group_id)
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if not self._visibility.can_view_owner(group.owner_org_id, excluded):
                return _not_found(input.group_id)

            if input.name is not None and input.name.strip() != group.name:
                dup = await self._repo.find_by_name(
                    input.workspace_id, group.owner_org_id, group.parent_group_id,
                    input.name.strip(),
                )
                if dup is not None and dup.id != group.id:
                    return Failure(
                        ConflictError(
                            f"A group named '{input.name.strip()}' already exists here"
                        )
                    )

            kwargs: dict = {}
            if input.name is not None:
                kwargs["name"] = input.name
            if input.group_type is not UNSET:
                kwargs["group_type"] = input.group_type
            if input.description is not UNSET:
                kwargs["description"] = input.description
            group.update(**kwargs)

            await self._repo.save(group)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(group)


class MovePlateGroup:
    """Reparent a group (None = make root). Rejects cycles and org mixing."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateGroupRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: MovePlateGroupCommand, auth: AuthContext | None = None
    ) -> Result[PlateGroup, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            group = await self._repo.find_by_id_in_workspace(input.workspace_id, input.group_id)
            if group is None:
                return _not_found(input.group_id)
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if not self._visibility.can_view_owner(group.owner_org_id, excluded):
                return _not_found(input.group_id)

            if input.new_parent_group_id is not None:
                # One flat fetch of the org's groups covers parent lookup +
                # cycle walk (org trees are small; ponytail: no recursive SQL).
                org_groups = await self._repo.find_by_workspace(
                    input.workspace_id, owner_org_id=group.owner_org_id
                )
                by_id = {g.id: g for g in org_groups}
                parent = by_id.get(input.new_parent_group_id)
                if parent is None:
                    # Missing OR belongs to another org — same 404 either way.
                    return _not_found(input.new_parent_group_id)
                if is_descendant(by_id, group.id, parent.id):
                    return Failure(
                        ValidationError("Cannot move a group under its own descendant")
                    )

            dup = await self._repo.find_by_name(
                input.workspace_id, group.owner_org_id, input.new_parent_group_id, group.name
            )
            if dup is not None and dup.id != group.id:
                return Failure(
                    ConflictError(
                        f"A group named '{group.name}' already exists under the target parent"
                    )
                )

            group.move_to(input.new_parent_group_id)
            await self._repo.save(group)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(group)


class DeletePlateGroup:
    """Delete a childless group; member plates auto-ungroup via DB SET NULL."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateGroupRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: DeletePlateGroupCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            group = await self._repo.find_by_id_in_workspace(input.workspace_id, input.group_id)
            if group is None:
                return _not_found(input.group_id)
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if not self._visibility.can_view_owner(group.owner_org_id, excluded):
                return _not_found(input.group_id)

            children = await self._repo.find_children(input.workspace_id, input.group_id)
            if children:
                return Failure(
                    ConflictError(f"Cannot delete group '{group.name}': it has child groups")
                )

            deleted_event = PlateGroupDeleted(
                aggregate_id=group.id,
                aggregate_type="PlateGroup",
                workspace_id=group.workspace_id,
                name=group.name,
                owner_org_id=group.owner_org_id,
            )
            await self._repo.delete(input.workspace_id, input.group_id)
            await self._uow.commit()

        await self._dispatcher.dispatch_all([deleted_event])
        return Success(None)


class GetGroupTree:
    """Org-scoped group tree with per-group plate counts (spec §5, §10)."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateGroupRepository,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._visibility = visibility

    async def __call__(
        self, input: GetGroupTreeQuery, auth: AuthContext | None = None
    ) -> Result[GroupTree, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)

        org_id = input.org_id if input.org_id is not None else (auth.org_id if auth else None)
        if org_id is None:
            return Failure(ValidationError("org_id is required (caller has no organization)"))

        async with self._uow:
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if org_id in excluded:
                # Spec §5: org-scoped reads of a private org are member-only.
                raise AuthorizationError("This organization's plates are private")
            groups = await self._repo.find_by_workspace(input.workspace_id, owner_org_id=org_id)
            counts = await self._repo.count_plates_by_group(input.workspace_id)
            return Success(GroupTree(org_id=org_id, roots=build_tree(groups, counts)))


class AssignPlatesToGroup:
    """Set group on plates. Every plate must be visible and share the group's org."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateGroupRepository,
        plate_repo: RegisteredPlateRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._plate_repo = plate_repo
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: AssignPlatesToGroupCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        if not input.plate_ids:
            return Failure(ValidationError("plate_ids must not be empty"))

        async with self._uow:
            group = await self._repo.find_by_id_in_workspace(input.workspace_id, input.group_id)
            if group is None:
                return _not_found(input.group_id)
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if not self._visibility.can_view_owner(group.owner_org_id, excluded):
                return _not_found(input.group_id)

            plates = []
            for plate_id in input.plate_ids:
                plate = await self._plate_repo.find_by_id_in_workspace(
                    input.workspace_id, plate_id
                )
                if plate is None or not self._visibility.can_view(plate, auth, excluded):
                    return Failure(NotFoundError("RegisteredPlate", str(plate_id)))
                if plate.owner_org_id != group.owner_org_id:
                    return Failure(
                        ValidationError(
                            f"Plate '{plate.barcode.value}' belongs to a different "
                            "organization than the group"
                        )
                    )
                plates.append(plate)

            for plate in plates:
                plate.assign_to_group(group.id)
                await self._plate_repo.save(plate)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)


class RemovePlatesFromGroup:
    """Clear group on plates currently in the given group."""

    def __init__(
        self,
        uow: UnitOfWork,
        repo: PlateGroupRepository,
        plate_repo: RegisteredPlateRepository,
        dispatcher: EventDispatcherProtocol,
        visibility: PlateVisibilityService,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._plate_repo = plate_repo
        self._dispatcher = dispatcher
        self._visibility = visibility

    async def __call__(
        self, input: RemovePlatesFromGroupCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        if not input.plate_ids:
            return Failure(ValidationError("plate_ids must not be empty"))

        async with self._uow:
            group = await self._repo.find_by_id_in_workspace(input.workspace_id, input.group_id)
            if group is None:
                return _not_found(input.group_id)
            excluded = await self._visibility.excluded_org_ids(input.workspace_id, auth)
            if not self._visibility.can_view_owner(group.owner_org_id, excluded):
                return _not_found(input.group_id)

            plates = []
            for plate_id in input.plate_ids:
                plate = await self._plate_repo.find_by_id_in_workspace(
                    input.workspace_id, plate_id
                )
                if plate is None or not self._visibility.can_view(plate, auth, excluded):
                    return Failure(NotFoundError("RegisteredPlate", str(plate_id)))
                if plate.group_id != group.id:
                    return Failure(
                        ValidationError(
                            f"Plate '{plate.barcode.value}' is not in this group"
                        )
                    )
                plates.append(plate)

            for plate in plates:
                plate.assign_to_group(None)
                await self._plate_repo.save(plate)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
```

- [ ] **Step 4: `group_id` filter on ListPlates.** In `backend/src/cellar/application/inventory/registered_plates.py`: add `group_id: uuid.UUID | None = None` to `ListPlatesQuery` (after `owner_org_id`) and pass `group_id=input.group_id,` in `ListPlates.__call__`'s `self._repo.search(...)` call.

- [ ] **Step 5: DI + Dep aliases.** In `backend/src/cellar/infrastructure/di/_inventory.py`, add a `# --- Plate Groups ---` section following the `# --- Org Plate Policies ---` pattern exactly (each factory builds `AsyncUnitOfWork` + repos + `PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow))` inline, mirroring how `di/_screening.py`'s plate section builds visibility):

```python
    def _create_plate_group(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreatePlateGroup(
            uow,
            SQLAlchemyPlateGroupRepository(uow),
            c[EventDispatcher],
            PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow)),
        )
```

…and analogously `_update_plate_group`, `_move_plate_group`, `_delete_plate_group` (same 4 args), `_get_group_tree` (no dispatcher: `GetGroupTree(uow, repo, visibility)`), `_assign_plates_to_group` / `_remove_plates_from_group` (extra `SQLAlchemyRegisteredPlateRepository(uow)` as `plate_repo`, matching the constructor order `(uow, repo, plate_repo, dispatcher, visibility)`). Then `container.define(...)` each. In `backend/src/cellar/interface/dependencies/_inventory.py` add Dep aliases following the existing `GetOrgPlatePolicyDep` pattern (`CreatePlateGroupDep`, `UpdatePlateGroupDep`, `MovePlateGroupDep`, `DeletePlateGroupDep`, `GetGroupTreeDep`, `AssignPlatesToGroupDep`, `RemovePlatesFromGroupDep`), and export them wherever the existing Deps are exported (`interface/dependencies/__init__.py`).

- [ ] **Step 6: Run tests.**

Run: `cd backend && uv run pytest tests/unit/test_plate_group_tree.py tests/unit -q` — PASS (tree tests + no regressions).
Run: `cd backend && uv run python -c "from cellar.infrastructure.di.container import create_container; create_container()"` — imports/bindings resolve without error. (If container creation needs config/env, instead run `uv run python -c "import cellar.infrastructure.di._inventory"` plus the import-linter: `uv run lint-imports` — match the Makefile's `lint` target.)

- [ ] **Step 7: Commit.**

```bash
git commit -m "feat(application): PlateGroup use cases, tree read model, DI wiring" -- backend/src/cellar/application/inventory/plate_groups.py backend/src/cellar/application/inventory/plate_visibility.py backend/src/cellar/application/inventory/registered_plates.py backend/src/cellar/infrastructure/di/_inventory.py backend/src/cellar/interface/dependencies/_inventory.py backend/src/cellar/interface/dependencies/__init__.py backend/tests/unit/test_plate_group_tree.py
```

---

### Task 6: API routes + API tests

**Files:**
- Create: `backend/src/cellar/interface/routes/plate_groups.py`
- Modify: `backend/src/cellar/interface/app.py` (include router next to the plates cluster, ~line 275)
- Modify: `backend/src/cellar/interface/routes/registered_plates.py` (`group_id` query param on list)
- Modify: `backend/tests/api/conftest.py` (`_create_test_app` must import/include the new router — API tests silently 404 otherwise)
- Test: `backend/tests/api/test_plate_groups.py` (new)

**Interfaces:**
- Consumes: Task 5 commands/use cases/Deps (exact names from Task 5's Produces block).
- Produces: routes `POST /api/v1/plate-groups` (201), `PATCH /{group_id}`, `POST /{group_id}/move`, `DELETE /{group_id}` (204), `GET /tree?org_id=`, `POST /{group_id}/plates` (204), `DELETE /{group_id}/plates` (204), plus `group_id` filter on `GET /api/v1/plates`. Response models `PlateGroupResponse` and `GroupTreeResponse{org_id, roots: list[GroupTreeNodeResponse]}` with recursive `GroupTreeNodeResponse{id, name, group_type, description, parent_group_id, owner_org_id, plate_count, created_by, version, children}`. Task 7's orval regen consumes this OpenAPI.

- [ ] **Step 1: Failing API tests** — `backend/tests/api/test_plate_groups.py`. Reuse the conftest fixtures (`client` = admin @ `AUTH_ORG_ID`, `editor_client_own_org`, `editor_client_other_org`, `viewer_client`) and the S2 privacy arrangement style from `test_registered_plates.py::TestPlateVisibility` (its `_set_plates_private` helper — copy it locally):

```python
"""API tests for /api/v1/plate-groups."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.api.conftest import AUTH_ORG_ID, OTHER_ORG_ID


async def _mk_group(client: AsyncClient, name: str, **overrides) -> dict:
    body = {"name": name, **overrides}
    resp = await client.post("/api/v1/plate-groups", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _mk_plate(client: AsyncClient, barcode: str, **overrides) -> dict:
    body = {
        "barcode": barcode,
        "plate_label": barcode,
        "format": "96",
        "plate_type": "assay",
        **overrides,
    }
    resp = await client.post("/api/v1/plates", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _set_plates_private(client: AsyncClient, org_id, *, private: bool = True):
    body = {
        "require_approval": True,
        "confirmation": "admin_confirm",
        "default_due_days": None,
        "plates_private": private,
    }
    return await client.put(f"/api/v1/org-plate-policies/{org_id}", json=body)


class TestCreate:
    async def test_create_defaults_to_caller_org(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")
        assert g["owner_org_id"] == str(AUTH_ORG_ID)
        assert g["parent_group_id"] is None
        assert g["version"] == 1

    async def test_editor_cannot_create_for_foreign_org(
        self, editor_client_own_org: AsyncClient
    ) -> None:
        resp = await editor_client_own_org.post(
            "/api/v1/plate-groups",
            json={"name": "X", "owner_org_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 403

    async def test_admin_can_create_for_foreign_org(self, client: AsyncClient) -> None:
        g = await _mk_group(
            client, f"G-{uuid.uuid4().hex[:6]}", owner_org_id=str(OTHER_ORG_ID)
        )
        assert g["owner_org_id"] == str(OTHER_ORG_ID)

    async def test_viewer_forbidden(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.post("/api/v1/plate-groups", json={"name": "X"})
        assert resp.status_code == 403

    async def test_duplicate_root_name_conflict(self, client: AsyncClient) -> None:
        name = f"Dup-{uuid.uuid4().hex[:6]}"
        await _mk_group(client, name)
        resp = await client.post("/api/v1/plate-groups", json={"name": name})
        assert resp.status_code == 409

    async def test_parent_in_other_org_rejected(self, client: AsyncClient) -> None:
        parent = await _mk_group(
            client, f"P-{uuid.uuid4().hex[:6]}", owner_org_id=str(OTHER_ORG_ID)
        )
        resp = await client.post(
            "/api/v1/plate-groups",
            json={"name": "child", "parent_group_id": parent["id"]},
            # admin's own org (default) != parent's org
        )
        assert resp.status_code == 422


class TestUpdateMoveDelete:
    async def test_rename_and_clear_type(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}", group_type="vendor")
        resp = await client.patch(
            f"/api/v1/plate-groups/{g['id']}",
            json={"name": "Renamed", "group_type": None},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Renamed"
        assert resp.json()["group_type"] is None

    async def test_move_and_cycle_rejected(self, client: AsyncClient) -> None:
        root = await _mk_group(client, f"R-{uuid.uuid4().hex[:6]}")
        child = await _mk_group(
            client, f"C-{uuid.uuid4().hex[:6]}", parent_group_id=root["id"]
        )
        # Move root under its own child -> cycle
        resp = await client.post(
            f"/api/v1/plate-groups/{root['id']}/move",
            json={"parent_group_id": child["id"]},
        )
        assert resp.status_code == 422
        # Move child to root level
        resp = await client.post(
            f"/api/v1/plate-groups/{child['id']}/move", json={"parent_group_id": None}
        )
        assert resp.status_code == 200
        assert resp.json()["parent_group_id"] is None

    async def test_delete_with_children_conflict_then_ok(self, client: AsyncClient) -> None:
        root = await _mk_group(client, f"R-{uuid.uuid4().hex[:6]}")
        child = await _mk_group(
            client, f"C-{uuid.uuid4().hex[:6]}", parent_group_id=root["id"]
        )
        resp = await client.delete(f"/api/v1/plate-groups/{root['id']}")
        assert resp.status_code == 409
        assert (await client.delete(f"/api/v1/plate-groups/{child['id']}")).status_code == 204
        assert (await client.delete(f"/api/v1/plate-groups/{root['id']}")).status_code == 204

    async def test_delete_ungroups_plates(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        resp = await client.post(
            f"/api/v1/plate-groups/{g['id']}/plates", json={"plate_ids": [plate["id"]]}
        )
        assert resp.status_code == 204, resp.text
        assert (await client.delete(f"/api/v1/plate-groups/{g['id']}")).status_code == 204
        got = await client.get(f"/api/v1/plates/{plate['id']}")
        assert got.status_code == 200
        assert got.json()["group_id"] is None


class TestTree:
    async def test_tree_shape_and_counts(self, client: AsyncClient) -> None:
        tag = uuid.uuid4().hex[:6]
        root = await _mk_group(client, f"Root-{tag}")
        child = await _mk_group(client, f"Child-{tag}", parent_group_id=root["id"])
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        await client.post(
            f"/api/v1/plate-groups/{child['id']}/plates", json={"plate_ids": [plate["id"]]}
        )
        resp = await client.get("/api/v1/plate-groups/tree")
        assert resp.status_code == 200, resp.text
        tree = resp.json()
        assert tree["org_id"] == str(AUTH_ORG_ID)
        roots = {n["name"]: n for n in tree["roots"]}
        node = roots[f"Root-{tag}"]
        assert node["plate_count"] == 0
        (child_node,) = [c for c in node["children"] if c["name"] == f"Child-{tag}"]
        assert child_node["plate_count"] == 1

    async def test_tree_scoped_to_requested_org(self, client: AsyncClient) -> None:
        mine = await _mk_group(client, f"Mine-{uuid.uuid4().hex[:6]}")
        theirs = await _mk_group(
            client, f"Theirs-{uuid.uuid4().hex[:6]}", owner_org_id=str(OTHER_ORG_ID)
        )
        resp = await client.get(f"/api/v1/plate-groups/tree?org_id={OTHER_ORG_ID}")
        assert resp.status_code == 200
        names = [n["name"] for n in resp.json()["roots"]]
        assert theirs["name"] in names
        assert mine["name"] not in names

    async def test_private_org_tree_forbidden_for_non_members(
        self, client: AsyncClient, editor_client_other_org: AsyncClient
    ) -> None:
        await _mk_group(
            client, f"Priv-{uuid.uuid4().hex[:6]}", owner_org_id=str(OTHER_ORG_ID)
        )
        assert (await _set_plates_private(client, OTHER_ORG_ID)).status_code == 200
        try:
            # Non-member (admin included — S2 semantics: no admin bypass) -> 403
            resp = await client.get(f"/api/v1/plate-groups/tree?org_id={OTHER_ORG_ID}")
            assert resp.status_code == 403
            # Member still sees it
            resp = await editor_client_other_org.get(
                f"/api/v1/plate-groups/tree?org_id={OTHER_ORG_ID}"
            )
            assert resp.status_code == 200
        finally:
            await _set_plates_private(client, OTHER_ORG_ID, private=False)


class TestAssignRemove:
    async def test_assign_org_mismatch_rejected(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")  # AUTH_ORG
        plate = await _mk_plate(
            client, f"PL-{uuid.uuid4().hex[:8]}", owner_org_id=str(OTHER_ORG_ID)
        )
        resp = await client.post(
            f"/api/v1/plate-groups/{g['id']}/plates", json={"plate_ids": [plate["id"]]}
        )
        assert resp.status_code == 422

    async def test_assign_then_remove_and_list_filter(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        assert (
            await client.post(
                f"/api/v1/plate-groups/{g['id']}/plates", json={"plate_ids": [plate["id"]]}
            )
        ).status_code == 204
        listed = await client.get(f"/api/v1/plates?group_id={g['id']}")
        assert [p["id"] for p in listed.json()] == [plate["id"]]
        got = await client.get(f"/api/v1/plates/{plate['id']}")
        assert got.json()["group_id"] == g["id"]
        assert (
            await client.request(
                "DELETE",
                f"/api/v1/plate-groups/{g['id']}/plates",
                json={"plate_ids": [plate["id"]]},
            )
        ).status_code == 204
        assert (await client.get(f"/api/v1/plates?group_id={g['id']}")).json() == []

    async def test_remove_plate_not_in_group_rejected(self, client: AsyncClient) -> None:
        g = await _mk_group(client, f"G-{uuid.uuid4().hex[:6]}")
        plate = await _mk_plate(client, f"PL-{uuid.uuid4().hex[:8]}")
        resp = await client.request(
            "DELETE",
            f"/api/v1/plate-groups/{g['id']}/plates",
            json={"plate_ids": [plate["id"]]},
        )
        assert resp.status_code == 422

    async def test_hidden_group_404s_for_other_org(
        self, client: AsyncClient, editor_client_own_org: AsyncClient
    ) -> None:
        g = await _mk_group(
            client, f"Priv-{uuid.uuid4().hex[:6]}", owner_org_id=str(OTHER_ORG_ID)
        )
        assert (await _set_plates_private(client, OTHER_ORG_ID)).status_code == 200
        try:
            # AUTH_ORG editor: private foreign group is indistinguishable from missing.
            resp = await editor_client_own_org.patch(
                f"/api/v1/plate-groups/{g['id']}", json={"name": "nope"}
            )
            assert resp.status_code == 404
            resp = await editor_client_own_org.request(
                "DELETE", f"/api/v1/plate-groups/{g['id']}"
            )
            assert resp.status_code == 404
        finally:
            await _set_plates_private(client, OTHER_ORG_ID, private=False)
```

Notes for the implementer: `viewer_client` fixture name — confirm in conftest (if it differs, use the real one). `format: "96"` / `plate_type: "assay"` — confirm against `PlateFormat`/`PlateType` values used in `test_registered_plates.py` and copy those. httpx `AsyncClient.delete` takes no body — the tests above already use `client.request("DELETE", ..., json=...)` where a body is needed.

- [ ] **Step 2: Run to verify failure.**

Run: `cd backend && uv run pytest tests/api/test_plate_groups.py -q` (requires `make up`)
Expected: FAIL — 404s (router not registered yet).

- [ ] **Step 3: Implement the router.** Create `backend/src/cellar/interface/routes/plate_groups.py`:

```python
"""PlateGroup API routes — hierarchy CRUD, tree read model, plate assignment."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.inventory.plate_groups import (
    AssignPlatesToGroupCommand,
    CreatePlateGroupCommand,
    DeletePlateGroupCommand,
    GetGroupTreeQuery,
    GroupTree,
    GroupTreeNode,
    MovePlateGroupCommand,
    RemovePlatesFromGroupCommand,
    UpdatePlateGroupCommand,
)
from cellar.application.shared.sentinel import UNSET
from cellar.domain.inventory.plate_group import PlateGroup
from cellar.interface.dependencies import (
    AssignPlatesToGroupDep,
    AuthDep,
    CreatePlateGroupDep,
    DeletePlateGroupDep,
    GetGroupTreeDep,
    MovePlateGroupDep,
    RemovePlatesFromGroupDep,
    UpdatePlateGroupDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/plate-groups", tags=["plate-groups"])


class PlateGroupResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    owner_org_id: uuid.UUID
    name: str
    parent_group_id: uuid.UUID | None = None
    group_type: str | None = None
    description: str | None = None
    created_by: uuid.UUID
    version: int

    @classmethod
    def from_domain(cls, g: PlateGroup) -> PlateGroupResponse:
        return cls(
            id=g.id,
            workspace_id=g.workspace_id,
            owner_org_id=g.owner_org_id,
            name=g.name,
            parent_group_id=g.parent_group_id,
            group_type=g.group_type,
            description=g.description,
            created_by=g.created_by,
            version=g.version,
        )


class GroupTreeNodeResponse(BaseModel):
    id: uuid.UUID
    name: str
    group_type: str | None = None
    description: str | None = None
    parent_group_id: uuid.UUID | None = None
    owner_org_id: uuid.UUID
    plate_count: int
    created_by: uuid.UUID
    version: int
    children: list[GroupTreeNodeResponse] = []

    @classmethod
    def from_node(cls, n: GroupTreeNode) -> GroupTreeNodeResponse:
        return cls(
            id=n.group.id,
            name=n.group.name,
            group_type=n.group.group_type,
            description=n.group.description,
            parent_group_id=n.group.parent_group_id,
            owner_org_id=n.group.owner_org_id,
            plate_count=n.plate_count,
            created_by=n.group.created_by,
            version=n.group.version,
            children=[cls.from_node(c) for c in n.children],
        )


class GroupTreeResponse(BaseModel):
    org_id: uuid.UUID
    roots: list[GroupTreeNodeResponse]

    @classmethod
    def from_tree(cls, t: GroupTree) -> GroupTreeResponse:
        return cls(org_id=t.org_id, roots=[GroupTreeNodeResponse.from_node(r) for r in t.roots])


class CreatePlateGroupBody(BaseModel):
    name: str
    owner_org_id: uuid.UUID | None = None
    parent_group_id: uuid.UUID | None = None
    group_type: str | None = None
    description: str | None = None

    model_config = {"extra": "forbid"}


class UpdatePlateGroupBody(BaseModel):
    name: str | None = None
    group_type: str | None = None
    description: str | None = None

    model_config = {"extra": "forbid"}


class MovePlateGroupBody(BaseModel):
    parent_group_id: uuid.UUID | None

    model_config = {"extra": "forbid"}


class PlateIdsBody(BaseModel):
    plate_ids: list[uuid.UUID]

    model_config = {"extra": "forbid"}


@router.post("", response_model=PlateGroupResponse, status_code=201)
async def create_plate_group(
    body: CreatePlateGroupBody, auth: AuthDep, uc: CreatePlateGroupDep
) -> PlateGroupResponse:
    """Create a plate group (root or nested)."""
    command = CreatePlateGroupCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        created_by=auth.user_id,
        owner_org_id=body.owner_org_id,
        parent_group_id=body.parent_group_id,
        group_type=body.group_type,
        description=body.description,
    )
    group = result_to_response(await uc(command, auth=auth))
    return PlateGroupResponse.from_domain(group)


@router.get("/tree", response_model=GroupTreeResponse)
async def get_group_tree(
    auth: AuthDep, uc: GetGroupTreeDep, org_id: uuid.UUID | None = None
) -> GroupTreeResponse:
    """Org-scoped group tree with plate counts (defaults to the caller's org)."""
    query = GetGroupTreeQuery(workspace_id=auth.workspace_id, org_id=org_id)
    tree = result_to_response(await uc(query, auth=auth))
    return GroupTreeResponse.from_tree(tree)


@router.patch("/{group_id}", response_model=PlateGroupResponse)
async def update_plate_group(
    group_id: uuid.UUID, body: UpdatePlateGroupBody, auth: AuthDep, uc: UpdatePlateGroupDep
) -> PlateGroupResponse:
    """Rename / retype / redescribe a group."""
    provided = body.model_fields_set
    command = UpdatePlateGroupCommand(
        workspace_id=auth.workspace_id,
        group_id=group_id,
        name=body.name if "name" in provided else None,
        group_type=body.group_type if "group_type" in provided else UNSET,
        description=body.description if "description" in provided else UNSET,
    )
    group = result_to_response(await uc(command, auth=auth))
    return PlateGroupResponse.from_domain(group)


@router.post("/{group_id}/move", response_model=PlateGroupResponse)
async def move_plate_group(
    group_id: uuid.UUID, body: MovePlateGroupBody, auth: AuthDep, uc: MovePlateGroupDep
) -> PlateGroupResponse:
    """Reparent a group (null parent = make it a root)."""
    command = MovePlateGroupCommand(
        workspace_id=auth.workspace_id,
        group_id=group_id,
        new_parent_group_id=body.parent_group_id,
    )
    group = result_to_response(await uc(command, auth=auth))
    return PlateGroupResponse.from_domain(group)


@router.delete("/{group_id}", status_code=204)
async def delete_plate_group(
    group_id: uuid.UUID, auth: AuthDep, uc: DeletePlateGroupDep
) -> None:
    """Delete a childless group; its plates are ungrouped, not deleted."""
    command = DeletePlateGroupCommand(workspace_id=auth.workspace_id, group_id=group_id)
    result_to_response(await uc(command, auth=auth))


@router.post("/{group_id}/plates", status_code=204)
async def assign_plates_to_group(
    group_id: uuid.UUID, body: PlateIdsBody, auth: AuthDep, uc: AssignPlatesToGroupDep
) -> None:
    """Assign plates to a group (moves them if already grouped elsewhere)."""
    command = AssignPlatesToGroupCommand(
        workspace_id=auth.workspace_id, group_id=group_id, plate_ids=body.plate_ids
    )
    result_to_response(await uc(command, auth=auth))


@router.delete("/{group_id}/plates", status_code=204)
async def remove_plates_from_group(
    group_id: uuid.UUID, body: PlateIdsBody, auth: AuthDep, uc: RemovePlatesFromGroupDep
) -> None:
    """Remove plates from a group (clears their group assignment)."""
    command = RemovePlatesFromGroupCommand(
        workspace_id=auth.workspace_id, group_id=group_id, plate_ids=body.plate_ids
    )
    result_to_response(await uc(command, auth=auth))
```

(`GroupTreeNodeResponse` is self-referential — add `GroupTreeNodeResponse.model_rebuild()` after the class if Pydantic requires it. **Route order matters:** `/tree` is declared before `/{group_id}` so it isn't captured as a UUID path param.)

Then:
1. `backend/src/cellar/interface/app.py`: import `plate_groups` router and `app.include_router(plate_group_router)` in the plates cluster.
2. `backend/tests/api/conftest.py` `_create_test_app()`: add the same import + include.
3. `backend/src/cellar/interface/routes/registered_plates.py` `list_plates`: add `group_id: uuid.UUID | None = None,` param and pass `group_id=group_id` into `ListPlatesQuery`. **Also add `group_id` to `PlateResponse`** (`group_id: uuid.UUID | None = None` + `group_id=p.group_id` in `from_domain`) — the delete-ungroups and assign tests read it.

- [ ] **Step 4: Run tests.**

Run: `cd backend && uv run pytest tests/api/test_plate_groups.py -q` — PASS.
Run: `cd backend && uv run pytest tests/api/test_registered_plates.py tests/api/test_org_plate_policies.py -q` — no regressions.

- [ ] **Step 5: Commit.**

```bash
git commit -m "feat(api): /api/v1/plate-groups routes + tree + plate assignment" -- backend/src/cellar/interface/routes/plate_groups.py backend/src/cellar/interface/routes/registered_plates.py backend/src/cellar/interface/app.py backend/tests/api/conftest.py backend/tests/api/test_plate_groups.py
```

---

### Task 7: Orval regen + FE plate-group hooks

**Files:**
- Regenerate: `frontend/src/shared/lib/api/model/**`, `frontend/src/shared/lib/api/endpoints.ts`
- Modify: `frontend/src/features/inventory/hooks/query-keys.ts` (`PLATE_GROUPS_KEY`)
- Create: `frontend/src/features/inventory/hooks/use-plate-groups.ts`
- Test: `frontend/src/features/inventory/hooks/use-plate-groups.test.tsx`

**Interfaces:**
- Consumes: Task 6's OpenAPI (generated `GroupTreeResponse`, `GroupTreeNodeResponse`, `PlateGroupResponse`, `CreatePlateGroupBody`, `UpdatePlateGroupBody`, `MovePlateGroupBody`, `PlateIdsBody` — exact generated names may differ slightly, e.g. `BodyCreatePlateGroup…`; use what orval emits).
- Produces (Tasks 8–9 import these): `PLATE_GROUPS_KEY`; type aliases `PlateGroup = PlateGroupResponse`, `PlateGroupTree = GroupTreeResponse`, `PlateGroupNode = GroupTreeNodeResponse`; hooks `usePlateGroupTree(orgId?: string, opts?: {enabled?: boolean})`, `useCreatePlateGroup()`, `useUpdatePlateGroup()`, `useMovePlateGroup()`, `useDeletePlateGroup()`, `useAssignPlatesToGroup()`, `useRemovePlatesFromGroup()`.

- [ ] **Step 1: Regen orval** (same recipe as Task 2 Step 1 — backend up on :8000, `pnpm generate:api`, `make stop`). Verify `groupTreeResponse.ts` / `plateGroupResponse.ts` etc. exist in `model/`.

- [ ] **Step 2: Failing hook tests** — `frontend/src/features/inventory/hooks/use-plate-groups.test.tsx` (mirror `use-orgs.test.tsx`: mock `customInstance`, fresh QueryClient with `retry: false`):

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { customInstance } from "@/shared/lib/api/custom-instance";
import {
  useCreatePlateGroup,
  usePlateGroupTree,
} from "./use-plate-groups";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

const mocked = vi.mocked(customInstance);

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("usePlateGroupTree", () => {
  it("fetches the tree for an org", async () => {
    mocked.mockResolvedValueOnce({ org_id: "o1", roots: [] });
    const { result } = renderHook(() => usePlateGroupTree("o1"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/api/v1/plate-groups/tree",
        method: "GET",
        params: { org_id: "o1" },
      }),
    );
    expect(result.current.data?.org_id).toBe("o1");
  });

  it("omits org_id param when not given (server defaults to my org)", async () => {
    mocked.mockResolvedValueOnce({ org_id: "mine", roots: [] });
    const { result } = renderHook(() => usePlateGroupTree(undefined), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({ params: {} }),
    );
  });

  it("respects enabled=false", () => {
    renderHook(() => usePlateGroupTree("o1", { enabled: false }), { wrapper });
    expect(mocked).not.toHaveBeenCalled();
  });
});

describe("useCreatePlateGroup", () => {
  it("POSTs and resolves", async () => {
    mocked.mockResolvedValueOnce({ id: "g1", name: "G" });
    const { result } = renderHook(() => useCreatePlateGroup(), { wrapper });
    result.current.mutate({ name: "G" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mocked).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/api/v1/plate-groups",
        method: "POST",
        data: { name: "G" },
      }),
    );
  });
});
```

Run: `cd frontend && pnpm exec vitest run src/features/inventory/hooks/use-plate-groups.test.tsx` — FAIL (module missing).

- [ ] **Step 3: Implement.** In `frontend/src/features/inventory/hooks/query-keys.ts` add:

```ts
export const PLATE_GROUPS_KEY = ["plate-groups"] as const;
```

Create `frontend/src/features/inventory/hooks/use-plate-groups.ts`:

```ts
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  CreatePlateGroupBody,
  GroupTreeNodeResponse,
  GroupTreeResponse,
  PlateGroupResponse,
  UpdatePlateGroupBody,
} from "@/shared/lib/api/model";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { PLATE_GROUPS_KEY, PLATES_KEY } from "./query-keys";

export type PlateGroup = PlateGroupResponse;
export type PlateGroupTree = GroupTreeResponse;
export type PlateGroupNode = GroupTreeNodeResponse;

export function usePlateGroupTree(orgId?: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: [...PLATE_GROUPS_KEY, "tree", orgId ?? "mine"],
    queryFn: ({ signal }) =>
      customInstance<PlateGroupTree>({
        url: `${API_V1}/plate-groups/tree`,
        method: "GET",
        params: orgId ? { org_id: orgId } : {},
        signal,
      }),
    enabled: opts?.enabled ?? true,
  });
}

function useGroupMutation<TVars>(
  request: (vars: TVars) => Parameters<typeof customInstance>[0],
  successMessage: string,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: TVars) => customInstance<unknown>(request(vars)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PLATE_GROUPS_KEY });
      qc.invalidateQueries({ queryKey: PLATES_KEY });
      showSuccess(successMessage);
    },
    // Errors toast via the global MutationCache handler.
  });
}

export function useCreatePlateGroup() {
  return useGroupMutation(
    (body: CreatePlateGroupBody) => ({
      url: `${API_V1}/plate-groups`,
      method: "POST" as const,
      data: body,
    }),
    "Group created",
  );
}

export function useUpdatePlateGroup() {
  return useGroupMutation(
    ({ groupId, ...body }: UpdatePlateGroupBody & { groupId: string }) => ({
      url: `${API_V1}/plate-groups/${groupId}`,
      method: "PATCH" as const,
      data: body,
    }),
    "Group updated",
  );
}

export function useMovePlateGroup() {
  return useGroupMutation(
    ({ groupId, parentGroupId }: { groupId: string; parentGroupId: string | null }) => ({
      url: `${API_V1}/plate-groups/${groupId}/move`,
      method: "POST" as const,
      data: { parent_group_id: parentGroupId },
    }),
    "Group moved",
  );
}

export function useDeletePlateGroup() {
  return useGroupMutation(
    ({ groupId }: { groupId: string }) => ({
      url: `${API_V1}/plate-groups/${groupId}`,
      method: "DELETE" as const,
    }),
    "Group deleted",
  );
}

export function useAssignPlatesToGroup() {
  return useGroupMutation(
    ({ groupId, plateIds }: { groupId: string; plateIds: string[] }) => ({
      url: `${API_V1}/plate-groups/${groupId}/plates`,
      method: "POST" as const,
      data: { plate_ids: plateIds },
    }),
    "Plates assigned",
  );
}

export function useRemovePlatesFromGroup() {
  return useGroupMutation(
    ({ groupId, plateIds }: { groupId: string; plateIds: string[] }) => ({
      url: `${API_V1}/plate-groups/${groupId}/plates`,
      method: "DELETE" as const,
      data: { plate_ids: plateIds },
    }),
    "Plates removed from group",
  );
}
```

(Adjust generated type-import names to whatever orval actually emitted in Step 1 — check `model/index.ts`. If `customInstance`'s options type rejects `data` on DELETE, check its signature — it accepts a generic options object; no special-casing expected.)

- [ ] **Step 4: Run tests.**

Run: `cd frontend && pnpm exec vitest run src/features/inventory/hooks/use-plate-groups.test.tsx` — PASS.
Run: `cd frontend && pnpm exec tsc --noEmit` — exit 0.

- [ ] **Step 5: Commit** (include the regen):

```bash
git add frontend/src/shared/lib/api
git commit -m "feat(frontend): plate-group hooks + orval regen" -- frontend/src/shared/lib/api frontend/src/features/inventory/hooks/query-keys.ts frontend/src/features/inventory/hooks/use-plate-groups.ts frontend/src/features/inventory/hooks/use-plate-groups.test.tsx
```

---

### Task 8: Plate Groups page — nav, org selector, react-d3-tree, details panel

**Files:**
- Modify: `frontend/package.json` + `frontend/pnpm-lock.yaml` (add `react-d3-tree`; **commit note below**)
- Create: `frontend/src/app/(dashboard)/inventory/plate-groups/page.tsx`
- Create: `frontend/src/features/inventory/components/plate-group-dashboard.tsx`
- Create: `frontend/src/features/inventory/components/plate-group-tree.tsx`
- Create: `frontend/src/features/inventory/components/plate-group-details.tsx`
- Modify: `frontend/src/shared/lib/navigation.ts` (nav item)
- Test: `frontend/src/features/inventory/components/plate-group-details.test.tsx`

**Interfaces:**
- Consumes: Task 7 hooks/types; `useOrgs`, `useCurrentUser`, `usePlates`; `PageHeader`; shadcn primitives.
- Produces: `PlateGroupDashboard` (page root); `PlateGroupTreeView({tree, selectedId, onSelect})`; `PlateGroupDetails({node, onAddChild?, onAddPlates?, onEdit?, onMove?, onDelete?, onRemovePlates?})` — Task 9 wires these callbacks to real dialogs (Task 8 renders the buttons; handlers arrive via props from the dashboard, which leaves them `undefined` until Task 9).

**UX decisions (locked):** Left = tree canvas (react-d3-tree, horizontal layout, definite height `calc(100vh - 12rem)`), right = fixed-width details panel (`w-96`, scrollable). Node label = name + plate-count badge; `group_type` shown as a small muted chip under the name (color-coding by type deferred to S5's dataviz pass — counts and type text carry the information; a hue system without a legend is noise on a first cut). Click node → details panel: metadata (type, description, created-by-name is NOT available — omit; owner org name via `useOrgs`), plates-in-group list (barcode + label, via `usePlates({group_id})`), action buttons: "Add child", "Add plates", "Edit", "Move", "Delete". Empty state: "No groups yet for <org>" + "Create group" button. Org selector = same Select pattern as plate-list (My org default, named options from `useOrgs`, `meFailed` fallback to first org — NO "All orgs" option: the tree endpoint is org-scoped by spec).

- [ ] **Step 1: Install react-d3-tree.**

```bash
cd frontend && pnpm add react-d3-tree
```

React 19 peer warnings are acceptable (pnpm warns, doesn't fail). **Commit caution:** the working tree already carries the user's unrelated Sentinel 0.17→0.19 bump in `package.json`/`pnpm-lock.yaml`. Committing these two files will include that bump — that is NOT allowed. Instead: `git add -p frontend/package.json` and stage ONLY the react-d3-tree hunk; for the lockfile, run `git diff frontend/pnpm-lock.yaml` — if the react-d3-tree hunks are cleanly separable, stage them with `git add -p`; if they interleave with the sentinel hunks, STOP and report BLOCKED with the diff — the controller will decide (do not guess).

- [ ] **Step 2: Nav + page scaffold.** In `frontend/src/shared/lib/navigation.ts`, add to the Inventory group after "Plates" (import `FolderTree` from lucide-react):

```ts
  { title: "Plate Groups", href: "/inventory/plate-groups", icon: FolderTree },
```

Create `frontend/src/app/(dashboard)/inventory/plate-groups/page.tsx`:

```tsx
import { PlateGroupDashboard } from "@/features/inventory/components/plate-group-dashboard";

export default function PlateGroupsPage() {
  return <PlateGroupDashboard />;
}
```

- [ ] **Step 3: Tree component.** Create `frontend/src/features/inventory/components/plate-group-tree.tsx`:

```tsx
"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import type { RawNodeDatum, TreeNodeDatum } from "react-d3-tree";
import type { PlateGroupNode, PlateGroupTree } from "../hooks/use-plate-groups";

// react-d3-tree touches window at module scope — client-only.
const Tree = dynamic(() => import("react-d3-tree"), { ssr: false });

export interface PlateGroupTreeViewProps {
  tree: PlateGroupTree;
  selectedId: string | null;
  onSelect: (node: PlateGroupNode) => void;
}

interface GroupDatum extends RawNodeDatum {
  attributes: { id: string; plate_count: number; group_type: string };
  children?: GroupDatum[];
}

function toDatum(node: PlateGroupNode): GroupDatum {
  return {
    name: node.name,
    attributes: {
      id: node.id,
      plate_count: node.plate_count,
      group_type: node.group_type ?? "",
    },
    children: (node.children ?? []).map(toDatum),
  };
}

/** Index every node by id so a d3 click (which hands back the datum, not our
 *  domain node) can be resolved to the original PlateGroupNode. */
function indexNodes(roots: PlateGroupNode[]): Map<string, PlateGroupNode> {
  const map = new Map<string, PlateGroupNode>();
  const walk = (n: PlateGroupNode) => {
    map.set(n.id, n);
    (n.children ?? []).forEach(walk);
  };
  roots.forEach(walk);
  return map;
}

export function PlateGroupTreeView({ tree, selectedId, onSelect }: PlateGroupTreeViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [translate, setTranslate] = useState({ x: 80, y: 200 });
  const nodesById = indexNodes(tree.roots);

  useEffect(() => {
    // Center vertically once the container has a real size.
    const el = containerRef.current;
    if (el && el.clientHeight > 0) {
      setTranslate({ x: 80, y: el.clientHeight / 2 });
    }
  }, []);

  // react-d3-tree wants exactly one root; wrap multiple roots in a synthetic
  // org node (hidden styling, still clickable-noop).
  const data: GroupDatum =
    tree.roots.length === 1
      ? toDatum(tree.roots[0])
      : {
          name: "All groups",
          attributes: { id: "__root__", plate_count: 0, group_type: "" },
          children: tree.roots.map(toDatum),
        };

  const renderNode = ({ nodeDatum, toggleNode }: {
    nodeDatum: TreeNodeDatum;
    toggleNode: () => void;
  }) => {
    const attrs = nodeDatum.attributes as unknown as GroupDatum["attributes"];
    const isSynthetic = attrs.id === "__root__";
    const isSelected = attrs.id === selectedId;
    return (
      <g>
        <circle
          r={10}
          fill={isSelected ? "var(--primary)" : "var(--muted)"}
          stroke="var(--border)"
          onClick={(e) => {
            e.stopPropagation();
            toggleNode();
          }}
          data-testid={`tree-toggle-${attrs.id}`}
        />
        <g
          className="cursor-pointer"
          onClick={() => {
            if (isSynthetic) return;
            const node = nodesById.get(attrs.id);
            if (node) onSelect(node);
          }}
          data-testid={`tree-node-${attrs.id}`}
        >
          <text x={16} dy={-2} className="fill-foreground text-sm font-medium" strokeWidth={0}>
            {nodeDatum.name}
          </text>
          <text x={16} dy={14} className="fill-muted-foreground text-xs" strokeWidth={0}>
            {attrs.plate_count} plate{attrs.plate_count === 1 ? "" : "s"}
            {attrs.group_type ? ` · ${attrs.group_type}` : ""}
          </text>
        </g>
      </g>
    );
  };

  return (
    <div
      ref={containerRef}
      className="h-[calc(100vh-12rem)] min-h-[420px] w-full rounded-md border bg-card"
      data-testid="plate-group-tree"
    >
      <Tree
        data={data}
        orientation="horizontal"
        translate={translate}
        collapsible
        zoomable
        separation={{ siblings: 0.6, nonSiblings: 0.8 }}
        nodeSize={{ x: 260, y: 56 }}
        renderCustomNodeElement={renderNode}
        pathFunc="step"
      />
    </div>
  );
}
```

(Verify prop/type names against the installed react-d3-tree version's exports — `RawNodeDatum`/`TreeNodeDatum`/`renderCustomNodeElement` are the v3 API. If `var(--primary)` CSS vars don't resolve inside SVG in this Tailwind setup, use `currentColor` + Tailwind text classes on the `<g>` wrapper — check how the app's CSS variables are defined in `globals.css` and match.)

- [ ] **Step 4: Details panel.** Create `frontend/src/features/inventory/components/plate-group-details.tsx`:

```tsx
"use client";

import { useMemo } from "react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { useOrgs } from "@/shared/hooks/use-orgs";
import { usePlates } from "../hooks/use-plates";
import type { PlateGroupNode } from "../hooks/use-plate-groups";

export interface PlateGroupDetailsProps {
  node: PlateGroupNode;
  onAddChild?: () => void;
  onAddPlates?: () => void;
  onEdit?: () => void;
  onMove?: () => void;
  onDelete?: () => void;
  onRemovePlates?: (plateIds: string[]) => void;
}

export function PlateGroupDetails({
  node,
  onAddChild,
  onAddPlates,
  onEdit,
  onMove,
  onDelete,
  onRemovePlates,
}: PlateGroupDetailsProps) {
  const { data: orgs } = useOrgs();
  const orgName = useMemo(
    () => orgs?.find((o) => o.id === node.owner_org_id)?.name ?? "—",
    [orgs, node.owner_org_id],
  );
  const { data: plates, isLoading: platesLoading } = usePlates({ group_id: node.id });

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4" data-testid="group-details">
      <div>
        <h2 className="text-lg font-semibold">{node.name}</h2>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          {node.group_type ? <Badge variant="secondary">{node.group_type}</Badge> : null}
          <span>{orgName}</span>
        </div>
        {node.description ? (
          <p className="mt-2 text-sm text-muted-foreground">{node.description}</p>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={onAddChild}>Add child</Button>
        <Button size="sm" variant="outline" onClick={onAddPlates}>Add plates</Button>
        <Button size="sm" variant="outline" onClick={onEdit}>Edit</Button>
        <Button size="sm" variant="outline" onClick={onMove}>Move</Button>
        <Button size="sm" variant="destructive" onClick={onDelete}>Delete</Button>
      </div>

      <div>
        <div className="mb-2 flex items-center gap-2">
          <h3 className="text-sm font-medium">Plates</h3>
          <Badge variant="outline">{node.plate_count}</Badge>
        </div>
        {platesLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : !plates?.length ? (
          <p className="text-sm text-muted-foreground">No plates in this group.</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {plates.map((p) => (
              <li key={p.id} className="flex items-center justify-between px-3 py-2 text-sm">
                <span>
                  <span className="font-mono">{p.barcode}</span>
                  <span className="ml-2 text-muted-foreground">{p.plate_label}</span>
                </span>
                {onRemovePlates ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onRemovePlates([p.id])}
                    aria-label={`Remove ${p.barcode} from group`}
                  >
                    Remove
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
```

(Check `usePlates`' actual filter signature in `use-plates.ts` — it takes a filters object; add `group_id` to its filter type if the type is narrowed. Buttons render even when handlers are undefined — Task 9 wires them; a click is a no-op meanwhile.)

- [ ] **Step 5: Dashboard shell.** Create `frontend/src/features/inventory/components/plate-group-dashboard.tsx`:

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/shared/components/page-header";
import { Button } from "@/shared/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useCurrentUser } from "@/shared/hooks/use-current-user";
import { useOrgs } from "@/shared/hooks/use-orgs";
import { showError } from "@/shared/lib/toast";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { usePlateGroupTree } from "../hooks/use-plate-groups";
import { PlateGroupDetails } from "./plate-group-details";
import { PlateGroupTreeView } from "./plate-group-tree";

export function PlateGroupDashboard() {
  const { data: me, isError: meFailed } = useCurrentUser();
  const { data: orgs } = useOrgs();
  const [orgId, setOrgId] = useState<string | null>(null);
  const [selected, setSelected] = useState<PlateGroupNode | null>(null);

  // Default the selector to my org once /me resolves; if /me failed, fall
  // back to the first org in the directory so the page still works.
  useEffect(() => {
    if (orgId !== null) return;
    if (me?.org_id) setOrgId(me.org_id);
    else if (meFailed && orgs?.length) {
      setOrgId(orgs[0].id);
      showError("Could not resolve your organization — showing the first org");
    }
  }, [orgId, me, meFailed, orgs]);

  const { data: tree, isLoading, error } = usePlateGroupTree(orgId ?? undefined, {
    enabled: orgId !== null,
  });

  // Keep the details panel in sync with a refetched tree.
  const selectedNode = useMemo(() => {
    if (!tree || !selected) return null;
    const find = (nodes: PlateGroupNode[]): PlateGroupNode | null => {
      for (const n of nodes) {
        if (n.id === selected.id) return n;
        const hit = find(n.children ?? []);
        if (hit) return hit;
      }
      return null;
    };
    return find(tree.roots);
  }, [tree, selected]);

  return (
    <div className="flex flex-col gap-4 p-6">
      <PageHeader
        title="Plate Groups"
        subtitle="Org-owned hierarchy for organizing plates"
      >
        <Select value={orgId ?? ""} onValueChange={(v) => { setOrgId(v); setSelected(null); }}>
          <SelectTrigger className="w-56" aria-label="Organization">
            <SelectValue placeholder="Organization" />
          </SelectTrigger>
          <SelectContent>
            {(orgs ?? []).map((o) => (
              <SelectItem key={o.id} value={o.id}>
                {o.name}
                {me?.org_id === o.id ? " (my org)" : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button data-testid="create-root-group">New group</Button>
      </PageHeader>

      {error ? (
        <p className="text-sm text-destructive">
          {error instanceof Error ? error.message : "Failed to load groups"}
        </p>
      ) : isLoading || orgId === null ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : !tree || tree.roots.length === 0 ? (
        <div className="flex h-64 flex-col items-center justify-center gap-3 rounded-md border border-dashed">
          <p className="text-sm text-muted-foreground">No groups yet for this organization.</p>
          <Button data-testid="create-root-group-empty">Create group</Button>
        </div>
      ) : (
        <div className="flex gap-4">
          <div className="min-w-0 flex-1">
            <PlateGroupTreeView
              tree={tree}
              selectedId={selectedNode?.id ?? null}
              onSelect={setSelected}
            />
          </div>
          {selectedNode ? (
            <aside className="w-96 shrink-0 rounded-md border bg-card">
              <PlateGroupDetails node={selectedNode} />
            </aside>
          ) : null}
        </div>
      )}
    </div>
  );
}
```

(A private foreign org yields a 403 → the `error` branch shows the API's "private" message — acceptable copy for S3. The two "New group"/"Create group" buttons are inert until Task 9 wires dialogs.)

- [ ] **Step 6: Details-panel test** — `frontend/src/features/inventory/components/plate-group-details.test.tsx` (component test with mocked `customInstance` for orgs + plates; jsdom can't render the d3 tree — the tree component is deliberately untested here, covered by Task 10's runtime pass):

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { PlateGroupDetails } from "./plate-group-details";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

const mocked = vi.mocked(customInstance);

const node: PlateGroupNode = {
  id: "g1",
  name: "Vendor Library A",
  group_type: "vendor",
  description: "Legacy vendor set",
  parent_group_id: null,
  owner_org_id: "org1",
  plate_count: 1,
  created_by: "u1",
  version: 1,
  children: [],
};

function setup(props: Partial<Parameters<typeof PlateGroupDetails>[0]> = {}) {
  mocked.mockImplementation((opts: { url: string }) => {
    if (opts.url.includes("/orgs")) {
      return Promise.resolve([{ id: "org1", slug: "acme", name: "Acme Labs" }]);
    }
    return Promise.resolve([
      { id: "p1", barcode: "000123", plate_label: "Plate 123", group_id: "g1" },
    ]);
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<PlateGroupDetails node={node} {...props} />, { wrapper });
}

describe("PlateGroupDetails", () => {
  it("shows metadata, org name, and plates", async () => {
    setup();
    expect(screen.getByText("Vendor Library A")).toBeInTheDocument();
    expect(screen.getByText("vendor")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Acme Labs")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("000123")).toBeInTheDocument());
  });

  it("fires onRemovePlates with the plate id", async () => {
    const onRemovePlates = vi.fn();
    setup({ onRemovePlates });
    const btn = await screen.findByRole("button", { name: /remove 000123/i });
    fireEvent.click(btn);
    expect(onRemovePlates).toHaveBeenCalledWith(["p1"]);
  });

  it("fires action callbacks", () => {
    const onEdit = vi.fn();
    setup({ onEdit });
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(onEdit).toHaveBeenCalled();
  });
});
```

- [ ] **Step 7: Verify.**

Run: `cd frontend && pnpm exec vitest run src/features/inventory/components/plate-group-details.test.tsx` — PASS.
Run: `cd frontend && pnpm exec tsc --noEmit` — exit 0.
Run: `cd frontend && pnpm exec biome check src/features/inventory src/app/\(dashboard\)/inventory/plate-groups src/shared/lib/navigation.ts` — exit 0.

- [ ] **Step 8: Commit** (per Step 1's caution, package.json/lockfile only if the react-d3-tree hunks staged cleanly):

```bash
git commit -m "feat(frontend): plate-groups dashboard — nav, org selector, d3 tree, details panel" -- frontend/src/app frontend/src/features/inventory/components/plate-group-dashboard.tsx frontend/src/features/inventory/components/plate-group-tree.tsx frontend/src/features/inventory/components/plate-group-details.tsx frontend/src/features/inventory/components/plate-group-details.test.tsx frontend/src/shared/lib/navigation.ts
# plus the separately staged package.json/pnpm-lock.yaml react-d3-tree hunks:
git commit -m "chore(frontend): add react-d3-tree"
```

---

### Task 9: Group management dialogs + wiring

**Files:**
- Create: `frontend/src/features/inventory/components/plate-group-dialog.tsx` (create + edit, one component)
- Create: `frontend/src/features/inventory/components/move-plate-group-dialog.tsx`
- Create: `frontend/src/features/inventory/components/assign-plates-dialog.tsx`
- Modify: `frontend/src/features/inventory/components/plate-group-dashboard.tsx` (wire dialogs + delete confirm + remove-plates)
- Test: `frontend/src/features/inventory/components/plate-group-dialog.test.tsx`

**Interfaces:**
- Consumes: Task 7 mutation hooks; Task 8 components; shadcn `Dialog`, `AlertDialog`, `Select`, `Input`, `Textarea`, `Command` (if present) or plain filtered list.
- Produces: `PlateGroupDialog({open, onOpenChange, orgId, parentGroupId, group})` (create when `group` is null, edit otherwise); `MovePlateGroupDialog({open, onOpenChange, group, tree})`; `AssignPlatesDialog({open, onOpenChange, group})`.

**Conventions:** plain per-field `useState` dialogs (the inventory feature's own house style — `org-plate-policy-dialog.tsx`), explicit Save/Cancel gestures, mutation `isPending` disables buttons, `useEffect` reset-on-open. Group-type suggestions come from the `plate_group_type` ControlledVocabulary when it exists, else the spec's seed list.

- [ ] **Step 1: Failing dialog test** — `frontend/src/features/inventory/components/plate-group-dialog.test.tsx` (copy the Radix Select polyfill block from `org-plate-policy-dialog.test.tsx` verbatim into `beforeAll`):

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { PlateGroupDialog } from "./plate-group-dialog";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: vi.fn(),
}));
vi.mock("@/shared/lib/toast", () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

const mocked = vi.mocked(customInstance);

beforeAll(() => {
  // Radix Select portal polyfills — copy the exact block from
  // org-plate-policy-dialog.test.tsx (scrollIntoView/hasPointerCapture/
  // releasePointerCapture no-ops).
  window.HTMLElement.prototype.scrollIntoView = () => {};
  window.HTMLElement.prototype.hasPointerCapture = () => false;
  window.HTMLElement.prototype.releasePointerCapture = () => {};
});

function setup(props: Partial<Parameters<typeof PlateGroupDialog>[0]> = {}) {
  mocked.mockImplementation((opts: { url: string; method: string }) => {
    if (opts.url.includes("/vocabularies")) return Promise.resolve([]);
    return Promise.resolve({ id: "g-new", name: "New Group" });
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(
    <PlateGroupDialog
      open
      onOpenChange={() => {}}
      orgId="org1"
      parentGroupId={null}
      group={null}
      {...props}
    />,
    { wrapper },
  );
}

describe("PlateGroupDialog", () => {
  it("disables Save until a name is entered, then POSTs the create body", async () => {
    setup();
    const save = screen.getByRole("button", { name: /create/i });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "Vendor Set 1" } });
    expect(save).not.toBeDisabled();
    fireEvent.click(save);
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "/api/v1/plate-groups",
          method: "POST",
          data: expect.objectContaining({
            name: "Vendor Set 1",
            owner_org_id: "org1",
            parent_group_id: null,
          }),
        }),
      ),
    );
  });

  it("edit mode PATCHes only the changed fields", async () => {
    setup({
      group: {
        id: "g1",
        name: "Old Name",
        group_type: "vendor",
        description: null,
        parent_group_id: null,
        owner_org_id: "org1",
        plate_count: 0,
        created_by: "u1",
        version: 1,
        children: [],
      },
    });
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "New Name" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(mocked).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "/api/v1/plate-groups/g1",
          method: "PATCH",
          data: expect.objectContaining({ name: "New Name" }),
        }),
      ),
    );
  });
});
```

Run: `cd frontend && pnpm exec vitest run src/features/inventory/components/plate-group-dialog.test.tsx` — FAIL (module missing).

- [ ] **Step 2: Create/edit dialog.** `frontend/src/features/inventory/components/plate-group-dialog.tsx`:

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Textarea } from "@/shared/components/ui/textarea";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { useCreatePlateGroup, useUpdatePlateGroup } from "../hooks/use-plate-groups";

/** Spec §4.2 seed list — used when no `plate_group_type` vocabulary exists. */
const DEFAULT_GROUP_TYPES = ["vendor", "screening", "master_twin", "hit_collection"];
const NONE = "__none__";

interface VocabularyEntry {
  id: string;
  name: string;
  terms: string[];
}

function useGroupTypeOptions(): string[] {
  const { data } = useQuery({
    queryKey: ["vocabularies"],
    queryFn: ({ signal }) =>
      customInstance<VocabularyEntry[]>({
        url: `${API_V1}/vocabularies`,
        method: "GET",
        signal,
      }),
    staleTime: 5 * 60 * 1000,
  });
  return useMemo(() => {
    const vocab = data?.find((v) => v.name === "plate_group_type");
    return vocab?.terms?.length ? vocab.terms : DEFAULT_GROUP_TYPES;
  }, [data]);
}

export interface PlateGroupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Owner org for creation (ignored in edit mode). */
  orgId: string;
  /** Parent for creation (null = root; ignored in edit mode). */
  parentGroupId: string | null;
  /** Non-null switches the dialog to edit mode. */
  group: PlateGroupNode | null;
}

export function PlateGroupDialog({
  open,
  onOpenChange,
  orgId,
  parentGroupId,
  group,
}: PlateGroupDialogProps) {
  const isEdit = group !== null;
  const [name, setName] = useState("");
  const [groupType, setGroupType] = useState<string>(NONE);
  const [description, setDescription] = useState("");
  const groupTypes = useGroupTypeOptions();
  const create = useCreatePlateGroup();
  const update = useUpdatePlateGroup();
  const pending = create.isPending || update.isPending;

  useEffect(() => {
    if (!open) return;
    setName(group?.name ?? "");
    setGroupType(group?.group_type ?? NONE);
    setDescription(group?.description ?? "");
  }, [open, group]);

  const handleSave = () => {
    const type = groupType === NONE ? null : groupType;
    const desc = description.trim() === "" ? null : description;
    const opts = { onSuccess: () => onOpenChange(false) };
    if (isEdit) {
      update.mutate(
        { groupId: group.id, name, group_type: type, description: desc },
        opts,
      );
    } else {
      create.mutate(
        {
          name,
          owner_org_id: orgId,
          parent_group_id: parentGroupId,
          group_type: type,
          description: desc,
        },
        opts,
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit group" : parentGroupId ? "Add child group" : "New group"}
          </DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="group-name">Name</Label>
            <Input
              id="group-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={300}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label>Type</Label>
            <Select value={groupType} onValueChange={setGroupType}>
              <SelectTrigger aria-label="Group type">
                <SelectValue placeholder="None" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>None</SelectItem>
                {groupTypes.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="group-description">Description</Label>
            <Textarea
              id="group-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={pending || name.trim() === ""}>
            {isEdit ? "Save" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 3: Move dialog.** `frontend/src/features/inventory/components/move-plate-group-dialog.tsx` — parent picker as an indented flat list built from the tree, excluding the group's own subtree (client-side mirror of the server's cycle rule so users only see legal targets; the server still enforces):

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import type { PlateGroupNode, PlateGroupTree } from "../hooks/use-plate-groups";
import { useMovePlateGroup } from "../hooks/use-plate-groups";

const ROOT = "__root__";

interface Option {
  id: string;
  label: string;
}

function collectOptions(
  nodes: PlateGroupNode[],
  excludeId: string,
  depth: number,
  out: Option[],
): void {
  for (const n of nodes) {
    if (n.id === excludeId) continue; // prunes the whole subtree
    out.push({ id: n.id, label: `${" ".repeat(depth * 3)}${n.name}` });
    collectOptions(n.children ?? [], excludeId, depth + 1, out);
  }
}

export interface MovePlateGroupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group: PlateGroupNode;
  tree: PlateGroupTree;
}

export function MovePlateGroupDialog({
  open,
  onOpenChange,
  group,
  tree,
}: MovePlateGroupDialogProps) {
  const [target, setTarget] = useState<string>(ROOT);
  const move = useMovePlateGroup();

  useEffect(() => {
    if (open) setTarget(group.parent_group_id ?? ROOT);
  }, [open, group]);

  const options = useMemo(() => {
    const out: Option[] = [];
    collectOptions(tree.roots, group.id, 0, out);
    return out;
  }, [tree, group.id]);

  const handleMove = () => {
    move.mutate(
      { groupId: group.id, parentGroupId: target === ROOT ? null : target },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Move "{group.name}"</DialogTitle>
        </DialogHeader>
        <Select value={target} onValueChange={setTarget}>
          <SelectTrigger aria-label="New parent">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ROOT}>(top level)</SelectItem>
            {options.map((o) => (
              <SelectItem key={o.id} value={o.id}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={move.isPending}>
            Cancel
          </Button>
          <Button
            onClick={handleMove}
            disabled={move.isPending || target === (group.parent_group_id ?? ROOT)}
          >
            Move
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Assign-plates dialog.** `frontend/src/features/inventory/components/assign-plates-dialog.tsx` — searchable checkbox list of the org's plates (no UUID entry ever); plates already in this group are excluded; plates in *another* group show their move-warning inline:

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { usePlates } from "../hooks/use-plates";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { useAssignPlatesToGroup } from "../hooks/use-plate-groups";

export interface AssignPlatesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group: PlateGroupNode;
}

export function AssignPlatesDialog({ open, onOpenChange, group }: AssignPlatesDialogProps) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const assign = useAssignPlatesToGroup();
  // Org invariant: only same-org plates are assignable — filter server-side.
  const { data: plates, isLoading } = usePlates(
    { owner_org_id: group.owner_org_id },
    { enabled: open },
  );

  useEffect(() => {
    if (open) {
      setSearch("");
      setSelected(new Set());
    }
  }, [open]);

  const candidates = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (plates ?? [])
      .filter((p) => p.group_id !== group.id)
      .filter(
        (p) =>
          q === "" ||
          p.barcode.toLowerCase().includes(q) ||
          p.plate_label.toLowerCase().includes(q),
      );
  }, [plates, search, group.id]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleAssign = () => {
    assign.mutate(
      { groupId: group.id, plateIds: [...selected] },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add plates to "{group.name}"</DialogTitle>
        </DialogHeader>
        <Input
          placeholder="Search barcode or label…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="max-h-72 overflow-y-auto rounded-md border">
          {isLoading ? (
            <p className="p-3 text-sm text-muted-foreground">Loading…</p>
          ) : candidates.length === 0 ? (
            <p className="p-3 text-sm text-muted-foreground">
              No assignable plates in this organization.
            </p>
          ) : (
            <ul className="divide-y">
              {candidates.map((p) => (
                <li key={p.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                  <Checkbox
                    id={`assign-${p.id}`}
                    checked={selected.has(p.id)}
                    onCheckedChange={() => toggle(p.id)}
                  />
                  <label htmlFor={`assign-${p.id}`} className="flex-1 cursor-pointer">
                    <span className="font-mono">{p.barcode}</span>
                    <span className="ml-2 text-muted-foreground">{p.plate_label}</span>
                    {p.group_id ? (
                      <span className="ml-2 text-xs text-amber-600">
                        will move from its current group
                      </span>
                    ) : null}
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={assign.isPending}>
            Cancel
          </Button>
          <Button onClick={handleAssign} disabled={assign.isPending || selected.size === 0}>
            Add {selected.size > 0 ? `(${selected.size})` : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

(If `Checkbox` isn't in `shared/components/ui`, add it via the shadcn pattern used by the repo — check for an existing `checkbox.tsx` first; if genuinely absent, use a plain `<input type="checkbox">` styled minimally instead of adding a component library file in this task.)

- [ ] **Step 5: Wire the dashboard.** In `plate-group-dashboard.tsx`: add state `const [dialog, setDialog] = useState<null | { kind: "create"; parentId: string | null } | { kind: "edit" } | { kind: "move" } | { kind: "assign" } | { kind: "delete" }>(null);` and:
  - "New group" / empty-state "Create group" buttons → `setDialog({ kind: "create", parentId: null })`.
  - `PlateGroupDetails` props: `onAddChild={() => setDialog({ kind: "create", parentId: selectedNode.id })}`, `onAddPlates={() => setDialog({ kind: "assign" })}`, `onEdit={() => setDialog({ kind: "edit" })}`, `onMove={() => setDialog({ kind: "move" })}`, `onDelete={() => setDialog({ kind: "delete" })}`, `onRemovePlates={(ids) => removePlates.mutate({ groupId: selectedNode.id, plateIds: ids })}` (`const removePlates = useRemovePlatesFromGroup();`).
  - Render `<PlateGroupDialog>` (create/edit), `<MovePlateGroupDialog>`, `<AssignPlatesDialog>` bound to that state, plus a delete `AlertDialog` (shadcn `alert-dialog` — copy an existing delete-confirm usage from the repo, e.g. the storage or organization delete) whose confirm calls `useDeletePlateGroup().mutate({ groupId: selectedNode.id }, { onSuccess: () => setSelected(null) })`. On successful delete also close the dialog. Clear `selected` if the org selector changes (already done in Task 8).

- [ ] **Step 6: Verify.**

Run: `cd frontend && pnpm exec vitest run src/features/inventory` — PASS (new dialog tests + no regressions).
Run: `cd frontend && pnpm exec tsc --noEmit` — exit 0.
Run: `cd frontend && pnpm exec biome check src/features/inventory` — exit 0.

- [ ] **Step 7: Commit.**

```bash
git commit -m "feat(frontend): plate-group management dialogs (create/edit, move, assign, delete)" -- frontend/src/features/inventory/components/plate-group-dialog.tsx frontend/src/features/inventory/components/plate-group-dialog.test.tsx frontend/src/features/inventory/components/move-plate-group-dialog.tsx frontend/src/features/inventory/components/assign-plates-dialog.tsx frontend/src/features/inventory/components/plate-group-dashboard.tsx
```

---

### Task 10: Runtime verification + legacy-flavored sample data (CONTROLLER-DRIVEN — not a subagent task)

The controller (main session) runs this: launch the stack, seed sample data shaped like the legacy plate tracker's sets, then drive the real UI in Chrome (Claude for Chrome; real Google sign-in `rhymesofsid@gmail.com` → saclab-dev workspace is explicitly authorized) — falling back to the repo `verify` skill's headless recipe if Chrome tooling is unavailable.

- [ ] Launch: `make up` + `make dev` (backend :8000, frontend :3000).
- [ ] Seed via API (dev-mode auth per the verify skill / `reference_dev_api_access`): mine legacy set names from `~/workspace/legacy/intranet/web-files/sacnet/` (plate-tracker) for realistic data — a vendor-library root with 2 child sets, a screening root, ~6-10 plates with legacy-style zero-padded barcodes (`000123`) assigned across groups, two orgs (public + tamu exist in prod Sentinel; locally use FakeAuth orgs or the real dev workspace's orgs).
- [ ] Chrome pass: sign in, open Inventory → Plate Groups; verify: tree renders + expands/collapses; counts match; node click → details; create root + child; rename; move (and verify the picker excludes own subtree); assign plates (search by barcode); remove plate; delete (confirm dialog; children-conflict toast when applicable); org selector switches trees; plates list still works (group_id filter via a group's details "Plates" list).
- [ ] Screenshot the tree page for the issue comment.
- [ ] Any defect found → fix subagent, re-verify, before Task 11.

### Task 11: Suites, issue, push (final)

- [ ] Full backend suite: `cd backend && uv run pytest -q` — only the 10 documented baseline failures (`docs/backlog/pre-existing-test-failures.md`).
- [ ] Full FE suite: `cd frontend && pnpm exec vitest run` — green. `pnpm exec biome check src` — exit 0 (or matching the repo's pre-existing baseline).
- [ ] `git add -f docs/superpowers/plans/2026-08-11-s3-plate-groups.md` + commit (docs/ is gitignored; plans are force-added).
- [ ] Comment on issue sidxz/cellar#71: S3 shipped — scope summary, commit range, screenshot.
- [ ] Push. Update memory (`project_plate_tracker_port.md`): S3 shipped, S4 next.

---

## Execution notes for the controller

- Tasks 1, 3, 5 are prose+code-complete → cheap/mid-tier implementers. Tasks 4, 6 touch real DB/test infra → mid-tier. Tasks 2, 7 need the live-backend regen dance → mid-tier with exact commands. Tasks 8, 9 are the largest FE surfaces → capable model.
- Tasks 2 and 7 both regenerate orval — if executing back-to-back with no intervening backend change, Task 7's regen still runs (Task 6 added routes after Task 2's regen).
- The S2 spec file needs a §4.2/§9/§10 sync note ONLY if implementation deviates from spec — record deviations (group GET-by-id omitted [tree is the read surface, matching §9's use-case list which has no GetPlateGroup]; `group_type` free-string decision; groups owner NOT NULL) in the spec file in Task 11 if reviewers agree they're spec-visible.

