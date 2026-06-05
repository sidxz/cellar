# Multi-Target Links for Runs & Protocols — Design

**Date:** 2026-06-05
**Context:** Screening & Assay (02)
**Status:** Approved (design); pending implementation plan

---

## 1. Problem

Today a `Protocol` carries a **single** optional biological target via a scalar
`protocols.target_id` FK → `targets.id`. A `Run` has **no** target concept at
all (it inherits its protocol's target only implicitly).

We need:

1. **Every Run** linkable to **one or more** targets, as an **independent** set.
   (Run A screens NadD; Run B screens PptT — no copying between runs, no
   auto-seed from the protocol.)
2. **Every Protocol** linkable to **one or more** targets at the base level.
3. **Roll-up on add:** adding a target to a run makes that target appear on the
   run's protocol automatically.
4. **Auto-prune orphans on remove:** a target stays on the protocol as long as
   **either** it was added directly at the protocol level **or** at least one
   run still references it. When the last run drops an inherited-only target, it
   disappears from the protocol. A directly-added protocol target (e.g. an
   existing Pks13) is never auto-pruned.

### Worked example

```
Protocol P (direct: [Pks13])

Run A targets: [NadD]      → P effective: [Pks13, NadD]
Run B targets: [PptT]      → P effective: [Pks13, NadD, PptT]

Remove NadD from Run A (no other run has NadD, not direct)
                           → P effective: [Pks13, PptT]   (NadD pruned)

Remove Pks13 directly at P (added directly)
                           → P effective: [PptT]          (allowed)
```

---

## 2. Chosen approach — compute the inherited set

Two representations were considered for the auto-prune provenance:

- **Approach 1 (chosen): compute the inherited set.** Store only the run sets
  and the protocol's *direct* additions; derive the protocol's effective list as
  a union at read time.
- **Approach 2 (rejected): store the rolled-up list with an `is_direct` flag,**
  upsert into the protocol on every run-target add, and run explicit prune logic
  on every run-target remove.

Approach 1 wins: the auto-prune behavior is **correct by construction** (no
bookkeeping to get wrong), and **no write ever crosses an aggregate boundary** —
adding a target to a run touches only `run_targets`; the protocol picks it up
purely through the union query. Approach 2's cross-aggregate writes and
hand-rolled prune logic are exactly the class of bug Approach 1 makes
impossible. The only cost is that protocol target reads are a small
join/aggregate instead of a flat select — negligible with the right index.

---

## 3. Data model

Two **pure association tables**, mirroring the existing `protocol_projects`
precedent in
`backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py`
(composite PK, both FKs `ON DELETE CASCADE`, no metadata columns):

```
run_targets        run_id      → runs.id       (PK part, ON DELETE CASCADE)
                   target_id   → targets.id    (PK part, ON DELETE CASCADE)
                   PRIMARY KEY (run_id, target_id)

protocol_targets   protocol_id → protocols.id  (PK part, ON DELETE CASCADE)
                   target_id   → targets.id    (PK part, ON DELETE CASCADE)
                   PRIMARY KEY (protocol_id, target_id)
```

- `run_targets` — each run's **independent** target set; source of truth for runs.
- `protocol_targets` — the protocol's **direct** target additions only.
- **Effective protocol targets** =
  `protocol_targets(protocol)` ∪ `DISTINCT run_targets` over the protocol's runs.
- The `target_id → targets.id` FK uses `ON DELETE CASCADE` so deleting a target
  removes all of its links. Add an index on `target_id` for both tables (cascade
  + reverse lookup).

Provenance is **implicit**: a target present in `protocol_targets` is "direct";
a target present only via the run union is "inherited". This is what gives
auto-prune for free.

### Why repo/application-managed, not on the aggregate

The established convention for a reference-entity M2M in this codebase
(`protocol_projects`) keeps the **domain aggregate free of the collection** and
manages the association in the repository + application layer
(`add_to_project` / `remove_from_project` / `find_project_ids` on the repo, a
dedicated `/protocols/{id}/projects/{id}` endpoint, `project_ids` populated into
the response separately). We mirror this exactly. The **only** domain change is
*removing* the now-obsolete scalar `Protocol.target_id`. Aggregates gain no
target collection. Lock/status rules are enforced in the use cases (load the
entity, check `is_locked` / status) — consistent with how the rest of the
application layer guards mutations.

This was explicitly chosen over pure-DDD aggregate modeling (a `target_ids` set
with `add_target`/`remove_target` domain methods) for consistency with the
precedent.

---

## 4. Migration — `051_protocol_run_targets_m2m`

Chains from current head `050_tagging_expansion`. Follows the association-table
template from `050_tagging_expansion.py` and `001_001_initial_schema.py`.

**upgrade():**
1. Create `protocol_targets` and `run_targets` (composite PK, FKs with CASCADE).
2. Create index on `target_id` for each table.
3. **Backfill:** `INSERT INTO protocol_targets (protocol_id, target_id)
   SELECT id, target_id FROM protocols WHERE target_id IS NOT NULL`.
4. **Drop** column `protocols.target_id` (and its FK constraint).

**downgrade():**
1. Re-add `protocols.target_id` FK column (nullable).
2. Best-effort restore: set `protocols.target_id` from the single
   `protocol_targets` row where exactly one direct target exists (lossy by
   nature — multi-target protocols cannot round-trip; documented in the
   migration docstring).
3. Drop `run_targets` and `protocol_targets`.

No backwards-compat shim is kept on the column — this is a clean cutover.

---

## 5. Backend API surface

### Protocol

- `ProtocolResponse.target_id` (scalar) → **`targets: list[ProtocolTargetRef]`**
  where `ProtocolTargetRef = { id, name, target_type, is_direct: bool, run_count: int }`.
  `is_direct` and `run_count` let the UI badge "Added here" vs "From N runs".
- `ProtocolSummaryResponse.target_id` + `target_name` → **`targets: list[{ id, name }]`**
  (lightweight; for list badges + search).
- `CreateProtocolRequest.target_id` → **`target_ids: list[uuid] = []`**
  (initial *direct* targets).
- `UpdateProtocolRequest`: drop `target_id` (direct targets are managed by the
  dedicated endpoints below; keeps update small).
- **New endpoints** (mirror the projects endpoints):
  - `POST   /protocols/{protocol_id}/targets/{target_id}` — add a direct target (idempotent).
  - `DELETE /protocols/{protocol_id}/targets/{target_id}` — remove a direct target.

### Run

- `RunResponse` gains **`targets: list[{ id, name, target_type }]`**.
- `CreateRunRequest` gains **`target_ids: list[uuid] = []`** (initial run set).
- **New endpoints:**
  - `POST   /runs/{run_id}/targets/{target_id}` — add a target to the run (idempotent).
  - `DELETE /runs/{run_id}/targets/{target_id}` — remove a target from the run.

All add operations are idempotent (`ON CONFLICT DO NOTHING`, mirroring
`add_to_project`). All endpoints are workspace-scoped with the same
defense-in-depth checks `add_to_project` uses (verify both entities belong to
the caller's workspace before mutating).

---

## 6. Backend consumers to update

From the consumer map:

**Repository**
- `protocol_repository.py`: remove scalar `target_id` mapping (`:335` to_domain,
  `:394` to_model, `:427` update_model); add `add_target` / `remove_target` /
  `find_effective_targets(protocol_id)` (union query) /
  `find_direct_target_ids(protocol_id)`.
- `run_repository.py`: add `add_target` / `remove_target` /
  `find_target_ids(run_id)`; hydrate `targets` for run reads.

**Domain**
- `protocol.py`: remove `target_id` from `__init__` (`:309/:339`), `create`
  (`:431/:446`), `update` (`:510/:527-528`).
- `protocol_versioning_service.py:88`: copy the parent's **direct** targets into
  the new version's `protocol_targets` (done in the versioning flow, since
  associations are repo-managed). Inherited targets are not copied — they
  re-derive from the new version's runs.

**Application**
- `create_protocol.py` (`:44/:146`): accept `target_ids`, write direct targets.
- `manage_protocol.py` (`:159/:194`): drop `target_id` from update command.
- `list_protocol_summaries.py` (`:42/:93-94`): replace single `target_name`
  enrichment with a batched effective-targets lookup (no N+1: load
  `protocol_targets` + `run_targets`⋈`runs` + a target id→name map, union in
  Python).
- `get_molecule_activity_detail.py:227`: replace the scalar `target_id` field
  with `targets: list[{ id, name }]` (the protocol's effective target list).
- `create_run.py`: accept `target_ids`, write run targets.
- `update_run.py`: unchanged (targets via dedicated endpoints), unless we choose
  to accept targets here too — out of scope for v1.
- `close_campaign.py:173`: serialize the effective target list instead of the
  scalar `target_id`.

---

## 7. Frontend

- **New reusable `TargetMultiSelect`** (search + multi-select chips + inline
  "create target" affordance — never asks for UUIDs), built on the existing
  `SearchableSelect`. Sources from `useTargets()`.
- **Protocol `#design` tab** (`design-tab.tsx`): replace the single-target field
  with a **Targets** section — direct targets as removable chips; inherited
  targets shown read-only with a "from N runs" badge (managed on the run).
  Optional later: a "pin to protocol" action to promote inherited → direct.
  Add/remove are explicit gestures that persist immediately via the dedicated
  endpoints (consistent with how readout/condition adds work).
- **Run detail page**: new **Targets** card — the run's independent set,
  add/remove chips. Explicit gestures, no autosave-on-blur.
- **Create dialogs**: `create-protocol-dialog.tsx` and the run-create flow get
  the multi-select for initial targets (replacing the single `SearchableSelect`
  at `create-protocol-dialog.tsx:477-485`).
- **List/search**: `protocol-section.tsx` (`:133/:162-164`) and
  `source-protocols-list.tsx:27` render multiple target chips and search across
  all target names.
- **Types/hooks**: update `types/index.ts` (`Protocol`, `ProtocolSummary`,
  `Run`, add target-ref shapes) and `use-protocols.ts`. These are currently
  hand-written interfaces; per CLAUDE.md the ideal is orval-generated + aliased.
  We follow the existing hand-written local convention to keep scope tight, and
  **flag the orval regen** (`pnpm generate:api`) as the correct path — to be
  decided during implementation review.

---

## 8. Decisions (resolved)

- **Run ↔ Protocol semantics:** runs independent; add rolls up to protocol;
  remove auto-prunes orphans; directly-added protocol targets never pruned.
- **Representation:** Approach 1 (compute the inherited set).
- **Aggregate vs repo-managed:** repo/application-managed, mirroring
  `protocol_projects`.
- **Delete a target that is in use:** allowed (CASCADE cleans links); the
  delete-confirm dialog shows a usage count ("Used by N protocols, M runs").
- **Lock/status guards:** block target edits on a locked run; allow protocol
  direct-target edits on DRAFT or unlocked ACTIVE, block on RETIRED/locked.
- **Run-target edits allowed in any run status** as long as the run is unlocked
  (targets are metadata, like notes).

---

## 9. Out of scope (v1)

- Run-import "target" column — targets remain a UI/API action, not part of CSV
  import.
- Dedicated target detail/landing page.
- Bulk target assignment across many runs/protocols.
- Accepting target edits through `update_run` (use the dedicated endpoints).

---

## 10. Testing

- **Domain:** versioning copies the parent's direct targets to a new version.
- **Repository:** union / auto-prune — add a target to two runs → protocol
  effective list shows it once; drop the last run referencing it → pruned; a
  direct target survives when all runs drop it; deleting a target cascades link
  rows.
- **API:** add/remove endpoints (idempotent, workspace-scoped); create-with-
  targets for both protocol and run; effective-targets shape in responses.
- **Migration:** backfill copies existing `target_id` into `protocol_targets`;
  column dropped; downgrade restores single-target protocols.
- **Frontend:** `TargetMultiSelect` (search, multi-select, create affordance);
  protocol design tab direct vs inherited rendering; run targets card.
```
