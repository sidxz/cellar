# S15 — Run plate ↔ inventory plate link — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An optional `registered_plate_id` on a run's plate, auto-resolved from the file's plate name at import, manually linkable by barcode/label, back-filled for existing rows, surfaced as "Used in runs" on the inventory plate page and as a physical-plate link on the run page.

**Architecture:** Domain field + method on `Run.Plate`; SA column + migration 069 (with SQL backfill); one shared resolver in `application/inventory`; two screening use cases (link/unlink) + one inventory query (runs for plate) behind readers; three routes; orval regen; one FE component + one card.

**Tech stack:** Python 3.13 / FastAPI / SQLAlchemy 2 async / Alembic / returns / Lagom; Next.js 16 / TanStack Query / shadcn; vitest, pytest + testcontainers.

**Spec:** `docs/superpowers/specs/2026-08-26-run-plate-inventory-link-spec.md` — read it first; sections are referenced below.

## Global Constraints

- **Read `docs/backend-code-guidelines.md` and `docs/patterns-and-conventions.md` before touching backend code.** Guards first (`require_authenticated` → role → `require_same_workspace`), Railway `Result`, UoW with dispatch after commit, workspace-scoped repo calls only, no `try/except AuthorizationError`.
- Backend commands run from `backend/`: `uv run pytest <path> -q`; integration/API tests need `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock` (testcontainers). Lint: `uv run ruff check <files>` and `uv run ruff format <files>`. Types: `uv run mypy <files>` if the repo runs mypy on that package (check `pyproject.toml`); otherwise skip.
- Frontend commands from `frontend/`: `pnpm vitest run <path>`, `pnpm exec biome check <files>`, `pnpm exec tsc --noEmit`. Generated types only from `@/shared/lib/api/model` — never hand-roll a DTO; the orchestrator runs `pnpm generate:api` between the backend and frontend waves.
- **Subagents never commit.** The orchestrator commits by explicit pathspec.
- Migration numbering: the head is `068_plate_comments`; this session adds exactly one migration, `069_run_plate_registered_plate`.
- Test fakes: unit tests use `tests/fakes/fake_auth.py` (`FakeAuth`) and the in-memory fake repositories under `tests/fakes/` — extend the fake plate repo when you add `find_by_label`.

## File map

| Task | Files |
|---|---|
| T1 domain | `backend/src/cellar/domain/screening_assay/run.py`, `backend/tests/unit/domain/screening_assay/test_run.py` |
| T2 persistence | `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py`, `.../screening_assay/run_repository.py`, `.../screening_assay/plate_map_reader.py`, `backend/src/cellar/application/screening/plate_map_reader.py`, `backend/alembic/versions/069_run_plate_registered_plate.py`, `backend/tests/integration/test_migration_069_backfill.py`, `backend/tests/integration/test_run_repository_find_by_ids.py` (or a new sibling) |
| T3 resolver | `backend/src/cellar/domain/inventory/repository.py`, `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/registered_plate_repository.py` (find the SA plate repo file), `backend/tests/fakes/` (fake plate repo), `backend/src/cellar/application/inventory/plate_reference.py`, `backend/tests/unit/application/inventory/test_plate_reference.py` |
| T4 link/unlink + import auto-link | `backend/src/cellar/application/screening/link_run_plate.py`, `.../screening/import_plan.py` (+ the import use case that builds the plan), `backend/src/cellar/infrastructure/di/_screening.py`, `backend/src/cellar/interface/dependencies/_screening.py`, `backend/src/cellar/interface/routes/plate_setup.py`, `backend/tests/unit/application/screening/test_link_run_plate.py`, `backend/tests/unit/application/screening/test_import_plan_autolink.py` (or extend the existing import-plan test), `backend/tests/api/test_run_plate_links.py` |
| T5 runs-for-plate | `backend/src/cellar/application/inventory/plate_runs_reader.py`, `.../inventory/list_runs_for_plate.py`, `backend/src/cellar/infrastructure/persistence/sqlalchemy/inventory/plate_runs_reader.py`, `backend/src/cellar/infrastructure/di/_inventory.py`, `backend/src/cellar/interface/dependencies/_inventory.py`, `backend/src/cellar/interface/routes/registered_plates.py`, `backend/tests/unit/application/inventory/test_list_runs_for_plate.py`, `backend/tests/api/test_plate_runs.py` |
| T6 frontend | `frontend/src/features/screening-assay/hooks/use-plate-setup.ts`, `frontend/src/features/screening-assay/components/run-plate-link.tsx` (+test), `.../run-data-panel.tsx`, `.../run-heatmap-panel.tsx`, `frontend/src/features/inventory/hooks/use-plates.ts`, `frontend/src/features/inventory/components/plate-detail.tsx` (+test) |
| T7 docs | `docs/domain-model/02-screening-assay.md`, `docs/domain-model/03-inventory.md` |

