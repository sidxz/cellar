# S5 — Kiosk + Insights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship spec S5 (KioskDevice aggregate + token-authed kiosk scan/confirm endpoints; per-org plate-insights read model + Plotly dashboard tab) plus the S5 intake batch (borrowed-plates-in-My-org filter, admin loan-verb visibility, tree count scoping, tree polish, two coverage-gap tests, S4 minors).

**Architecture:** DDD + Clean Architecture + Railway, mirroring S4's PlateLoan stack: new `KioskDevice` aggregate (domain → migration 064 → repo → use cases → routes), kiosk routes excluded from Sentinel middleware and authed by an `X-Kiosk-Token` header validated inside the use case; insights follow the `InventorySummaryReader` read-model pattern (application Protocol + SQLAlchemy impl over its own session factory). FE extends the existing plate-groups dashboard with a tabbed Insights panel and adds a kiosk-device admin page under workspace-config.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2 async / Alembic / Lagom / returns; Next.js 16 / React 19 / TanStack Query / react-d3-tree / Plotly (via `shared/lib/plotly.tsx`) / orval.

## Global Constraints

- **Read `docs/backend-code-guidelines.md` + `docs/patterns-and-conventions.md` before writing any backend code** (CLAUDE.md mandate; workspace scoping, auth guards, railway checklist).
- **Commits: ALWAYS explicit pathspecs** (`git commit -m "…" -- <paths>`). The working tree has the user's uncommitted `frontend/package.json` + `frontend/pnpm-lock.yaml` sentinel-auth bump (`^0.17.0 → ^0.19.0`) and untracked `.claude/skills/` — these must NEVER be swept into a commit.
- **pnpm:** bare `pnpm` is broken on this machine (Homebrew pnpm 9 + Node 25). Always use `/Users/sidx/Library/pnpm/pnpm`.
- **FE tests:** `cd frontend && /Users/sidx/Library/pnpm/pnpm test` (no Makefile target). Baseline 1000 green. **Biome:** `pnpm lint` gates at error severity for format — verify by EXIT CODE, never piped output.
- **Backend tests:** `cd backend && uv run pytest tests/unit/ -q` (unit), `uv run pytest tests/api/ -q` + `tests/integration/` (need `make up` DB). Baseline: 10 documented pre-existing failures (`docs/backlog/pre-existing-test-failures.md`), 3770 passed at S4 close.
- **Ruff line length 99** (backend). Guards live in `application/auth.py`; **user-attributed guards need `require_authenticated(auth)` FIRST** (`require_workspace_role(None)` bypasses — worker convention; S4 lesson).
- **orval regen batching (recorded deviation from per-change regen):** one regen per contiguous backend batch, always BEFORE the first FE task consuming it — Task 4 regens (covers Task 1's `status` enum + Task 4's MeResponse), Task 10 regens (covers kiosk-devices + kiosk + Task 9's insights). Regen is all-or-nothing for `model/`; review the diff; orval never prunes `model/index.ts`.
- **Protocol wideners must sweep ALL structural implementers** (S1/S4 `_AuthShim` lesson): after widening any repository Protocol, `grep -rn "def <method>(" backend/src backend/tests` and update every fake/impl.
- **UI rules:** names never UUIDs (org pickers via `useOrgs`); token shown ONCE with explicit copy gesture; no autosave on consequential actions; toasts via `showSuccess`/`showError` from `@/shared/lib/toast`.
- **New routers register in BOTH** `interface/app.py` and `tests/api/conftest.py::_create_test_app` (separate include lists; missing the second silently 404s API tests). New `*Dep` aliases go in `interface/dependencies/_inventory.py` (already star-exported).
- Migration numbering: next is **064**; `revision` string == filename stem; `down_revision = "063_plate_loans"`.
- Backend serving for orval regen / runtime verify: see **Appendix A** (auth-stubbed `serve_verify.py` recipe).

---

### Task 1: Backend cleanup batch (coverage gaps + S4 minors)

**Files:**
- Modify: `backend/tests/api/test_registered_plates.py` (append 2 tests)
- Modify: `backend/tests/api/test_plate_loans.py` (tighten 2 tests, add 1)
- Modify: `backend/tests/unit/test_plate_loan.py` (add 1 test)
- Modify: `backend/src/cellar/interface/routes/plate_loans.py:158-177` (status param → enum)
- Delete: `docs/backlog/plate-response-coverage-gaps.md` (both items closed here)

**Interfaces:**
- Produces: `GET /api/v1/plate-loans` `status` query param typed `LoanStatus | None` (OpenAPI enum `open|closed`; invalid values now 422 instead of silently matching zero rows). Consumed by Task 4's FE typing.

- [ ] **Step 1: Write the two coverage-gap API tests** (fix shapes from `docs/backlog/plate-response-coverage-gaps.md`). Append to `backend/tests/api/test_registered_plates.py`, reusing the file's existing register/derive helpers (mirror their exact names/payloads — the shapes below are the fallback if none exist):

```python
class TestCoverageGaps:
    """Closes docs/backlog/plate-response-coverage-gaps.md (S3 triage)."""

    async def test_delete_plate_with_children_conflicts_then_ok(
        self, client: AsyncClient
    ) -> None:
        parent = await _register_plate(client, f"CG-{uuid.uuid4().hex[:8]}")
        resp = await client.post(
            f"/api/v1/plates/{parent['id']}/derive",
            json={"barcode": f"CG-{uuid.uuid4().hex[:8]}", "plate_label": "Daughter"},
        )
        assert resp.status_code == 201, resp.text
        child = resp.json()

        resp = await client.delete(f"/api/v1/plates/{parent['id']}")
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        # The message must NOT count children (count was a visibility oracle).
        assert not any(ch.isdigit() for ch in detail), detail

        assert (await client.delete(f"/api/v1/plates/{child['id']}")).status_code == 204
        assert (await client.delete(f"/api/v1/plates/{parent['id']}")).status_code == 204

    async def test_plate_response_enum_fields_serialize_as_wire_values(
        self, client: AsyncClient
    ) -> None:
        plate = await _register_plate(client, f"CG-{uuid.uuid4().hex[:8]}")
        assert plate["format"] == "96"
        assert plate["plate_type"] == "assay"
        assert plate["status"] == "registered"
```

(If the file lacks a register helper, add: `async def _register_plate(client, barcode): resp = await client.post("/api/v1/plates", json={"barcode": barcode, "plate_label": f"Plate {barcode}", "format": "96", "plate_type": "assay"}); assert resp.status_code == 201, resp.text; return resp.json()` — match the derive route's actual body model in `interface/routes/registered_plates.py:351`.)

- [ ] **Step 2: Run them** — `cd backend && uv run pytest tests/api/test_registered_plates.py -q -k CoverageGaps`. Expected: PASS (they pin existing behavior; if the 409 message contains a digit, that's a regression to fix, not a test to loosen).

- [ ] **Step 3: Type the ListLoans status filter.** In `backend/src/cellar/interface/routes/plate_loans.py:161`, change `status: str | None = None` → `status: LoanStatus | None = None` (`LoanStatus` already imported at line 18) and at line 171 pass `status=status.value if status is not None else None` (ListLoansQuery.status stays `str | None`).

- [ ] **Step 4: Add a 422 test for the enum param.** Append to `backend/tests/api/test_plate_loans.py`:

```python
    async def test_list_loans_rejects_unknown_status(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/plate-loans", params={"status": "opne"})
        assert resp.status_code == 422  # was: silently zero rows
```

- [ ] **Step 5: Tighten the approve tests** in `backend/tests/api/test_plate_loans.py`:
  - In the test where `approver_client_own_org` approves, add an `approved_by` value assertion — fetch the approver's id first: `me = (await approver_client_own_org.get("/api/v1/user/me")).json()`, then after approving assert `body["approved_by"] == me["user_id"]`.
  - Find the wrong-org-beats-action test (editor in `OTHER_ORG_ID` denied). It currently relies on `granted_actions=None` (permissive default) so the org guard is what rejects — make the grant explicit so the test proves ordering: build the client with `granted_actions={LOAN_APPROVE_ACTION}` via the file's `_client_as(...)` helper (import `LOAN_APPROVE_ACTION` from `cellar.application.auth`) and keep the 403/404 assertion.

- [ ] **Step 6: Add the approved_by-first-wins unit test.** In `backend/tests/unit/test_plate_loan.py`, mirroring the file's loan-builder helpers:

```python
    def test_approved_by_first_approver_wins(self) -> None:
        loan = _make_loan(items=2)  # two REQUESTED items — use the file's builder
        first, second = uuid.uuid4(), uuid.uuid4()
        loan.approve_items([loan.items[0].id], approved_by=first)
        loan.approve_items([loan.items[1].id], approved_by=second)
        assert loan.approved_by == first
```

(Match `approve_items`' real signature in `domain/inventory/plate_loan.py:137-145`; the assertion is that a second approver does not overwrite `approved_by`.)

- [ ] **Step 7: Run the touched suites** — `uv run pytest tests/unit/test_plate_loan.py tests/api/test_plate_loans.py -q`. Expected: PASS.

- [ ] **Step 8: Delete the closed backlog note + commit**

```bash
git rm docs/backlog/plate-response-coverage-gaps.md
git add backend/tests/api/test_registered_plates.py backend/tests/api/test_plate_loans.py \
  backend/tests/unit/test_plate_loan.py backend/src/cellar/interface/routes/plate_loans.py
git commit -m "test(inventory): close plate coverage gaps; type loan status filter; tighten approve tests" \
  -- backend/tests backend/src/cellar/interface/routes/plate_loans.py docs/backlog/plate-response-coverage-gaps.md
```

---

### Task 2: "My org" plates filter includes borrowed-by-us (spec §5, S4 deviation #5)

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/registered_plate_repository.py:111-153`
- Modify: `backend/src/cellar/domain/inventory/repository.py` (RegisteredPlateRepository.search Protocol)
- Modify: `backend/src/cellar/application/inventory/registered_plates.py:257-281` (ListPlates)
- Test: `backend/tests/api/test_plate_loans.py` (borrowed-filter tests live here — loan helpers exist)

**Interfaces:**
- Produces: `search(..., owner_scope_plate_ids: set[uuid.UUID] | None = None)` — extra plate ids OR-ed into the `owner_org_id` filter arm ONLY. `ListPlates` passes the caller's borrowed set iff `input.owner_org_id == auth.org_id`. No FE change (the FE `MY_ORG` sentinel already resolves to the real org UUID client-side — verified `plate-list.tsx:57-66`).
- Consumes: `PlateVisibilityService.borrowed_plate_ids` (already computed on every ListPlates call).

- [ ] **Step 1: Write the failing API tests.** Append to `backend/tests/api/test_plate_loans.py`:

```python
class TestMyOrgFilterIncludesBorrowed:
    """Spec §5 'plus borrowed-by-us' — S4 deviation #5 closure."""

    async def _borrow_foreign_plate(self, client, editor_client_own_org) -> dict:
        # Admin registers a plate owned by OTHER org; AUTH-org editor borrows it.
        plate = await _mk_plate(client, f"BR-{uuid.uuid4().hex[:8]}",
                                owner_org_id=str(OTHER_ORG_ID))
        loan = await _mk_loan(editor_client_own_org, plate_ids=[plate["id"]])
        return plate

    async def test_my_org_filter_includes_borrowed_foreign_plate(
        self, client, editor_client_own_org
    ) -> None:
        plate = await self._borrow_foreign_plate(client, editor_client_own_org)
        resp = await editor_client_own_org.get(
            "/api/v1/plates", params={"owner_org_id": str(AUTH_ORG_ID)}
        )
        assert resp.status_code == 200
        assert plate["id"] in [p["id"] for p in resp.json()]

    async def test_explicit_foreign_org_filter_not_widened(
        self, client, editor_client_own_org
    ) -> None:
        # Borrowed plate owned by OTHER org must NOT leak into a browse of a
        # third org, and filtering the OWNER org itself needs no widening.
        plate = await self._borrow_foreign_plate(client, editor_client_own_org)
        third = uuid.uuid4()
        resp = await editor_client_own_org.get(
            "/api/v1/plates", params={"owner_org_id": str(third)}
        )
        assert plate["id"] not in [p["id"] for p in resp.json()]
```

Adapt `_mk_plate`/`_mk_loan` to the file's real helper signatures (`_mk_plate(client, barcode)` exists per S4; pass `owner_org_id` the way the file's cross-org tests already do). Note: an active loan in ANY active status counts as borrowed (`borrowed_plate_ids` uses the ACTIVE set), so an unapproved request suffices.

- [ ] **Step 2: Run to verify the first test fails** — `uv run pytest tests/api/test_plate_loans.py -q -k MyOrgFilter`. Expected: first test FAILS (plate absent — the owner AND-clause excludes it), second PASSES.

- [ ] **Step 3: Widen the repo.** In `registered_plate_repository.py`, add to the `search` signature (after `include_plate_ids`): `owner_scope_plate_ids: set[uuid.UUID] | None = None`, and replace lines 152-153:

```python
        if owner_org_id is not None:
            owner_terms = [RegisteredPlateModel.owner_org_id == owner_org_id]
            # spec §5 "plus borrowed-by-us": when the caller filters by their
            # OWN org, plates actively borrowed by that org count as mine.
            # Truthy-guard mirrors the exclusion block's empty-IN gotcha.
            if owner_scope_plate_ids:
                owner_terms.append(RegisteredPlateModel.id.in_(owner_scope_plate_ids))
            stmt = stmt.where(or_(*owner_terms))
```

Mirror the same parameter onto the `RegisteredPlateRepository.search` Protocol in `domain/inventory/repository.py`, then sweep implementers: `grep -rn "async def search(" backend/src backend/tests` — update every fake with the new kwarg.

- [ ] **Step 4: Wire the use case.** In `application/inventory/registered_plates.py` `ListPlates.__call__`, after the `borrowed = …` line:

```python
            owner_scope = (
                borrowed
                if auth is not None
                and input.owner_org_id is not None
                and input.owner_org_id == auth.org_id
                else None
            )
```

and add `owner_scope_plate_ids=owner_scope,` to the `self._repo.search(...)` call. (Decided at use-case layer so an explicit browse of org X by a member of org Y is never widened.)

- [ ] **Step 5: Run tests** — `uv run pytest tests/api/test_plate_loans.py tests/api/test_registered_plates.py -q`. Expected: PASS (including S2's privacy suite — the privacy OR-block is untouched).

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(inventory): My-org plate filter includes plates borrowed by the org (spec §5)" \
  -- backend/src/cellar backend/tests
```

---

### Task 3: Per-org count scoping in GetGroupTree (S3 minor)

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_group_repository.py:71-81`
- Modify: `backend/src/cellar/domain/inventory/repository.py` (PlateGroupRepository Protocol, `count_plates_by_group`)
- Modify: `backend/src/cellar/application/inventory/plate_groups.py:438` (GetGroupTree)
- Test: `backend/tests/integration/inventory/test_plate_group_repository.py` (append)

**Interfaces:**
- Produces: `count_plates_by_group(workspace_id, owner_org_id: uuid.UUID | None = None)` — org-scoped GROUP BY (efficiency fix; values were already per-group-correct).

- [ ] **Step 1: Write the integration test** (append to `test_plate_group_repository.py`, using its session/builder fixtures): seed two orgs, one group each, one plate per group with matching `owner_org_id`; assert `await repo.count_plates_by_group(ws, owner_org_id=org_a)` returns ONLY org A's group id (`org_b`'s group absent from the dict), with the correct count; and `owner_org_id=None` keeps the old workspace-wide behavior.

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/integration/inventory/test_plate_group_repository.py -q -k count`. Expected: FAIL (foreign group present in dict).

- [ ] **Step 3: Implement.** Add the kwarg and conditional where-clause:

```python
    async def count_plates_by_group(
        self, workspace_id: uuid.UUID, owner_org_id: uuid.UUID | None = None
    ) -> dict[uuid.UUID, int]:
        stmt = (
            select(RegisteredPlateModel.group_id, func.count())
            .where(
                RegisteredPlateModel.workspace_id == workspace_id,
                RegisteredPlateModel.group_id.is_not(None),
            )
            .group_by(RegisteredPlateModel.group_id)
        )
        if owner_org_id is not None:
            stmt = stmt.where(RegisteredPlateModel.owner_org_id == owner_org_id)
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}
```

Mirror the kwarg on the Protocol; sweep fakes (`grep -rn "count_plates_by_group" backend/src backend/tests`). In `GetGroupTree` (plate_groups.py:438) pass `owner_org_id=org_id`.

- [ ] **Step 4: Run** — integration file + `uv run pytest tests/api/test_plate_groups.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "perf(inventory): scope group plate-count query to the requested org" -- backend/src/cellar backend/tests`

---

### Task 4: MeResponse admin fields + FE loans admin visibility (closes `docs/backlog/loan-approvals-admin-visibility.md`)

**Files:**
- Modify: `backend/src/cellar/interface/routes/user.py:23-39` (MeResponse)
- Test: the existing `/me` API test file (`grep -rln 'user/me' backend/tests/api`) — extend
- Regen: `frontend/src/shared/lib/api/model/` (orval — covers Task 1's status enum too; Appendix A serve recipe)
- Modify: `frontend/src/features/inventory/hooks/use-plate-loans.ts:20-27` (LoanFilters.status typing)
- Modify: `frontend/src/features/inventory/components/loan-dashboard.tsx:45-89`
- Modify: `frontend/src/features/inventory/components/loan-card.tsx:74-91`
- Test: `frontend/src/features/inventory/components/loan-card.test.tsx` (new)
- Delete: `docs/backlog/loan-approvals-admin-visibility.md`

**Interfaces:**
- Produces: `MeResponse.workspace_role: str`, `MeResponse.is_admin: bool` (generated type `MeResponse` gains both after regen). FE: Approvals tab visible to workspace admins of any org; approvals query drops the org filter for admins; `canApprove = me.is_admin || me.org_id === loan.owner_org_id` gates owner verbs per card.
- Consumes: `AuthContext.workspace_role` / `.is_admin` (Protocol already declares both — `application/auth.py:17-43`; FakeAuth provides them).

- [ ] **Step 1: Backend — extend MeResponse** (`user.py`): add fields `workspace_role: str` and `is_admin: bool` to the model; in the route pass `workspace_role=auth.workspace_role, is_admin=auth.is_admin`. Extend the existing `/me` API test: admin fixture → `is_admin is True, workspace_role == "admin"`; `editor_client` → `is_admin is False`. Run the file; PASS.

- [ ] **Step 2: Orval regen.** Boot the auth-stubbed backend on :8000 (Appendix A), then `cd frontend && /Users/sidx/Library/pnpm/pnpm generate:api`. Review the diff: `meResponse.ts` gains both fields; `listLoansApiV1PlateLoansGetParams.ts` status becomes the enum union. Regen is all-or-nothing — confirm no unrelated deletions; orval never prunes `model/index.ts`.

- [ ] **Step 3: Type LoanFilters.status.** In `use-plate-loans.ts` change `status?: string;` → `status?: LoanStatus;` (enum already imported in the module per S4). Fix any literal call sites (loan-dashboard passes `"open"` → `LoanStatus.open`).

- [ ] **Step 4: Write the failing loan-card test** (`loan-card.test.tsx`, colocated; mock `@/shared/lib/toast` and `@/shared/lib/api/custom-instance` per the file conventions in `use-plates.test.tsx`; wrap in a local QueryClientProvider wrapper):

```tsx
const baseLoan = {
  id: "l1", status: "open", owner_org_id: "org-A", borrower_org_id: "org-B",
  requested_by: "u1", due_date: null, notes: null,
  items: [{ id: "i1", plate_id: "p1", status: "requested", status_changed_at: "2026-08-13T00:00:00Z" }],
  plates: {}, created_at: "2026-08-13T00:00:00Z",
} as unknown as PlateLoan;

it("shows owner verbs to a foreign-org workspace admin on the approvals tab", () => {
  render(<LoanCard loan={baseLoan} context="approvals"
    me={{ user_id: "u9", email: "", name: "", org_id: "org-Z", is_admin: true, workspace_role: "admin" } as MeResponse} />,
    { wrapper });
  expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
});

it("hides owner verbs from a foreign-org non-admin", () => {
  render(<LoanCard loan={baseLoan} context="approvals"
    me={{ user_id: "u9", email: "", name: "", org_id: "org-Z", is_admin: false, workspace_role: "editor" } as MeResponse} />,
    { wrapper });
  expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
});

it("shows owner verbs to an owner-org member", () => {
  render(<LoanCard loan={baseLoan} context="approvals"
    me={{ user_id: "u9", email: "", name: "", org_id: "org-A", is_admin: false, workspace_role: "editor" } as MeResponse} />,
    { wrapper });
  expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
});
```

(Match the real `PlateLoan` item/field names from the generated model; the S4 card renders `Approve (1)` — the `/approve/i` name regex covers it.) Run: `pnpm test loan-card` — first test FAILS (card is context-gated only today; a foreign-org admin currently sees the button, so the FAILING one is test 2 — either way, red first, then green).

- [ ] **Step 5: Implement the card gate.** In `loan-card.tsx` replace the `showOwner` line (L77):

```tsx
  const canApprove = !!me && (me.is_admin === true || me.org_id === loan.owner_org_id);
  const showOwner = context === "approvals" && canApprove;
```

Update the locked-UX comment (backlog item now closed) — All tab stays read-only.

- [ ] **Step 6: Widen the Approvals tab for admins + /me-failure toast.** In `loan-dashboard.tsx`:

```tsx
  const { data: me, isError: meFailed } = useCurrentUser();
  const isAdmin = me?.is_admin === true;
  const orgId = me?.org_id ?? undefined;
  const showApprovals = isAdmin || !!orgId;

  useEffect(() => {
    if (meFailed) showError("Could not load your identity — the Approvals tab is unavailable.");
  }, [meFailed]);

  const approvals = useLoans(
    { status: LoanStatus.open, owner_org_id: isAdmin ? undefined : orgId },
    { enabled: showApprovals },
  );
```

Replace both `{orgId ? …}` tab guards with `{showApprovals ? …}`. Imports: `useEffect`, `showError`, `LoanStatus`.

- [ ] **Step 7: Run FE suite** — `/Users/sidx/Library/pnpm/pnpm test` (full) + `pnpm lint` (check exit code). Expected: baseline + 3 green.
- [ ] **Step 8: Commit + close backlog**

```bash
git rm docs/backlog/loan-approvals-admin-visibility.md
git commit -m "feat: surface is_admin/workspace_role on /me; admins see and act on all approvals" \
  -- backend/src/cellar/interface/routes/user.py backend/tests frontend/src \
     docs/backlog/loan-approvals-admin-visibility.md
```

(`frontend/src` pathspec is safe — the user's uncommitted files are `frontend/package.json`/`pnpm-lock.yaml`, outside it. Include the regenerated `frontend/src/shared/lib/api/model/` in this commit.)

---

### Task 5: KioskDevice domain aggregate

**Files:**
- Create: `backend/src/cellar/domain/inventory/kiosk_device.py`
- Modify: `backend/src/cellar/domain/inventory/events.py` (append 2 events)
- Test: `backend/tests/unit/test_kiosk_device.py`

**Interfaces:**
- Produces: `KioskDevice` aggregate — `create(workspace_id, org_id, name, token_hash, created_by)` classmethod (validates + emits `KioskDeviceCreated`), `revoke()` (idempotent; emits `KioskDeviceRevoked` once), fields `id, workspace_id, org_id, name, token_hash, is_active, last_seen_at, created_by, created_at, updated_at, version`. Events `KioskDeviceCreated{org_id, name, created_by}` / `KioskDeviceRevoked{org_id, name}`.
- Consumes: `AggregateRoot` (`domain/shared/entity.py`), `ValidationError`, `DomainEvent`.

- [ ] **Step 1: Write failing unit tests** (`tests/unit/test_kiosk_device.py`):

```python
"""KioskDevice aggregate unit tests (spec §4.5)."""

import uuid

import pytest

from cellar.domain.inventory.events import KioskDeviceCreated, KioskDeviceRevoked
from cellar.domain.inventory.kiosk_device import KioskDevice
from cellar.domain.shared.errors import ValidationError

WS = uuid.uuid4()
ORG = uuid.uuid4()
USER = uuid.uuid4()
HASH = "a" * 64


def _make() -> KioskDevice:
    return KioskDevice.create(
        workspace_id=WS, org_id=ORG, name="Bench scanner", token_hash=HASH, created_by=USER
    )


class TestCreate:
    def test_create_sets_fields_and_emits(self) -> None:
        device = _make()
        assert device.is_active is True
        assert device.last_seen_at is None
        assert device.token_hash == HASH
        events = device.collect_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, KioskDeviceCreated)
        assert (event.org_id, event.name, event.created_by) == (ORG, "Bench scanner", USER)

    def test_create_strips_and_requires_name(self) -> None:
        with pytest.raises(ValidationError):
            KioskDevice.create(
                workspace_id=WS, org_id=ORG, name="   ", token_hash=HASH, created_by=USER
            )

    def test_create_rejects_overlong_name(self) -> None:
        with pytest.raises(ValidationError):
            KioskDevice.create(
                workspace_id=WS, org_id=ORG, name="x" * 101, token_hash=HASH, created_by=USER
            )

    def test_create_rejects_non_sha256_hash(self) -> None:
        with pytest.raises(ValidationError):
            KioskDevice.create(
                workspace_id=WS, org_id=ORG, name="Ok", token_hash="short", created_by=USER
            )


class TestRevoke:
    def test_revoke_deactivates_and_emits_once(self) -> None:
        device = _make()
        device.collect_events()
        device.revoke()
        assert device.is_active is False
        events = device.collect_events()
        assert len(events) == 1 and isinstance(events[0], KioskDeviceRevoked)

    def test_revoke_is_idempotent(self) -> None:
        device = _make()
        device.revoke()
        device.collect_events()
        device.revoke()  # second call: no-op, no duplicate audit event
        assert device.collect_events() == []
```

(If the event-drain method on `AggregateRoot` is named differently than `collect_events`, mirror `tests/unit/test_plate_loan.py`'s usage — do NOT invent a new accessor.)

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/unit/test_kiosk_device.py -q`. Expected: FAIL (module missing).

- [ ] **Step 3: Add the events** (append to `domain/inventory/events.py`, matching the file's dataclass style):

```python
@dataclass(frozen=True, kw_only=True)
class KioskDeviceCreated(DomainEvent):
    org_id: uuid.UUID
    name: str
    created_by: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class KioskDeviceRevoked(DomainEvent):
    org_id: uuid.UUID
    name: str
```

- [ ] **Step 4: Implement the aggregate** (`domain/inventory/kiosk_device.py`):

```python
"""KioskDevice aggregate — org-bound scan-station credential (spec §4.5).

The plaintext token exists only at creation time (application layer);
the domain stores its sha256 hexdigest. A device acts only on plates
whose owner org matches its org — enforced by the kiosk use cases.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.inventory.events import KioskDeviceCreated, KioskDeviceRevoked
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError

MAX_NAME_LENGTH = 100
_SHA256_HEX_LENGTH = 64


class KioskDevice(AggregateRoot):
    """Admin-issued device credential for kiosk scan/confirm endpoints."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        org_id: uuid.UUID,
        name: str,
        token_hash: str,
        is_active: bool = True,
        last_seen_at: datetime | None = None,
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.org_id = org_id
        self.name = name
        self.token_hash = token_hash
        self.is_active = is_active
        self.last_seen_at = last_seen_at
        self.created_by = created_by

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        org_id: uuid.UUID,
        name: str,
        token_hash: str,
        created_by: uuid.UUID,
    ) -> KioskDevice:
        name = name.strip()
        if not name:
            raise ValidationError("Device name is required")
        if len(name) > MAX_NAME_LENGTH:
            raise ValidationError(f"Device name exceeds {MAX_NAME_LENGTH} characters")
        if len(token_hash) != _SHA256_HEX_LENGTH:
            raise ValidationError("token_hash must be a sha256 hexdigest")
        device = cls(
            workspace_id=workspace_id,
            org_id=org_id,
            name=name,
            token_hash=token_hash,
            created_by=created_by,
        )
        device.register_event(
            KioskDeviceCreated(
                aggregate_id=device.id,
                aggregate_type="KioskDevice",
                workspace_id=workspace_id,
                org_id=org_id,
                name=name,
                created_by=created_by,
            )
        )
        return device

    def revoke(self) -> None:
        """Deactivate the credential. Idempotent — a second revoke is a no-op."""
        if not self.is_active:
            return
        self.is_active = False
        self.updated_at = datetime.now(UTC)
        self.register_event(
            KioskDeviceRevoked(
                aggregate_id=self.id,
                aggregate_type="KioskDevice",
                workspace_id=self.workspace_id,
                org_id=self.org_id,
                name=self.name,
            )
        )
```

(Match `_emit`-style kwargs to how `DomainEvent` is actually constructed in `plate_loan.py` — `aggregate_id/aggregate_type/workspace_id` are the base fields.)

- [ ] **Step 5: Run** — `uv run pytest tests/unit/test_kiosk_device.py -q`. Expected: PASS.
- [ ] **Step 6: Commit** — `git commit -m "feat(domain): KioskDevice aggregate with create/revoke lifecycle events" -- backend/src/cellar/domain backend/tests/unit/test_kiosk_device.py`

---

### Task 6: Kiosk persistence — migration 064, ORM, repository

**Files:**
- Create: `backend/alembic/versions/064_kiosk_devices.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/kiosk_device_models.py`
- Modify: `backend/src/cellar/domain/inventory/repository.py` (append Protocol)
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/kiosk_device_repository.py`
- Test: `backend/tests/integration/inventory/test_kiosk_device_repository.py`
- Modify: whichever module registers inventory models for metadata (mirror how `plate_loan_models` is imported — `grep -rn "plate_loan_models" backend/src backend/alembic` and add `kiosk_device_models` alongside every hit)

**Interfaces:**
- Produces:

```python
@runtime_checkable
class KioskDeviceRepository(Protocol):
    """Repository for KioskDevice aggregates."""

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> KioskDevice | None: ...
    async def find_by_workspace(self, workspace_id: uuid.UUID) -> list[KioskDevice]: ...
    async def find_by_name(self, workspace_id: uuid.UUID, name: str) -> KioskDevice | None: ...
    async def find_active_by_token_hash(self, token_hash: str) -> KioskDevice | None: ...
    async def touch_last_seen(self, device_id: uuid.UUID) -> None: ...
    async def save(self, aggregate: KioskDevice) -> None: ...
```

`find_active_by_token_hash` is deliberately workspace-UNSCOPED — the token IS the identity (unique index); it returns only `is_active` rows. `touch_last_seen` is a direct UPDATE that does NOT bump `version` (telemetry, not domain state — avoids optimistic conflicts between rapid scans).

- [ ] **Step 1: ORM model** (`kiosk_device_models.py`, mirror `plate_loan_models.py` imports/style):

```python
"""SQLAlchemy model for the KioskDevice aggregate."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from cellar.infrastructure.persistence.sqlalchemy.base import (
    Base,
    EntityModelMixin,
    VersionMixin,
    WorkspaceIdMixin,
)


class KioskDeviceModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    """Persistent model for KioskDevice — token stored as sha256 hexdigest only."""

    __tablename__ = "kiosk_devices"

    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_kiosk_devices_ws_name"),
        # Token lookup is cross-workspace (the token is the identity) — unique
        # doubles as the lookup index.
        UniqueConstraint("token_hash", name="uq_kiosk_devices_token_hash"),
        Index("ix_kiosk_devices_ws_org", "workspace_id", "org_id"),
    )
```

- [ ] **Step 2: Migration** (`064_kiosk_devices.py`, mirror 063's header/conventions):

```python
"""kiosk_devices table (spec §4.5, §8).

Revision ID: 064_kiosk_devices
"""

import sqlalchemy as sa
from alembic import op

revision = "064_kiosk_devices"
down_revision = "063_plate_loans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kiosk_devices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_kiosk_devices_ws_name"),
        sa.UniqueConstraint("token_hash", name="uq_kiosk_devices_token_hash"),
    )
    op.create_index("ix_kiosk_devices_ws_org", "kiosk_devices", ["workspace_id", "org_id"])


def downgrade() -> None:
    op.drop_index("ix_kiosk_devices_ws_org", table_name="kiosk_devices")
    op.drop_table("kiosk_devices")
```

(Exact column kwargs: mirror 063's table blocks — if 063 declares `workspace_id` index via separate `op.create_index`, do the same.)

- [ ] **Step 3: Repository impl** (`kiosk_device_repository.py`) — mirror `SQLAlchemyOrgPlatePolicyRepository`'s structure (uow-bound session, model↔domain mapping, optimistic-version save). The two non-boilerplate methods:

```python
    async def find_active_by_token_hash(self, token_hash: str) -> KioskDevice | None:
        stmt = select(KioskDeviceModel).where(
            KioskDeviceModel.token_hash == token_hash,
            KioskDeviceModel.is_active.is_(True),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def touch_last_seen(self, device_id: uuid.UUID) -> None:
        # ponytail: raw UPDATE, no version bump — last_seen is telemetry;
        # rapid scans must not trade optimistic-concurrency conflicts.
        await self._session.execute(
            update(KioskDeviceModel)
            .where(KioskDeviceModel.id == device_id)
            .values(last_seen_at=func.now())
        )
```

`find_by_workspace` orders by `name`. Append the `KioskDeviceRepository` Protocol (Interfaces block above) to `domain/inventory/repository.py`. Register the model module for metadata (Step 0 grep).

- [ ] **Step 4: Integration tests** (`test_kiosk_device_repository.py`, mirror `test_plate_loan_repository.py` fixtures): (a) save → find_by_id round-trips every field; (b) `find_active_by_token_hash` finds the device, returns None after `revoke()`+save; (c) duplicate `(workspace, name)` insert raises IntegrityError; (d) `touch_last_seen` sets the timestamp WITHOUT bumping `version` (reload and assert `version` unchanged, `last_seen_at` not None); (e) `find_by_name` exact match.

- [ ] **Step 5: Run migration + tests** — `cd backend && uv run alembic upgrade head && uv run pytest tests/integration/inventory/test_kiosk_device_repository.py -q`. Expected: PASS. Also `uv run alembic downgrade -1 && uv run alembic upgrade head` once to prove downgrade works.

- [ ] **Step 6: Commit** — `git commit -m "feat(inventory): kiosk_devices persistence (migration 064, ORM, repository)" -- backend/alembic backend/src/cellar backend/tests/integration`

---

### Task 7: Kiosk-device admin use cases + routes

**Files:**
- Create: `backend/src/cellar/application/inventory/kiosk_devices.py`
- Create: `backend/src/cellar/interface/routes/kiosk_devices.py`
- Modify: `backend/src/cellar/interface/dependencies/_inventory.py` (3 new `*Dep`)
- Modify: `backend/src/cellar/infrastructure/di/_inventory.py` (3 defines)
- Modify: `backend/src/cellar/interface/app.py:275-285` (include router)
- Modify: `backend/tests/api/conftest.py:59-153` (include router)
- Test: `backend/tests/api/test_kiosk_devices.py`

**Interfaces:**
- Produces:
  - `CreateKioskDevice(uow, repo, dispatcher)` — `__call__(CreateKioskDeviceCommand{workspace_id, org_id, name}, auth) -> Result[CreatedKioskDevice, DomainError]` where `CreatedKioskDevice{device: KioskDevice, token: str}` (token = plaintext, returned ONCE).
  - `ListKioskDevices(uow, repo)` — `__call__(ListKioskDevicesQuery{workspace_id}, auth) -> Result[list[KioskDevice], DomainError]`.
  - `RevokeKioskDevice(uow, repo, dispatcher)` — `__call__(RevokeKioskDeviceCommand{workspace_id, device_id}, auth) -> Result[KioskDevice, DomainError]`.
  - Routes: `POST /api/v1/kiosk-devices` (201, `KioskDeviceCreatedResponse` = device fields + `token`), `GET /api/v1/kiosk-devices` (`list[KioskDeviceResponse]`), `POST /api/v1/kiosk-devices/{device_id}:revoke` (`KioskDeviceResponse`). All admin-only (guard in use case). Task 8 consumes the create endpoint in its test setup; Task 10 consumes all three.

- [ ] **Step 1: Use cases** (`application/inventory/kiosk_devices.py`) — full file:

```python
"""KioskDevice admin use cases — create (token minted once), list, revoke (spec §4.5, §9)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_admin,
    require_authenticated,
    require_same_workspace,
)
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.kiosk_device import KioskDevice
from cellar.domain.inventory.repository import KioskDeviceRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError

KIOSK_TOKEN_BYTES = 32


@dataclass(frozen=True)
class CreateKioskDeviceCommand:
    workspace_id: uuid.UUID
    org_id: uuid.UUID
    name: str


@dataclass(frozen=True)
class CreatedKioskDevice:
    """The one and only carrier of the plaintext token."""

    device: KioskDevice
    token: str


@dataclass(frozen=True)
class ListKioskDevicesQuery:
    workspace_id: uuid.UUID


@dataclass(frozen=True)
class RevokeKioskDeviceCommand:
    workspace_id: uuid.UUID
    device_id: uuid.UUID


def hash_kiosk_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class CreateKioskDevice:
    def __init__(self, uow: UnitOfWork, repo: KioskDeviceRepository, dispatcher) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: CreateKioskDeviceCommand, auth: AuthContext | None = None
    ) -> Result[CreatedKioskDevice, DomainError]:
        require_authenticated(auth)  # created_by attribution — before role guard
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        assert auth is not None
        token = secrets.token_urlsafe(KIOSK_TOKEN_BYTES)
        async with self._uow:
            if await self._repo.find_by_name(input.workspace_id, input.name.strip()):
                return Failure(
                    ConflictError(f"A kiosk device named '{input.name.strip()}' already exists")
                )
            device = KioskDevice.create(
                workspace_id=input.workspace_id,
                org_id=input.org_id,
                name=input.name,
                token_hash=hash_kiosk_token(token),
                created_by=auth.user_id,
            )
            await self._repo.save(device)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(CreatedKioskDevice(device=device, token=token))


class ListKioskDevices:
    def __init__(self, uow: UnitOfWork, repo: KioskDeviceRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, input: ListKioskDevicesQuery, auth: AuthContext | None = None
    ) -> Result[list[KioskDevice], DomainError]:
        require_authenticated(auth)
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            return Success(await self._repo.find_by_workspace(input.workspace_id))


class RevokeKioskDevice:
    def __init__(self, uow: UnitOfWork, repo: KioskDeviceRepository, dispatcher) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: RevokeKioskDeviceCommand, auth: AuthContext | None = None
    ) -> Result[KioskDevice, DomainError]:
        require_authenticated(auth)
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            device = await self._repo.find_by_id_in_workspace(
                input.workspace_id, input.device_id
            )
            if device is None:
                return Failure(NotFoundError("Kiosk device"))
            device.revoke()
            await self._repo.save(device)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(device)
```

(Match `UnitOfWork`/dispatcher import paths and the dispatcher's type annotation to `application/inventory/plate_loans.py`'s imports. Match `NotFoundError`/`ConflictError` constructor args to house usage.)

- [ ] **Step 2: Routes** (`interface/routes/kiosk_devices.py`):

```python
"""Kiosk-device admin routes — token minted once at create, never re-shown."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.inventory.kiosk_devices import (
    CreateKioskDeviceCommand,
    ListKioskDevicesQuery,
    RevokeKioskDeviceCommand,
)
from cellar.domain.inventory.kiosk_device import KioskDevice
from cellar.interface.dependencies import (
    AuthDep,
    CreateKioskDeviceDep,
    ListKioskDevicesDep,
    RevokeKioskDeviceDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/kiosk-devices", tags=["kiosk-devices"])


class CreateKioskDeviceBody(BaseModel):
    org_id: uuid.UUID
    name: str


class KioskDeviceResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    is_active: bool
    last_seen_at: datetime | None
    created_at: datetime

    @classmethod
    def from_domain(cls, d: KioskDevice) -> "KioskDeviceResponse":
        return cls(
            id=d.id,
            org_id=d.org_id,
            name=d.name,
            is_active=d.is_active,
            last_seen_at=d.last_seen_at,
            created_at=d.created_at,
        )


class KioskDeviceCreatedResponse(KioskDeviceResponse):
    token: str  # shown once; only the sha256 hash is stored


@router.post("", response_model=KioskDeviceCreatedResponse, status_code=201)
async def create_kiosk_device(
    body: CreateKioskDeviceBody, auth: AuthDep, uc: CreateKioskDeviceDep
) -> KioskDeviceCreatedResponse:
    command = CreateKioskDeviceCommand(
        workspace_id=auth.workspace_id, org_id=body.org_id, name=body.name
    )
    created = result_to_response(await uc(command, auth=auth))
    base = KioskDeviceResponse.from_domain(created.device)
    return KioskDeviceCreatedResponse(**base.model_dump(), token=created.token)


@router.get("", response_model=list[KioskDeviceResponse])
async def list_kiosk_devices(auth: AuthDep, uc: ListKioskDevicesDep) -> list[KioskDeviceResponse]:
    devices = result_to_response(
        await uc(ListKioskDevicesQuery(workspace_id=auth.workspace_id), auth=auth)
    )
    return [KioskDeviceResponse.from_domain(d) for d in devices]


@router.post("/{device_id}:revoke", response_model=KioskDeviceResponse)
async def revoke_kiosk_device(
    device_id: uuid.UUID, auth: AuthDep, uc: RevokeKioskDeviceDep
) -> KioskDeviceResponse:
    command = RevokeKioskDeviceCommand(workspace_id=auth.workspace_id, device_id=device_id)
    device = result_to_response(await uc(command, auth=auth))
    return KioskDeviceResponse.from_domain(device)
```

- [ ] **Step 3: Wire DI + deps + routers.** `infrastructure/di/_inventory.py` (mirror the loans block):

```python
    def _create_kiosk_device(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateKioskDevice(uow, SQLAlchemyKioskDeviceRepository(uow), c[EventDispatcher])

    def _list_kiosk_devices(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListKioskDevices(uow, SQLAlchemyKioskDeviceRepository(uow))

    def _revoke_kiosk_device(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RevokeKioskDevice(uow, SQLAlchemyKioskDeviceRepository(uow), c[EventDispatcher])

    container.define(CreateKioskDevice, _create_kiosk_device)
    container.define(ListKioskDevices, _list_kiosk_devices)
    container.define(RevokeKioskDevice, _revoke_kiosk_device)
```

`interface/dependencies/_inventory.py`: `CreateKioskDeviceDep = Annotated[CreateKioskDevice, Depends(_get_use_case(CreateKioskDevice))]` (+ List/Revoke), added to `__all__`. `app.py`: import + `app.include_router(kiosk_devices_router)` in the plate block. `tests/api/conftest.py::_create_test_app`: same include.

- [ ] **Step 4: API tests** (`tests/api/test_kiosk_devices.py`) — matrix: (1) admin create → 201, token present (len > 30), response has no `token_hash`; (2) list shows the device with `last_seen_at: None` and NO token field; (3) duplicate name → 409; (4) `editor_client` create → 403, `viewer_client` list → 403; (5) revoke → `is_active` false; (6) revoke again → 200 (idempotent); (7) create for any org id succeeds (org existence not validated — FE picker constrains; document with a comment). Write the file mirroring `test_plate_loans.py` fixtures/imports.

- [ ] **Step 5: Run** — `uv run pytest tests/api/test_kiosk_devices.py -q`. Expected: PASS.
- [ ] **Step 6: Commit** — `git commit -m "feat(inventory): kiosk device admin API (create shows token once, list, revoke)" -- backend/src/cellar backend/tests`

---

### Task 8: Kiosk scan/confirm endpoints (token-authed, Sentinel-excluded)

**Files:**
- Create: `backend/src/cellar/application/inventory/kiosk.py`
- Create: `backend/src/cellar/interface/routes/kiosk.py`
- Modify: `backend/src/cellar/interface/app.py:196-200` (exclude_paths) + router include
- Modify: `backend/src/cellar/interface/dependencies/_inventory.py`, `backend/src/cellar/infrastructure/di/_inventory.py`
- Modify: `backend/tests/api/conftest.py` (include router)
- Test: `backend/tests/api/test_kiosk.py`

**Interfaces:**
- Consumes: `resolve_barcode` (`application/inventory/barcode_resolution.py` — module docstring already promises this reuse); `PlateLoanRepository.find_by_workspace(ws, status="open", plate_id=…)`; `KioskDeviceRepository.find_active_by_token_hash` / `touch_last_seen`; `loan.confirm_checkout([id])` / `loan.confirm_return([id])`; Task 7's create endpoint (test setup).
- Produces:
  - `ResolveScan(uow, device_repo, plate_repo, loan_repo)` — `__call__(ResolveScanQuery{token, barcode}) -> Result[KioskScanResult, DomainError]`, `KioskScanResult{plate: RegisteredPlate, loan: PlateLoan, item: LoanItem, action: str}` with `action ∈ {"checkout","return"}`.
  - `ConfirmScan(uow, device_repo, loan_repo, dispatcher)` — `__call__(ConfirmScanCommand{token, loan_id, item_id}) -> Result[KioskConfirmResult, DomainError]`, `KioskConfirmResult{loan_id, item_id, new_status: str}`.
  - Routes `POST /api/v1/kiosk/scan` + `POST /api/v1/kiosk/confirm`, header `X-Kiosk-Token`, NO `AuthDep`. Response `KioskScanResponse{plate_id, barcode, plate_label, loan_id, item_id, item_status, action, borrower_org_id, borrower_org_name: str | None, due_date: date | None}`; `KioskConfirmResponse{loan_id, item_id, new_status}`.
- **Recorded decisions** (carry into the spec sync note in Task 14): kiosk auth failures map to 403 (`AuthorizationError` — no 401 in the house error map); kiosk confirm is allowed regardless of the owner org's `confirmation` mode (the device is org-issued authority; policy modes shape the UI flow, not the device's capability); kiosk transitions reuse the existing batch events with **no actor field** (parity with admin confirm — attribution = device `last_seen_at` + structlog request logs); wrong-org and unknown plates/loans are indistinguishable 404s (no existence leak to devices).

- [ ] **Step 1: Use cases** (`application/inventory/kiosk.py`) — full file:

```python
"""Kiosk scan/confirm use cases — device-token principal, no user session (spec §9, §10).

The X-Kiosk-Token header is the ONLY credential: `_authenticate_device`
replaces the require_* guard stack. A device sees and acts on exactly its
own org's plates; anything else is an indistinguishable 404.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.inventory.barcode_resolution import resolve_barcode
from cellar.application.inventory.kiosk_devices import hash_kiosk_token
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.inventory.enums import LoanItemStatus
from cellar.domain.inventory.kiosk_device import KioskDevice
from cellar.domain.inventory.plate_loan import LoanItem, PlateLoan
from cellar.domain.inventory.registered_plate import RegisteredPlate
from cellar.domain.inventory.repository import (
    KioskDeviceRepository,
    PlateLoanRepository,
    RegisteredPlateRepository,
)
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConflictError,
    DomainError,
    NotFoundError,
)

KIOSK_ACTION_BY_STATUS: dict[LoanItemStatus, str] = {
    LoanItemStatus.APPROVED: "checkout",
    LoanItemStatus.RETURN_PENDING: "return",
}


@dataclass(frozen=True)
class ResolveScanQuery:
    token: str
    barcode: str


@dataclass(frozen=True)
class KioskScanResult:
    plate: RegisteredPlate
    loan: PlateLoan
    item: LoanItem
    action: str


@dataclass(frozen=True)
class ConfirmScanCommand:
    token: str
    loan_id: uuid.UUID
    item_id: uuid.UUID


@dataclass(frozen=True)
class KioskConfirmResult:
    loan_id: uuid.UUID
    item_id: uuid.UUID
    new_status: str


async def _authenticate_device(repo: KioskDeviceRepository, token: str) -> KioskDevice:
    if not token:
        raise AuthorizationError("Missing kiosk token")
    device = await repo.find_active_by_token_hash(hash_kiosk_token(token))
    if device is None:
        raise AuthorizationError("Invalid or revoked kiosk token")
    return device


class ResolveScan:
    """Barcode → pending loan item + which confirm action applies."""

    def __init__(
        self,
        uow: UnitOfWork,
        device_repo: KioskDeviceRepository,
        plate_repo: RegisteredPlateRepository,
        loan_repo: PlateLoanRepository,
    ) -> None:
        self._uow = uow
        self._device_repo = device_repo
        self._plate_repo = plate_repo
        self._loan_repo = loan_repo

    async def __call__(self, input: ResolveScanQuery) -> Result[KioskScanResult, DomainError]:
        async with self._uow:
            device = await _authenticate_device(self._device_repo, input.token)
            plate = await resolve_barcode(
                self._plate_repo, device.workspace_id, input.barcode
            )
            if plate is None or plate.owner_org_id != device.org_id:
                # Foreign-org plates are invisible to a device — same 404 as unknown.
                return Failure(NotFoundError(f"Plate '{input.barcode.strip()}'"))
            loans = await self._loan_repo.find_by_workspace(
                device.workspace_id, status="open", plate_id=plate.id
            )
            hit = next(
                (
                    (loan, item)
                    for loan in loans
                    for item in loan.items
                    if item.plate_id == plate.id and item.status in KIOSK_ACTION_BY_STATUS
                ),
                None,
            )
            if hit is None:
                return Failure(
                    ConflictError(f"No pending kiosk action for plate '{plate.barcode}'")
                )
            loan, item = hit
            await self._device_repo.touch_last_seen(device.id)
            await self._uow.commit()
        return Success(
            KioskScanResult(
                plate=plate, loan=loan, item=item, action=KIOSK_ACTION_BY_STATUS[item.status]
            )
        )


class ConfirmScan:
    """Drive APPROVED→CHECKED_OUT or RETURN_PENDING→RETURNED for one item."""

    def __init__(
        self,
        uow: UnitOfWork,
        device_repo: KioskDeviceRepository,
        loan_repo: PlateLoanRepository,
        dispatcher,
    ) -> None:
        self._uow = uow
        self._device_repo = device_repo
        self._loan_repo = loan_repo
        self._dispatcher = dispatcher

    async def __call__(self, input: ConfirmScanCommand) -> Result[KioskConfirmResult, DomainError]:
        async with self._uow:
            device = await _authenticate_device(self._device_repo, input.token)
            loan = await self._loan_repo.find_by_id_in_workspace(
                device.workspace_id, input.loan_id
            )
            if loan is None or loan.owner_org_id != device.org_id:
                return Failure(NotFoundError("Loan"))
            item = next((i for i in loan.items if i.id == input.item_id), None)
            if item is None:
                return Failure(NotFoundError("Loan item"))
            action = KIOSK_ACTION_BY_STATUS.get(item.status)
            if action is None:
                return Failure(
                    ConflictError(
                        f"Item is '{item.status.value}' — nothing for a kiosk to confirm"
                    )
                )
            if action == "checkout":
                loan.confirm_checkout([input.item_id])
            else:
                loan.confirm_return([input.item_id])
            await self._device_repo.touch_last_seen(device.id)
            await self._loan_repo.save(loan)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(
            KioskConfirmResult(
                loan_id=loan.id, item_id=item.id, new_status=item.status.value
            )
        )
```

(Match the `RegisteredPlate` import path and dispatcher annotation to the loans module. `LoanItem`/`PlateLoan` import from wherever `plate_loan.py` exports them.)

- [ ] **Step 2: Routes** (`interface/routes/kiosk.py`):

```python
"""Kiosk endpoints — X-Kiosk-Token authed, excluded from Sentinel middleware.

The org directory is display-data only: a Sentinel outage must never block
a physical handout, so name resolution is best-effort.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Header
from pydantic import BaseModel

from cellar.application.inventory.kiosk import ConfirmScanCommand, ResolveScanQuery
from cellar.interface.dependencies import (
    ConfirmScanDep,
    OrgDirectoryDep,
    ResolveScanDep,
)
from cellar.interface.error_handlers import result_to_response

router = APIRouter(prefix="/api/v1/kiosk", tags=["kiosk"])

KioskTokenHeader = Annotated[str | None, Header(alias="X-Kiosk-Token")]


class KioskScanBody(BaseModel):
    barcode: str


class KioskScanResponse(BaseModel):
    plate_id: uuid.UUID
    barcode: str
    plate_label: str
    loan_id: uuid.UUID
    item_id: uuid.UUID
    item_status: str
    action: str  # "checkout" | "return"
    borrower_org_id: uuid.UUID
    borrower_org_name: str | None
    due_date: date | None


class KioskConfirmBody(BaseModel):
    loan_id: uuid.UUID
    item_id: uuid.UUID


class KioskConfirmResponse(BaseModel):
    loan_id: uuid.UUID
    item_id: uuid.UUID
    new_status: str


@router.post("/scan", response_model=KioskScanResponse)
async def kiosk_scan(
    body: KioskScanBody,
    uc: ResolveScanDep,
    directory: OrgDirectoryDep,
    x_kiosk_token: KioskTokenHeader = None,
) -> KioskScanResponse:
    result = result_to_response(
        await uc(ResolveScanQuery(token=x_kiosk_token or "", barcode=body.barcode))
    )
    borrower_org_name: str | None = None
    try:
        orgs = await directory.list_orgs()
        borrower_org_name = next(
            (o.name for o in orgs if o.id == result.loan.borrower_org_id), None
        )
    except Exception:  # noqa: BLE001 — directory outage must not block the kiosk
        borrower_org_name = None
    return KioskScanResponse(
        plate_id=result.plate.id,
        barcode=result.plate.barcode,
        plate_label=result.plate.plate_label,
        loan_id=result.loan.id,
        item_id=result.item.id,
        item_status=result.item.status.value,
        action=result.action,
        borrower_org_id=result.loan.borrower_org_id,
        borrower_org_name=borrower_org_name,
        due_date=result.loan.due_date,
    )


@router.post("/confirm", response_model=KioskConfirmResponse)
async def kiosk_confirm(
    body: KioskConfirmBody,
    uc: ConfirmScanDep,
    x_kiosk_token: KioskTokenHeader = None,
) -> KioskConfirmResponse:
    result = result_to_response(
        await uc(
            ConfirmScanCommand(
                token=x_kiosk_token or "", loan_id=body.loan_id, item_id=body.item_id
            )
        )
    )
    return KioskConfirmResponse(
        loan_id=result.loan_id, item_id=result.item_id, new_status=result.new_status
    )
```

(`OrgDirectoryDep` import — it lives in `interface/dependencies/_core.py` and is re-exported; if the route uses `plate.plate_label` under a different domain attribute name, mirror the plates route serializer.)

- [ ] **Step 3: Exclude from Sentinel + wire.** `app.py:196-200`:

```python
    sentinel.protect(
        app,
        # /api/v1/kiosk uses X-Kiosk-Token device auth (spec §10). SDK match is
        # exact-or-prefix-with-slash-boundary, so /api/v1/kiosk-devices (admin,
        # session-authed) is NOT excluded.
        exclude_paths=["/health", "/version", "/docs", "/openapi.json", "/api/v1/kiosk"],
    )
```

Include `kiosk_router` in `app.py` + conftest. DI defines for `ResolveScan`/`ConfirmScan` (mirror the loans factories; ResolveScan takes device+plate+loan repos, no dispatcher; ConfirmScan takes device+loan repos + dispatcher). Deps aliases `ResolveScanDep`/`ConfirmScanDep`.

- [ ] **Step 4: API tests** (`tests/api/test_kiosk.py`). Setup helper: admin creates a device for `AUTH_ORG_ID` (capturing the token), registers a plate with barcode `"000123"` owned by `AUTH_ORG_ID`, requests a loan as `editor_client_own_org`, approves it (admin). Matrix — all against `client`'s app but sending only the `X-Kiosk-Token` header (no auth override needed; the routes never use AuthDep):
  1. scan exact barcode → 200, `action == "checkout"`, `item_status == "approved"`, `due_date` echoed;
  2. scan `"123"` → 200 same plate (§7 zfill chain through the shared resolver);
  3. scan with no/garbage token → 403; after `:revoke` (fresh device) → 403;
  4. scan a plate owned by `OTHER_ORG_ID` → 404 (foreign org invisible);
  5. scan unknown barcode → 404; scan a plate with no pending item → 409;
  6. confirm the approved item → 200 `new_status == "checked_out"`; GET the loan as a user → item checked_out;
  7. confirm again → 409 (`checked_out` not confirmable);
  8. borrower requests return (`items:request-return`), kiosk confirm → `new_status == "returned"` AND the loan auto-closes (GET loan → `status == "closed"`) — proves both directions + `_refresh_status`;
  9. device list (admin) now shows `last_seen_at` not null;
  10. borrower_org_name: default stub directory has no `AUTH_ORG_ID` entry → assert `borrower_org_name is None`; then override `api_app.dependency_overrides[get_org_directory]` locally with a stub whose list includes `OrgSummary(id=AUTH_ORG_ID, slug="tamu", name="Texas A&M", is_public=True)` → assert the name resolves.

- [ ] **Step 5: Run** — `uv run pytest tests/api/test_kiosk.py tests/api/test_plate_loans.py -q`. Expected: PASS.
- [ ] **Step 6: Commit** — `git commit -m "feat(inventory): kiosk scan/confirm endpoints with X-Kiosk-Token device auth" -- backend/src/cellar backend/tests`

---

### Task 9: Plate-insights read model + route

**Files:**
- Create: `backend/src/cellar/application/inventory/plate_insights_reader.py`
- Create: `backend/src/cellar/application/inventory/get_plate_insights.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_insights_reader.py`
- Modify: `backend/src/cellar/interface/routes/registered_plates.py` (route between `GET ""` at :210 and `GET /{plate_id}` at :245 — **static before dynamic or FastAPI captures `plate_id="insights"`**)
- Modify: DI + deps (`_inventory.py` ×2)
- Test: `backend/tests/integration/inventory/test_plate_insights_reader.py`, `backend/tests/api/test_plate_insights.py`

**Interfaces:**
- Produces (application Protocol, mirrors `InventorySummaryReader`):

```python
@dataclass(frozen=True)
class CountBucket:
    key: str
    count: int

@dataclass(frozen=True)
class LocationCount:
    location_id: uuid.UUID | None   # None = unassigned bucket
    name: str                       # "Unassigned" for None
    count: int

@dataclass(frozen=True)
class GroupSize:
    group_id: uuid.UUID
    name: str
    count: int

@dataclass(frozen=True)
class WeeklyLoanActivity:
    week_start: date                # Monday (ISO), matches Postgres date_trunc('week')
    requested: int
    returned: int

@dataclass(frozen=True)
class PlateInsightsData:
    total_plates: int
    by_status: list[CountBucket]
    by_type: list[CountBucket]
    by_location: list[LocationCount]
    group_sizes: list[GroupSize]            # desc by count, ALL groups with ≥1 plate
    loan_activity_weekly: list[WeeklyLoanActivity]  # exactly 12 zero-filled buckets, oldest first
    open_loans: int
    overdue_count: int

@runtime_checkable
class PlateInsightsReader(Protocol):
    async def get_insights(
        self, workspace_id: uuid.UUID, org_id: uuid.UUID
    ) -> PlateInsightsData: ...
```

- `GetPlateInsights(uow, visibility, reader)` — `__call__(GetPlateInsightsQuery{workspace_id, org_id: UUID | None}, auth) -> Result[tuple[uuid.UUID, PlateInsightsData], DomainError]` (returns the resolved org_id + data). Org defaulting + private-org 403 mirror `GetGroupTree` (plate_groups.py:425-436) EXACTLY: default `org_id := auth.org_id`, `ValidationError` if neither, `AuthorizationError("This organization's plates are private")` if `org_id in excluded`.
- Route: `GET /api/v1/plates/insights?org_id=` → `PlateInsightsResponse{org_id, total_plates, open_loans, overdue_count, by_status: [{key,count}], by_type, by_location: [{location_id,name,count}], group_sizes: [{group_id,name,count}], loan_activity_weekly: [{week_start,requested,returned}]}`. Task 11 consumes the generated type.

- [ ] **Step 1: Write the reader integration test first** (`test_plate_insights_reader.py`, session fixtures from the sibling file). Seed directly via ORM models: org A — 3 plates (2 `stored`, 1 `depleted`; 2 `assay`, 1 `mother`; 2 in a storage location, 1 unassigned; 2 in a group "Vendor set"), 1 open loan `owner_org_id=A` with `due_date = date.today() - timedelta(days=1)` and one item `checked_out`, plus 1 item `returned` with `status_changed_at = now`; org B — 1 plate, 1 loan (noise). Assert for org A: `total_plates == 3`; `by_status` = {stored: 2, depleted: 1}; `by_type` = {assay: 2, mother: 1}; `by_location` has the named location with 2 and `("Unassigned", 1)` with `location_id is None`; `group_sizes == [GroupSize(g, "Vendor set", 2)]`; `open_loans == 1`; `overdue_count == 1`; `len(loan_activity_weekly) == 12`, last bucket `requested == 1, returned == 1`, all earlier buckets zero; org B's rows never leak. Run → FAIL (module missing).

- [ ] **Step 2: Implement the SQLAlchemy reader** (own `session_factory`, mirroring `protocol_stats_reader.py`). Queries:

```python
    async def get_insights(self, workspace_id, org_id) -> PlateInsightsData:
        ws = workspace_id
        async with self._session_factory() as session:
            plate_where = (
                RegisteredPlateModel.workspace_id == ws,
                RegisteredPlateModel.owner_org_id == org_id,
            )
            total = (
                await session.execute(select(func.count()).where(*plate_where))
            ).scalar_one()

            by_status = await self._buckets(session, RegisteredPlateModel.status, plate_where)
            by_type = await self._buckets(session, RegisteredPlateModel.plate_type, plate_where)

            loc_stmt = (
                select(
                    RegisteredPlateModel.storage_location_id,
                    StorageLocationModel.name,
                    func.count(),
                )
                .select_from(RegisteredPlateModel)
                .outerjoin(
                    StorageLocationModel,
                    RegisteredPlateModel.storage_location_id == StorageLocationModel.id,
                )
                .where(*plate_where)
                .group_by(RegisteredPlateModel.storage_location_id, StorageLocationModel.name)
                .order_by(func.count().desc())
            )
            by_location = [
                LocationCount(location_id=row[0], name=row[1] or "Unassigned", count=row[2])
                for row in (await session.execute(loc_stmt)).all()
            ]

            group_stmt = (
                select(RegisteredPlateModel.group_id, PlateGroupModel.name, func.count())
                .join(PlateGroupModel, RegisteredPlateModel.group_id == PlateGroupModel.id)
                .where(*plate_where)
                .group_by(RegisteredPlateModel.group_id, PlateGroupModel.name)
                .order_by(func.count().desc())
            )
            group_sizes = [
                GroupSize(group_id=row[0], name=row[1], count=row[2])
                for row in (await session.execute(group_stmt)).all()
            ]

            loan_where = (
                PlateLoanModel.workspace_id == ws,
                PlateLoanModel.owner_org_id == org_id,
            )
            open_loans = (
                await session.execute(
                    select(func.count()).where(*loan_where, PlateLoanModel.status == "open")
                )
            ).scalar_one()
            overdue = (
                await session.execute(
                    select(func.count()).where(
                        *loan_where,
                        PlateLoanModel.status == "open",
                        PlateLoanModel.due_date < func.current_date(),
                    )
                )
            ).scalar_one()

            weekly = await self._weekly_activity(session, ws, org_id)

        return PlateInsightsData(...)
```

`_buckets`: `select(col, func.count()).where(*where).group_by(col).order_by(func.count().desc())` → `[CountBucket(key=row[0], count=row[1])]`. `_weekly_activity`: window = 12 ISO weeks including current (`monday = today - timedelta(days=today.weekday())`; `window_start = monday - timedelta(weeks=11)` as tz-aware datetime); requested per week from `PlateLoanModel.created_at`, returned per week from `LoanItemModel.status_changed_at` joined to `PlateLoanModel` (items have NO workspace column — the join IS the scoping) with `LoanItemModel.status == "returned"`; both `func.date_trunc("week", …)` grouped; Python zero-fills the 12 buckets oldest-first (`.date()` the truncated datetimes). Overdue uses the DB's `current_date` (server TZ) — note in the docstring. Import `PlateGroupModel`/`StorageLocationModel` from their actual modules (grep).

- [ ] **Step 3: Use case + route + DI.** `get_plate_insights.py` — full use case (guards mirror `GetGroupTree`, plate_groups.py:425-436; the excluded-check runs inside `async with self._uow` because the policy repo is uow-bound, while the reader opens its own session AFTER the gate):

```python
"""GetPlateInsights — org-scoped dashboard counts behind the S2 privacy gate."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_same_workspace,
    require_workspace_role,
)
from cellar.application.inventory.plate_insights_reader import (
    PlateInsightsData,
    PlateInsightsReader,
)
from cellar.application.inventory.plate_visibility import PlateVisibilityService
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import AuthorizationError, DomainError, ValidationError


@dataclass(frozen=True)
class GetPlateInsightsQuery:
    workspace_id: uuid.UUID
    org_id: uuid.UUID | None = None


class GetPlateInsights:
    def __init__(
        self,
        uow: UnitOfWork,
        visibility: PlateVisibilityService,
        reader: PlateInsightsReader,
    ) -> None:
        self._uow = uow
        self._visibility = visibility
        self._reader = reader

    async def __call__(
        self, input: GetPlateInsightsQuery, auth: AuthContext | None = None
    ) -> Result[tuple[uuid.UUID, PlateInsightsData], DomainError]:
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

        data = await self._reader.get_insights(input.workspace_id, org_id)
        return Success((org_id, data))
```

Route in `registered_plates.py` (position per Files note):

```python
@router.get("/insights", response_model=PlateInsightsResponse)
async def get_plate_insights(
    auth: AuthDep, uc: GetPlateInsightsDep, org_id: uuid.UUID | None = None
) -> PlateInsightsResponse:
    """Org-scoped plate/loan insight counts for the dashboard (spec §9, §11)."""
    query = GetPlateInsightsQuery(workspace_id=auth.workspace_id, org_id=org_id)
    resolved_org, data = result_to_response(await uc(query, auth=auth))
    return PlateInsightsResponse.from_data(resolved_org, data)
```

Response models nested as in the Interfaces block (each with a `from_*` or inline construction; `CountBucket → {key, count}`). DI: two-define reader pattern (`container.define(PlateInsightsReader, lambda c: SQLAlchemyPlateInsightsReader(c[async_sessionmaker]))`) + `GetPlateInsights` factory with uow + fresh `PlateVisibilityService(SQLAlchemyOrgPlatePolicyRepository(uow))` + `c[PlateInsightsReader]`; deps alias `GetPlateInsightsDep`.

- [ ] **Step 4: API tests** (`test_plate_insights.py`): (1) shape — seed a plate + loan, GET → 200, all nine top-level fields present, `org_id` echoes caller org when param omitted; (2) explicit `org_id` scoping — org B's counts don't include org A's plates; (3) private org → 403 for non-members INCLUDING admin (copy the `_set_plates_private` helper pattern from `test_plate_groups.py:32-37,168-181`), member still 200; (4) orgless caller (`_client_as(..., org_id=None)`) without param → 422; (5) `/insights` does NOT shadow `GET /{plate_id}` (fetch a real plate by id still 200 — route-order canary).

- [ ] **Step 5: Run** — `uv run pytest tests/integration/inventory/test_plate_insights_reader.py tests/api/test_plate_insights.py tests/api/test_registered_plates.py -q`. Expected: PASS.
- [ ] **Step 6: Commit** — `git commit -m "feat(inventory): per-org plate insights read model + /plates/insights route" -- backend/src/cellar backend/tests`

---

### Task 10: FE kiosk-device admin page

**Files:**
- Regen: `frontend/src/shared/lib/api/model/` (orval — picks up kiosk-devices, kiosk, insights from Tasks 7-9; Appendix A)
- Create: `frontend/src/features/workspace-config/hooks/use-kiosk-devices.ts`
- Create: `frontend/src/features/workspace-config/components/kiosk-device-admin.tsx`
- Create: `frontend/src/app/(dashboard)/admin/kiosk-devices/page.tsx`
- Modify: `frontend/src/shared/lib/navigation.ts:67-118` (Organization group children)
- Test: `frontend/src/features/workspace-config/components/kiosk-device-admin.test.tsx`

**Interfaces:**
- Consumes: generated `KioskDeviceResponse` / `KioskDeviceCreatedResponse` (alias, never hand-roll); `useOrgs` (org names — no UUIDs in the UI); `createCrudHooks` (`@/shared/hooks/create-crud-hooks`) for list/create; hand-written revoke mutation (colon-verb POST, mirroring `useDeletePlateGroup`'s shape).
- Produces: `/admin/kiosk-devices` page — table (Name / Organization / Status / Last seen / row action Revoke), Add dialog (name + org Select), **token-reveal dialog shown exactly once after create** (monospace token + Copy button via `navigator.clipboard.writeText` + `showSuccess("Token copied")` + warning copy "This token is shown only once — store it in the scanner now."), bespoke revoke-confirm dialog (button label "Revoke", NOT the shared delete dialog).

- [ ] **Step 1: Regen orval** (backend on :8000 per Appendix A): `pnpm generate:api`; review diff (new kiosk/insights types + nothing pruned).
- [ ] **Step 2: Hooks** (`use-kiosk-devices.ts`):

```ts
import type { KioskDeviceCreatedResponse, KioskDeviceResponse } from "@/shared/lib/api/model";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export type KioskDevice = KioskDeviceResponse;
export type CreatedKioskDevice = KioskDeviceCreatedResponse;

const KIOSK_DEVICES_KEY = ["kiosk-devices"];

const hooks = createCrudHooks<CreatedKioskDevice, { org_id: string; name: string }, never>({
  entityName: "Kiosk device",
  baseUrl: `${API_V1}/kiosk-devices`,
  queryKey: KIOSK_DEVICES_KEY,
});

export const useKioskDevices = hooks.useList;
export const useCreateKioskDevice = hooks.useCreate; // mutateAsync resolves to {…device, token}

export function useRevokeKioskDevice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId }: { deviceId: string }) =>
      customInstance<KioskDevice>({
        url: `${API_V1}/kiosk-devices/${deviceId}:revoke`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KIOSK_DEVICES_KEY });
      showSuccess("Device revoked");
    },
  });
}
```

(If `createCrudHooks`' list typing fights the created-vs-list type split, type the CRUD entity as `KioskDevice` and hand-write the create mutation like the revoke one, returning `CreatedKioskDevice` — 10 lines either way; keep whichever compiles cleanly.)

- [ ] **Step 3: Component** (`kiosk-device-admin.tsx`), following `api-key-admin.tsx`'s skeleton (PageHeader + Add button, `SkeletonList` loading, bordered `Table`, `EmptyState variant="inline"`): org names resolved via `const orgName = (id: string) => orgs?.find((o) => o.id === id)?.name ?? "Unknown org"`; Status = `<Badge variant={d.is_active ? "secondary" : "outline"}>{d.is_active ? "Active" : "Revoked"}</Badge>`; Last seen = `d.last_seen_at ? formatDate(d.last_seen_at) : "Never"`. Create dialog: RHF + zod (`{ name: z.string().min(1).max(100), org_id: z.string().min(1) }`), org `Select` listing `useOrgs` by NAME. On `create.mutateAsync` success: close create dialog, `setIssued(created)` → token dialog:

```tsx
function TokenRevealDialog({ issued, onClose }: { issued: CreatedKioskDevice | null; onClose: () => void }) {
  return (
    <Dialog open={issued !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Device token for “{issued?.name}”</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          This token is shown only once — store it in the scanner now. Revoke the
          device to invalidate it.
        </p>
        <div className="flex items-center gap-2">
          <code
            className="flex-1 overflow-x-auto rounded-md border bg-muted px-3 py-2 font-mono text-sm"
            data-testid="kiosk-token"
          >
            {issued?.token}
          </code>
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              if (issued) {
                await navigator.clipboard.writeText(issued.token);
                showSuccess("Token copied");
              }
            }}
          >
            <Copy className="mr-2 h-4 w-4" />
            Copy
          </Button>
        </div>
        <DialogFooter>
          <Button onClick={onClose}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

Revoke: bespoke confirm `Dialog` (mirror api-key-admin's `DeleteDialog` shape) with destructive button labeled "Revoke"; hidden (not disabled) for already-revoked rows. Page wrapper `admin/kiosk-devices/page.tsx` (5-line convention). Nav: add `{ title: "Kiosk Devices", href: "/admin/kiosk-devices", icon: ScanLine }` to the Organization group's `children` (import `ScanLine` from `lucide-react`).

- [ ] **Step 4: Tests** (`kiosk-device-admin.test.tsx`, conventions from §10 of the FE patterns — mock `customInstance` URL-branched, local QueryClient wrapper, mock toast): (1) renders device rows with org name + "Never" last-seen; (2) create flow — fill name, pick org, submit → token dialog visible with the mocked token, closing it empties the reveal (token not re-shown); (3) revoke confirm fires `POST …:revoke`. Mock `navigator.clipboard` if the copy path is exercised.
- [ ] **Step 5: Run** — `/Users/sidx/Library/pnpm/pnpm test kiosk-device-admin` then full `pnpm test` + `pnpm lint` (exit codes). Expected: green.
- [ ] **Step 6: Commit** — `git commit -m "feat(frontend): kiosk device admin page with show-once token reveal" -- frontend/src`

---

### Task 11: FE insights tab on the plate-groups dashboard

**Files:**
- Create: `frontend/src/features/inventory/hooks/use-plate-insights.ts`
- Create: `frontend/src/features/inventory/components/plate-insights-panel.tsx`
- Modify: `frontend/src/features/inventory/components/plate-group-dashboard.tsx:83-155` (tabs)
- Test: `frontend/src/features/inventory/components/plate-insights-panel.test.tsx`

**Interfaces:**
- Consumes: generated `PlateInsightsResponse` (from Task 10's regen); `Plot`/`PlotProps` from `@/shared/lib/plotly` (SSR-disabled, `useResizeHandler`, `style={{width:"100%"}}`); `CHART_COLORS`/`CHART_AXIS`/`GROUP_PALETTE` from `@/shared/lib/chart-colors`; house layout conventions (height 350, `paper_bgcolor`/`plot_bgcolor: "transparent"`, `font.color: CHART_AXIS.label`, `gridcolor: CHART_AXIS.grid`, `bargap: 0.3`, `config={{ displayModeBar: false, responsive: true }}` — exemplar `activity-tab.tsx:170-215,528-534`); `useHashTab` (`@/shared/hooks/use-hash-tab`); shadcn `Tabs`.
- Produces: `usePlateInsights(orgId?: string)` → query keyed `["plate-insights", orgId]`, `GET /api/v1/plates/insights?org_id=`, enabled iff orgId; `<PlateInsightsPanel orgId={orgId} />`; dashboard gains `Tabs` — "Hierarchy" (existing tree + details, unchanged) / "Insights" (panel), org selector stays in the shared PageHeader, "New group" button rendered only on the Hierarchy tab.

- [ ] **Step 0: READ THE DATAVIZ SKILL FIRST** (implementer: invoke the `dataviz` skill before writing any chart code), plus `shared/lib/plotly.tsx` and `chart-colors.ts`. House rules win where they conflict with generic defaults.
- [ ] **Step 1: Hook** (`use-plate-insights.ts`):

```ts
import type { PlateInsightsResponse } from "@/shared/lib/api/model";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";

export type PlateInsights = PlateInsightsResponse;

export function usePlateInsights(orgId: string | undefined) {
  return useQuery({
    queryKey: ["plate-insights", orgId],
    queryFn: ({ signal }) =>
      customInstance<PlateInsights>({
        url: `${API_V1}/plates/insights`,
        method: "GET",
        params: { org_id: orgId as string },
        signal,
      }),
    enabled: !!orgId,
  });
}
```

- [ ] **Step 2: Panel** (`plate-insights-panel.tsx`). Structure: loading (`SkeletonList`), error (`text-destructive` line), empty (`total_plates === 0` → dashed-border empty state "No plates for this organization yet"), else:
  - **Stat tiles row** (`grid gap-4 sm:grid-cols-3`): Total plates / Open loans / Overdue — each a bordered card `rounded-md border bg-card p-4` with `text-2xl font-semibold` value + `text-sm text-muted-foreground` label; Overdue value gets `text-destructive` when `> 0`.
  - **Charts grid** (`grid gap-4 lg:grid-cols-2`), each chart in `rounded-md border bg-card p-4` with a `text-sm font-medium` title. Five `Plot`s sharing a `baseLayout` helper (house conventions above):
    1. *Plates by status* — vertical bar, `x: by_status.map(b => b.key)`, `marker.color: CHART_COLORS.primary`.
    2. *Plates by type* — vertical bar, `CHART_COLORS.purple`.
    3. *Loan activity (12 weeks)* — two bar traces (`Requested` = `CHART_COLORS.primary`, `Returned` = `CHART_COLORS.success`), `x: week_start`, `barmode: "group"`, horizontal legend at `y: -0.25`.
    4. *Storage occupancy* — horizontal bar (`orientation: "h"`, top 10 by count, `y` = names reversed so largest is on top), `CHART_COLORS.neutral`.
    5. *Top groups* — horizontal bar, top 10 of `group_sizes`, `CHART_COLORS.primaryLight`.
  - All numeric axes integer-ticked where sensible; categorical x uses `tickangle: -45` only when labels overflow.
- [ ] **Step 3: Tabs in the dashboard.** In `plate-group-dashboard.tsx` wrap the existing tree region (the `{error ? … : …}` block, L114-155) in `<Tabs value={tab} onValueChange={setTab}>` with `const [tab, setTab] = useHashTab("hierarchy")`; `TabsList` (Hierarchy / Insights) directly under the PageHeader; `TabsContent value="hierarchy"` = the existing block unchanged; `TabsContent value="insights"` = `<PlateInsightsPanel orgId={orgId ?? undefined} />`. Gate the "New group" header button with `{tab === "hierarchy" ? … : null}`. The org Select stays shared (switching org refreshes both tabs).
- [ ] **Step 4: Tests** (`plate-insights-panel.test.tsx`): mock `@/shared/lib/plotly` with `vi.mock("@/shared/lib/plotly", () => ({ Plot: (p: unknown) => <div data-testid="plot" /> }))`; URL-branch `customInstance` returning a fixture `PlateInsightsResponse`. Cases: (1) tiles render the three numbers (overdue styled destructive when > 0); (2) five plots render with data; (3) `total_plates: 0` fixture → empty state, zero plots; (4) no fetch when `orgId` undefined (`customInstance` not called).
- [ ] **Step 5: Run** — targeted then full FE suite + lint (exit codes). Expected: green (known ceiling: mocked `Plot` cannot catch Plotly layout/interaction issues — Task 13 covers visually).
- [ ] **Step 6: Commit** — `git commit -m "feat(frontend): insights tab with plate/loan charts on the plate-groups dashboard" -- frontend/src`

---

### Task 12: Tree polish — group-type colors, label clipping, keyboard a11y

**Files:**
- Create: `frontend/src/features/inventory/components/plate-group-tree-utils.ts`
- Modify: `frontend/src/features/inventory/components/plate-group-tree.tsx` (node renderer L79-115 + legend)
- Test: `frontend/src/features/inventory/components/plate-group-tree-utils.test.ts`

**Interfaces:**
- Produces (`plate-group-tree-utils.ts`):

```ts
import { CHART_COLORS, GROUP_PALETTE } from "@/shared/lib/chart-colors";

export const MAX_NODE_LABEL = 28;

/** Deterministic string hash → palette color; free-text group types get a
 * stable color across renders/sessions. Untyped groups stay neutral. */
export function groupTypeColor(groupType: string): string {
  if (!groupType) return CHART_COLORS.neutral;
  let hash = 5381;
  for (let i = 0; i < groupType.length; i++) {
    hash = (hash * 33) ^ groupType.charCodeAt(i);
  }
  return GROUP_PALETTE[Math.abs(hash) % GROUP_PALETTE.length];
}

export function truncateLabel(name: string, max: number = MAX_NODE_LABEL): string {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name;
}

/** Distinct group types present in the tree (first-seen order) for the legend. */
export function legendEntries(
  roots: PlateGroupNode[],
): { label: string; color: string }[] {
  const seen = new Set<string>();
  let hasUntyped = false;
  const entries: { label: string; color: string }[] = [];
  const stack = [...roots];
  while (stack.length > 0) {
    const node = stack.pop() as PlateGroupNode;
    const type = node.group_type ?? "";
    if (!type) hasUntyped = true;
    else if (!seen.has(type)) {
      seen.add(type);
      entries.push({ label: type, color: groupTypeColor(type) });
    }
    stack.push(...(node.children ?? []));
  }
  if (hasUntyped) entries.push({ label: "untyped", color: CHART_COLORS.neutral });
  return entries;
}
```

(Import `PlateGroupNode` from wherever the tree component gets it; if `children` is named differently on that type, mirror it.)
- Consumes: `GroupDatum.attributes.group_type` (already plumbed, `plate-group-tree.tsx:17-31`).

- [ ] **Step 1: Write utils tests first** (`plate-group-tree-utils.test.ts`): `groupTypeColor` is stable (same input twice), differs for `"vendor"` vs `"screening"`, returns neutral for `""`; `truncateLabel` passes short names through, truncates a 40-char name to 28 with a trailing `…`; `legendEntries` dedupes and appends the untyped entry only when an untyped group exists. Run → FAIL (module missing). Implement utils → PASS.
- [ ] **Step 2: Apply in the renderer** (`plate-group-tree.tsx`):
  - Circle: replace the selected/muted class fill with `style={{ fill: isSynthetic ? undefined : groupTypeColor(attrs.group_type) }}` and keep selection as a stroke ring: `className={isSelected ? "stroke-primary" : "stroke-border"} strokeWidth={isSelected ? 3 : 1}` (synthetic root keeps `fill-muted` class).
  - Labels: render `{truncateLabel(nodeDatum.name)}` and add `<title>{nodeDatum.name}</title>` inside the clickable `<g>` (native SVG tooltip restores the full name).
  - Keyboard a11y (the deferred "S5 dataviz/interaction pass" named by the two `biome-ignore` comments — REMOVE both comments): on the circle and the label `<g>`, add `role="button"`, `tabIndex={0}`, `onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); /* same handler as onClick */ } }}`.
  - Legend: above the tree container render `legendEntries(tree.roots)` as a `flex flex-wrap gap-3` row of `<span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"><span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />{label}</span>`; render nothing when there's ≤1 distinct type.
- [ ] **Step 3: Run** — full FE suite + `pnpm lint` (the removed biome-ignores must not resurface warnings — exit code check). Expected: green.
- [ ] **Step 4: Commit** — `git commit -m "feat(frontend): tree nodes colored by group type, truncated labels with tooltips, keyboard selection" -- frontend/src`

---

### Task 13: Runtime verification (rig)

**Files:** scratchpad only (`serve_verify.py`, Playwright walk script, screenshots). No repo changes except fixes for real defects found (each fixed at root + committed with pathspec).

Rig recipe: Appendix A (auth-stubbed real backend on :8000 vs real DB with the S3/S4 legacy seed — workspace `442df0cf-e618-4938-a089-80ae2f1e43e7` has SAC1+SAC2 (public org) + Sanofi (tamu) + 12 real plates; FE via `/Users/sidx/Library/pnpm/pnpm dev`; Playwright login per the repo `verify` skill).

- [ ] **Checklist** (screenshot each numbered item):
  1. Migration `uv run alembic upgrade head` against the dev DB succeeds (kiosk_devices exists).
  2. Plates list: as public-org admin, borrow a tamu-owned plate (request via UI), then "My org" filter shows it with its custody chip (deviation #5 closed live).
  3. Loans page: Approvals tab visible to the admin stub; a tamu-owned loan shows verb buttons (admin visibility fix); All tab still read-only.
  4. Plate Groups → Hierarchy: nodes colored by group type + legend; a long legacy set name is truncated with tooltip; Tab-key focuses a node and Enter selects it (details panel opens).
  5. Plate Groups → Insights: tiles + all five charts render for the seeded org; switching org selector refreshes; empty org shows the empty state.
  6. Admin → Kiosk Devices: create a device for the public org → token dialog shows once; Copy works; list shows Active/Never.
  7. Kiosk API (curl, no session): `POST /api/v1/kiosk/scan` with the token + a seeded barcode → checkout action; SHORT digit barcode resolves via zfill; `POST /api/v1/kiosk/confirm` → item checked_out visible in the Loans UI; request return in UI → kiosk confirm → loan closes.
  8. Revoke the device in the UI → same curl now 403.
  9. `GET /api/v1/plates/insights?org_id=<tamu>` with tamu private → 403 for public-org stub (curl); flip policy back.
  10. **Best-effort live check_action smoke:** against a REAL-Sentinel backend (`make` dev stack, real tokens minted per the dev-api-access recipe: two-token auth via Sentinel `/authz/resolve` with the backend service key), attempt a loan approve as the non-admin editor holding the `cellar:approve_loan` grant (granted 2026-08-13). Expected: 200 (grant works — FIRST live RoleClient round-trip) or a clean fail-closed 403 (report which). If token minting for that user isn't feasible headlessly, record "still unexercised against live Sentinel" in the ship notes — do not fake it.
- [ ] Fix-at-root anything found; re-run the affected checks; commit fixes individually.

---

### Task 14: Suites, docs sync, push, board

**Files:**
- Modify: `docs/superpowers/specs/2026-08-10-inventory-plate-org-loans-spec.md` (append S5 sync note)
- Modify: memory `project_plate_tracker_port.md` (S5 shipped + S6 handoff) — end of session
- Commit/push + `gh issue comment` on sidxz/cellar#71

- [ ] **Step 1: Full suites** — backend `uv run pytest -q` (expect: baseline 10 documented failures only, passed count > 3770) + `uv run lint-imports`; FE full `pnpm test` (> 1000 green) + `pnpm lint` exit 0; `uv run ruff check backend/src` if that's the house lint entry (mirror S4's Task 13 commands).
- [ ] **Step 2: Spec S5 sync note** — append to the spec (mirror the S4 note's format): kiosk auth = 403 not 401; kiosk confirm ignores `confirmation` mode (device = org authority); kiosk events carry no actor (parity with admin confirm; device attribution = last_seen + logs); `/plates/insights` returns ALL location/group rows (FE slices top 10); insights tab lives on the plate-groups page (one dashboard, spec §11's "new page" satisfied by the existing route); Task 13's check_action outcome; any further deviations found during execution. Also record: §11's plate-detail CODE128 barcode render remains UNSCHEDULED (not in §14-S5/S6 — note it so it rides with S6 polish or a later pass instead of silently dropping). Operator note: after deploy run migration 064; kiosk page (user-built) targets §10 contract with `X-Kiosk-Token`.
- [ ] **Step 3: Push + board** — push main; `gh issue comment 71 --repo sidxz/cellar --body "<S5 summary: shipped items, commit range, deviations, S6 = migration next>"`.
- [ ] **Step 4: Update memory** (`project_plate_tracker_port.md`): S5 shipped line (commit range, decisions), NEXT = S6 migration script (spec §12) — plan not yet written.

---

## Appendix A — auth-stubbed backend for regen + runtime verify

Proven S3/S4 recipe (memory). Write to scratchpad as `serve_verify.py`; run with `cd backend && uv run python <scratchpad>/serve_verify.py`:

```python
"""Serve the real app on :8000 with FakeAuth override + Sentinel middleware stripped."""
import os
import sys
import uuid

# Sentinel env must exist BEFORE importing the app (create_app eagerly configures) —
# copy the exact env block from backend/tests/api/conftest.py:11-18.
os.environ.setdefault("DATABASE_URL", "<dev DB url from root .env>")

sys.path.insert(0, "tests")  # for tests.fakes.fake_auth
from fakes.fake_auth import FakeAuth  # noqa: E402

from cellar.interface.app import create_app  # noqa: E402
from cellar.interface.dependencies import get_auth  # noqa: E402

app = create_app()
WS = uuid.UUID("442df0cf-e618-4938-a089-80ae2f1e43e7")  # dev workspace (S3/S4 seed)
PUBLIC_ORG = uuid.UUID("<public org id — query Sentinel /organizations or reuse S4 notes>")
stub = FakeAuth(role="admin", workspace_id=WS, org_id=PUBLIC_ORG)
app.dependency_overrides[get_auth] = lambda: stub

# Strip Sentinel middleware (module-name filter), keep CORS/RequestContext.
app.user_middleware = [
    m for m in app.user_middleware if "sentinel" not in str(getattr(m, "cls", "")).lower()
]
app.middleware_stack = None  # force rebuild

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, port=8000)
```

For orval regen only, any FakeAuth identity works (orval reads `/openapi.json`). For Task 13, swap `role`/`org_id` per check (e.g. an editor stub with `granted_actions=set()` to see denial paths). FE dev server: `cd frontend && /Users/sidx/Library/pnpm/pnpm dev`. Real-Sentinel checks (13.10) use the `make` dev stack instead, with tokens minted per the dev-api-access memory recipe.