Waves (file-disjoint inside a wave): **W1** T1 T2 T3 · **W2** T4 T5 (T4 edits `di/_screening.py`, T5 edits `di/_inventory.py`) · orval regen · **W3** T6 T7.

---

### Task 1: Domain — `Plate.registered_plate_id` + `Run.link_plate`

**Interfaces (Produces):** `Plate(..., registered_plate_id: uuid.UUID | None = None)`; `Run.link_plate(plate_id: uuid.UUID, registered_plate_id: uuid.UUID | None) -> None`.

- [ ] **Step 1: failing tests** — append to `tests/unit/domain/screening_assay/test_run.py` (reuse the file's existing run/plate factories; if none, build a `Run.create(...)` with the minimal fields the file already uses):

```python
def test_link_plate_sets_and_clears_registered_plate(run_with_plate):
    run, plate = run_with_plate
    target = uuid.uuid4()
    run.link_plate(plate.id, target)
    assert plate.registered_plate_id == target
    run.link_plate(plate.id, None)
    assert plate.registered_plate_id is None

def test_link_plate_unknown_plate_is_not_found(run_with_plate):
    run, _ = run_with_plate
    with pytest.raises(NotFoundError):
        run.link_plate(uuid.uuid4(), uuid.uuid4())

def test_link_plate_blocked_when_locked(run_with_plate):
    run, plate = run_with_plate
    run.lock(locked_by=uuid.uuid4(), reason="qc")
    with pytest.raises(ConflictError, match="locked"):
        run.link_plate(plate.id, uuid.uuid4())
```
(`run_with_plate` = a fixture creating a run and `run.add_plate(Plate(run_id=run.id, plate_number=1))`.)

- [ ] **Step 2:** run `uv run pytest tests/unit/domain/screening_assay/test_run.py -q` → fails (no attribute / method).
- [ ] **Step 3: implement** in `run.py` — add the constructor param + attribute on `Plate`; on `Run`:

```python
    def link_plate(self, plate_id: uuid.UUID, registered_plate_id: uuid.UUID | None) -> None:
        """Point a run plate at the physical inventory plate it was run on (or clear it).

        Optional by design — a run plate without a link is normal. Blocked when locked.
        """
        self._guard_not_locked()
        plate = next((p for p in self.plates if p.id == plate_id), None)
        if plate is None:
            raise NotFoundError("Plate", str(plate_id))
        plate.registered_plate_id = registered_plate_id
        self.updated_at = datetime.now(UTC)
```
(`NotFoundError` from `cellar.domain.shared.errors` — check the module's existing imports.)
- [ ] **Step 4:** tests pass; `uv run ruff check` + `format` on both files.

---

### Task 2: Persistence — column, mapping, plate-map reader, migration 069 + backfill

**Interfaces (Produces):** `PlateModel.registered_plate_id`; `PlateMapData.registered_plate_id / registered_plate_barcode / registered_plate_label` (all `| None`); migration module exposes `BACKFILL_SQL: str`.

- [ ] **Step 1: failing tests.**
  - Round-trip: in `tests/integration/test_run_repository_find_by_ids.py` (or a new `test_run_repository_plate_link.py` using the same fixtures) save a run whose plate has `registered_plate_id` set to an existing registered plate's id and assert it loads back; also assert an update that clears it persists NULL.
  - Backfill: `tests/integration/test_migration_069_backfill.py` — load the migration by path (`importlib.util.spec_from_file_location("m069", "alembic/versions/069_run_plate_registered_plate.py")`), insert (via the test session/engine the integration fixtures give you) one registered plate `barcode="000123", plate_label="SAC3-014-3070"`, a run with three plates: A `barcode="000123"` (→ links), B `plate_map={"name": "SAC3-014-3070"}` (→ links by label), C `plate_map={"name": "AMBIG"}` with **two** registered plates labelled `AMBIG` (→ stays NULL); execute `m069.BACKFILL_SQL`; assert.
- [ ] **Step 2:** run both → fail (column missing).
- [ ] **Step 3: implement.**
  - `models.py` `PlateModel`: `registered_plate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("registered_plates.id", ondelete="SET NULL"), index=True)` (check how other cross-table FKs import/declare in this file; keep the table-args index name `ix_plates_registered_plate` consistent with the migration).
  - `run_repository.py`: add `registered_plate_id=pm.registered_plate_id` in `_to_domain`'s `Plate(...)` and `registered_plate_id=plate.registered_plate_id` in `_plate_to_model`.
  - `application/screening/plate_map_reader.py` `PlateMapData`: three new optional fields defaulting to `None`. Infra reader: after loading plates, `linked = {p.registered_plate_id for p in plates if p.registered_plate_id}`; if any, `select(RegisteredPlateModel.id, RegisteredPlateModel.barcode, RegisteredPlateModel.plate_label).where(RegisteredPlateModel.id.in_(linked))` (import the model from the inventory models module) and fill the fields per plate.
  - Migration `069_run_plate_registered_plate.py` (revises `068_plate_comments`):

```python
BACKFILL_SQL = """
WITH candidates AS (
  SELECT p.id AS plate_id, rp.id AS registered_plate_id
  FROM plates p
  JOIN runs r ON r.id = p.run_id
  JOIN registered_plates rp ON rp.workspace_id = r.workspace_id
   AND (rp.barcode = p.barcode OR rp.plate_label = p.plate_map->>'name')
  WHERE p.registered_plate_id IS NULL
), unique_candidates AS (
  SELECT plate_id, MIN(registered_plate_id::text)::uuid AS registered_plate_id
  FROM candidates GROUP BY plate_id HAVING COUNT(*) = 1
)
UPDATE plates p SET registered_plate_id = u.registered_plate_id
FROM unique_candidates u WHERE u.plate_id = p.id
"""

def upgrade() -> None:
    op.add_column("plates", sa.Column("registered_plate_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_plates_registered_plate", "plates", "registered_plates",
                          ["registered_plate_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_plates_registered_plate", "plates", ["registered_plate_id"])
    op.execute(BACKFILL_SQL)   # ponytail: exact matches only; app resolver handles zero-padding for new links

def downgrade() -> None:
    op.drop_index("ix_plates_registered_plate", table_name="plates")
    op.drop_constraint("fk_plates_registered_plate", "plates", type_="foreignkey")
    op.drop_column("plates", "registered_plate_id")
```
- [ ] **Step 4:** `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/test_migration_069_backfill.py tests/integration/test_run_repository_find_by_ids.py -q` → pass. Also run `uv run alembic check` if the repo uses it (skip if not configured). Ruff both ways on touched files.

---

### Task 3: `find_by_label` + `resolve_plate_reference`

**Interfaces (Produces):** `RegisteredPlateRepository.find_by_label(workspace_id, label) -> list[RegisteredPlate]`; `application/inventory/plate_reference.py::resolve_plate_reference(repo, workspace_id, raw) -> RegisteredPlate | None`.

- [ ] **Step 1: failing test** `tests/unit/application/inventory/test_plate_reference.py` using the in-memory fake plate repo (extend it with `find_by_label` — exact match over its stored plates):
  - exact barcode wins; `"123"` resolves a plate with barcode `"000123"`; a label match resolves when unique; two plates with the same label → `None`; unknown → `None`; blank → `None`.
- [ ] **Step 2:** run → fail.
- [ ] **Step 3: implement.** Protocol method in `domain/inventory/repository.py`; SA implementation (`select(RegisteredPlateModel).where(workspace_id == ..., plate_label == label)`), fake implementation; helper:

```python
async def resolve_plate_reference(repo, workspace_id, raw) -> RegisteredPlate | None:
    """Barcode chain first (spec §7), then an exact plate_label — only when unique."""
    plate = await resolve_barcode(repo, workspace_id, raw)
    if plate is not None:
        return plate
    label = raw.strip()
    if not label:
        return None
    by_label = await repo.find_by_label(workspace_id, label)
    return by_label[0] if len(by_label) == 1 else None
```
- [ ] **Step 4:** pass; ruff.

---

### Task 4: Link / unlink use cases, import auto-link, routes, API tests

**Consumes:** T1 `Run.link_plate`, T2 column + `PlateMapData` fields, T3 resolver. **Produces:** the two routes + `RunPlateLinkResponse`.

- [ ] **Step 1: failing tests.**
  - `tests/unit/application/screening/test_link_run_plate.py` — model it on `tests/unit/application/screening/test_create_run.py`'s fixture style with `FakeAuth`, the fake run repo, fake plate repo and a `PlateVisibilityService` stub (see `tests/unit/test_plate_visibility.py` for how it is built with a stub org directory). Cases: link by barcode / zero-padded / label sets `registered_plate_id` and returns barcode+label; unknown → `Failure(NotFoundError)`; plate owned by a hidden org → `Failure(NotFoundError)`; locked run → `ConflictError` (409) exactly as the other run mutations surface `_guard_not_locked` — match `test_create_run.py`/the lock tests; plate not on run → `Failure(NotFoundError)`; viewer → `pytest.raises(AuthorizationError)`; unlink clears.
  - Import auto-link: extend the existing import-plan unit test module (find it under `tests/unit/application/screening/` — `test_import_plan*.py` or the import-run-file tests) with a case where a file plate name equals a registered plate's label → the new plate has `registered_plate_id`; another name → `None`.
  - `tests/api/test_run_plate_links.py` — follow `tests/api/test_plate_loans.py` helpers (`_mk_plate`, `editor_client_own_org`, `editor_client_other_org`, `viewer_client`). Create a protocol + run (see `tests/api/test_run_collections.py:78` for the run body), create a run plate via `POST /runs/{id}/plate-setup` (see `tests/api/test_plate_templates.py` / plate-setup tests for a minimal body), then: link by barcode → 200 with `registered_plate_id`; by zero-padded barcode; by label; unknown → 404; other-org hidden plate → 404; relink overwrites; unlink → null; `GET /runs/{id}/plate-map` carries `registered_plate_*`; viewer → 403; locked run → 409 (lock via the existing lock route).
- [ ] **Step 2:** run → fail.
- [ ] **Step 3: implement.**
  - `application/screening/link_run_plate.py` per spec §5.2 (commands are frozen `Command` dataclasses with `workspace_id`; guards in order; `excluded = await visibility.excluded_org_ids(ws, auth)`, `borrowed = await visibility.borrowed_plate_ids(ws, auth)`; return a small frozen dataclass `RunPlateLink`).
  - `import_plan.py`: give the plan builder the plate repo + visibility (+ auth) and resolve each new plate's name; wire through the import use case that calls it (read `import_run_file.py` to find the call site and its DI factory in `di/_screening.py`).
  - DI: define `LinkRunPlate` / `UnlinkRunPlate` in `di/_screening.py` next to `SetUpRunPlate` (reuse `_plate_visibility(c, uow)` and `SQLAlchemyRegisteredPlateRepository(uow)`); `LinkRunPlateDep` / `UnlinkRunPlateDep` in `interface/dependencies/_screening.py`.
  - Routes in `plate_setup.py`:

```python
class LinkRunPlateBody(BaseModel):
    barcode: str = Field(min_length=1, max_length=100)

class RunPlateLinkResponse(BaseModel):
    plate_id: uuid.UUID
    registered_plate_id: uuid.UUID | None
    barcode: str | None
    plate_label: str | None

@router.post("/runs/{run_id}/plates/{plate_id}:link", response_model=RunPlateLinkResponse)
async def link_run_plate(run_id, plate_id, body, auth: AuthDep, uc: LinkRunPlateDep): ...
@router.post("/runs/{run_id}/plates/{plate_id}:unlink", response_model=RunPlateLinkResponse)
async def unlink_run_plate(run_id, plate_id, auth: AuthDep, uc: UnlinkRunPlateDep): ...
```
  - `PlateData` in `plate_setup.py` gains the three optional fields, filled from `PlateMapData`.
- [ ] **Step 4:** unit + API tests pass (`DOCKER_HOST=...` for API); ruff.

---

### Task 5: `GET /plates/{plate_id}/runs`

**Consumes:** T2 column. **Produces:** `PlateRunResponse` route.

- [ ] **Step 1: failing tests.** Unit `tests/unit/application/inventory/test_list_runs_for_plate.py` (stub reader; hidden plate → NotFound; viewer allowed; other workspace → NotFound via `require_same_workspace`). API `tests/api/test_plate_runs.py`: after linking a run plate (reuse the T4 helpers — copy the small helper functions rather than importing across test modules), `GET /plates/{id}/runs` returns one row with `run_id`, `run_date`, `plate_number`, `protocol_name`; unlinked plate → `[]`; hidden plate (other org) → 404.
- [ ] **Step 2:** run → fail.
- [ ] **Step 3: implement.** `application/inventory/plate_runs_reader.py` (`PlateRunRow` frozen dataclass + `PlateRunsReader` Protocol with `async def runs_for_plate(workspace_id, plate_id) -> list[PlateRunRow]`); SA reader:

```python
stmt = (
    select(RunModel.id, RunModel.run_date, RunModel.status, ProtocolModel.id, ProtocolModel.name,
           PlateModel.plate_number, RunModel.created_at)
    .join(RunModel, RunModel.id == PlateModel.run_id)
    .join(ProtocolModel, ProtocolModel.id == RunModel.protocol_id)
    .where(PlateModel.registered_plate_id == plate_id, RunModel.workspace_id == workspace_id)
    .order_by(RunModel.created_at.desc())
)
```
(`RunModel.run_date` — runs have no name.) Use case per spec §5.4; DI in `di/_inventory.py` (construct `PlateVisibilityService(c[OrgDirectoryPort], SQLAlchemyPlateLoanRepository(uow))` there — mirror `_plate_visibility` in `_screening.py` rather than importing it); `ListRunsForPlateDep` in `dependencies/_inventory.py`; route in `registered_plates.py` **above** any `/{plate_id}` catch-alls that would shadow `/{plate_id}/runs` (FastAPI matches in order — `/{plate_id}/children` shows the placement).
- [ ] **Step 4:** tests pass; ruff.

---

### Task 6: Frontend — run plate link + "Used in runs"

**Consumes:** regenerated `PlateData`, `RunPlateLinkResponse`, `PlateRunResponse`, `LinkRunPlateBody` types under `@/shared/lib/api/model` (the orchestrator regenerates before dispatch — if they are missing, stop and report).

- [ ] **Step 1: failing tests.**
  - `run-plate-link.test.tsx`: (a) linked plate renders a link `href="/inventory/plates/{id}"` with the barcode and an Unlink button that POSTs `…/plates/{plate_id}:unlink`; (b) unlinked renders "Link plate", clicking opens a dialog, typing `SAC3-014-3070` and submitting POSTs `:link` with `{ barcode: "SAC3-014-3070" }`; (c) `readOnly` renders the link but no buttons, and no "Link plate" when unlinked.
  - `plate-detail.test.tsx`: mock `GET /api/v1/plates/p1/runs` → one row → the "Used in runs" card lists `protocol_name`, `Run {run_date}`, `Plate 2` and links to `/assays/runs/{run_id}`; empty → "Not used in any run yet."
- [ ] **Step 2:** run → fail.
- [ ] **Step 3: implement.**
  - Hooks in `use-plate-setup.ts`:

```ts
export function useLinkRunPlate(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ plateId, barcode }: { plateId: string; barcode: string }) =>
      customInstance<RunPlateLinkResponse>({ url: `${API_V1}/runs/${runId}/plates/${plateId}:link`, method: "POST", data: { barcode } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: PLATE_MAP_KEY }); showSuccess("Plate linked"); },
  });
}
export function useUnlinkRunPlate(runId: string) { /* same shape, `:unlink`, no body, "Plate unlinked" */ }
```
  - `run-plate-link.tsx`:

```tsx
export function RunPlateLink({ runId, plate, readOnly }: { runId: string; plate: PlateData; readOnly?: boolean }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const link = useLinkRunPlate(runId);
  const unlink = useUnlinkRunPlate(runId);
  if (plate.registered_plate_id) {
    return (
      <span className="inline-flex items-center gap-2 text-xs">
        <Link href={`/inventory/plates/${plate.registered_plate_id}`} className="font-mono text-primary hover:underline" title={plate.registered_plate_label ?? undefined}>
          {plate.registered_plate_barcode}
        </Link>
        {plate.registered_plate_label ? <span className="text-muted-foreground">{plate.registered_plate_label}</span> : null}
        {readOnly ? null : (
          <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" disabled={unlink.isPending}
                  onClick={() => unlink.mutate({ plateId: plate.plate_id })}>Unlink</Button>
        )}
      </span>
    );
  }
  if (readOnly) return null;
  return (
    <>
      <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => setOpen(true)}>Link plate</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader><DialogTitle>Link physical plate</DialogTitle></DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="link-plate-ref">Barcode or plate name</Label>
            <Input id="link-plate-ref" autoFocus value={value} onChange={(e) => setValue(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter" && value.trim()) submit(); }} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button disabled={!value.trim() || link.isPending} onClick={submit}>Link</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
  // submit = link.mutate({ plateId: plate.plate_id, barcode: value.trim() }, { onSuccess: () => { setOpen(false); setValue(""); } })
}
```
  - Place it in `run-data-panel.tsx`'s plate header (next to "Plate {n}"; `readOnly={run is locked || !canEdit}` — read how the panel already knows lock/edit state, e.g. `run.status`/`locked` and `useCanEdit`) and in `run-heatmap-panel.tsx` with `readOnly`.
  - `use-plates.ts`: `usePlateRuns(plateId)` → `GET ${API_V1}/plates/${plateId}/runs` (`queryKey: [...PLATES_KEY, plateId, "runs"]`).
  - `plate-detail.tsx`: card "Used in runs" above History in the right column, `data-testid="plate-runs"`; rows are `<Link href={/assays/runs/${r.run_id}}>` with `protocol_name · Run {formatDate(run_date)}`, `Plate {plate_number}`, `StatusBadge(run_status)`.
- [ ] **Step 4:** tests pass, biome, tsc.

---

### Task 7: Docs
- [ ] `docs/domain-model/02-screening-assay.md` Plate table: `| **registered_plate_id** | UUID? | FK → RegisteredPlate (inventory) — optional link to the physical plate; SET NULL on plate delete |`. `03-inventory.md`: under RegisteredPlate relationships add `- Run plates (`plates.registered_plate_id`) — runs this physical plate was used in (read via GET /plates/{id}/runs)`. (Local, untracked docs — no commit needed, but do the edit.)

## Wrap-up (orchestrator)
1. Backend: `uv run pytest tests/unit -q`; API + integration for the touched modules; `uv run alembic upgrade head` against the local dev DB (backfills saclab-dev — check the count: `SELECT count(*) FROM plates WHERE registered_plate_id IS NOT NULL`).
2. `pnpm generate:api` with the backend up; review the `model/` diff; then W3.
3. Frontend full suite + tsc + biome; browser check: a run page with a linked plate, link/unlink, the plate page's "Used in runs".
4. Commits: S15 backend (T1–T5 files + migration), S15 frontend (T6 + regenerated models). One whole-branch review; spec sync note; issue #71.
