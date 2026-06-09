# Collection Links & Coverage for Runs & Protocols — Design

**Date:** 2026-06-07
**Context:** Screening & Assay (02), reading Research Organization (05)
**Status:** Approved (design); pending implementation plan

---

## 1. Problem

A screening lead wants to know **how much of a compound library a run (and the
protocol overall) has actually covered.** "We've screened 1,840 of the 2,000
compounds in the Kinase Set (92%)" is a standard library-progress signal that
the platform can't surface today.

We already let a `Run` carry one or more **targets**, rolled up onto its
`Protocol`. We want the analogous capability for **collections**, plus a derived
**coverage %** on top:

1. **Every Run** linkable to **one or more** `Collection`s, as an **independent**
   set (mirrors run↔target).
2. For each attached collection, compute **coverage** = the run's screened
   molecules that are members of the collection ÷ the collection's size.
3. **Protocol roll-up:** the protocol shows each distinct attached collection
   with its **cumulative** coverage across the runs that attached it.
4. **Gap drill-down:** from any coverage bar, see exactly **which members are not
   yet screened** (run-level, and cumulative at the protocol level).

The feature is *intended* for `library`-type collections but is **not
restricted** — any collection type may be attached.

As a small companion deliverable: give each **collection type its own icon**,
used everywhere collections render (this is independent of coverage but ships
alongside it).

### Worked example

```
Protocol P
  Run A  attaches: [Kinase Set (2,000)]   screened ∩ Kinase Set = 1,200  → 60%
  Run B  attaches: [Kinase Set (2,000)]   screened ∩ Kinase Set = 1,500  → 75%
                                           (Run A ∪ Run B distinct) = 1,840

  P effective coverage:  Kinase Set — 1,840 / 2,000 (92%) across 2 runs
```

Union is taken over the **runs that attached the collection only** (a run that
incidentally screened a Kinase Set member but never attached the collection does
**not** count).

---

## 2. Chosen approach — store only the link, compute coverage live

Three approaches were considered for delivering coverage:

- **Approach A (chosen): live read-time computation.** Store only the
  `run_collections` link. Coverage numerators are computed on read via a single
  grouped `COUNT(DISTINCT molecule_id)` intersection query; denominators come
  from `collection_molecules`. Nothing derived is persisted.
- **Approach B (rejected): persisted/snapshotted coverage.** Store
  numerator/denominator on the link row and recompute on every readout import,
  merge, and collection-membership change. Fastest reads, but introduces a
  derived-state invalidation web (any missed trigger silently shows wrong
  coverage) — exactly the class of bug the platform's read-time roll-ups avoid.
- **Approach C (rejected): lazy on-demand only.** Compute coverage only when a
  panel is expanded, never in list views. Keeps grids cheap but loses the
  at-a-glance % on the run row, which is the feature's main draw.

Approach A wins: coverage is **correct by construction** (it always reflects
current readouts + current membership), there is **no invalidation bookkeeping**,
and it matches how `find_effective_targets` already rolls up at read time. The
only cost is a couple of indexed `COUNT(DISTINCT …)` queries per run/protocol
view; a short-TTL cache can be added later if profiling ever demands it.

**"Screened" = distinct `readout_data.molecule_id`.** This is consistent with the
existing per-run molecule count (`get_molecule_counts`) and is the only
universally-available path: summary / well-less imports carry a `molecule_id`
with no plate or well, and they **do** count (verified intent). No "planned from
plate layout" notion is introduced.

---

## 3. Data model

One **pure association table**, mirroring `run_targets`
(`backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/models.py`):

```
run_collections    run_id        → runs.id          (PK part, ON DELETE CASCADE)
                   collection_id → collections.id    (PK part, ON DELETE RESTRICT)
                   PRIMARY KEY (run_id, collection_id)
                   INDEX (collection_id)
```

- `run_collections` — each run's **independent** collection set; source of truth.
- **No `protocol_collections` table.** Attachment is **run-level only**; the
  protocol coverage view is pure roll-up over the attaching runs. (A direct
  protocol-level attach can be added later if a need appears — explicitly
  deferred.)
- The `collection_id → collections.id` FK uses **`ON DELETE RESTRICT`** (not
  CASCADE), mirroring `053_target_link_restrict`: a collection referenced by a
  run cannot be silently deleted; `DeleteCollection` must check references first.
- Index on `collection_id` for the reverse lookup + coverage joins.

Membership itself is **not duplicated** here — it stays in
`collection_molecules` (research-org owns it). `run_collections` only records the
attach.

### Repo/application-managed, not on the aggregate

Same convention as `run_targets`: the `Run` aggregate gains **no** collection
field; the association is managed in the repository + application layer. Lock
guards live in the use cases. This mirrors `manage_run_targets.py` exactly.

---

## 4. Coverage — a focused read model

Coverage spans three tables across two bounded contexts (`run_collections` +
`readout_data` in screening, `collection_molecules` in research-org). Rather than
scatter it, all coverage logic lives in **one well-bounded read-query object** in
screening infra, e.g. `coverage_query.py` (`CollectionCoverageQuery`). It exposes
two batched methods plus a size lookup. Every query is also filtered by
`workspace_id` on both the run and the collection (defense-in-depth).

**Per-run** (run detail + run list grid):

```sql
SELECT rc.run_id, rc.collection_id, COUNT(DISTINCT rd.molecule_id) AS covered
FROM run_collections rc
JOIN readout_data rd
  ON rd.run_id = rc.run_id AND rd.molecule_id IS NOT NULL
JOIN collection_molecules cm
  ON cm.collection_id = rc.collection_id AND cm.molecule_id = rd.molecule_id
WHERE rc.run_id = ANY(:run_ids)
GROUP BY rc.run_id, rc.collection_id
```

**Protocol roll-up** (union over attaching runs only):

```sql
SELECT rc.collection_id,
       COUNT(DISTINCT rd.molecule_id) AS covered,
       COUNT(DISTINCT rc.run_id)      AS run_count
FROM run_collections rc
JOIN runs r          ON r.id = rc.run_id AND r.protocol_id = :protocol_id
JOIN readout_data rd ON rd.run_id = rc.run_id AND rd.molecule_id IS NOT NULL
JOIN collection_molecules cm
  ON cm.collection_id = rc.collection_id AND cm.molecule_id = rd.molecule_id
GROUP BY rc.collection_id
```

`COUNT(DISTINCT rd.molecule_id)` dedupes a molecule that was screened in more
than one attaching run, giving a true cumulative union.

**Denominators** (`total`) come from a grouped count over `collection_molecules`
for the relevant `collection_id`s. Coverage fraction = `covered / total`, with
**`total = 0` → fraction is `None`** (empty library → surfaced as "—", never a
divide-by-zero).

### Gap list — the uncovered members

Beyond the %, the read model exposes the **set difference**: which collection
members have **not** yet been screened. This is the actionable drill-down behind
each coverage bar ("160 remaining → see which 160"). Two paginated methods,
`run_gap(workspace_id, run_id, collection_id, offset, limit)` and
`protocol_gap(workspace_id, protocol_id, collection_id, offset, limit)`, each
returning `molecule_id`s ordered by `collection_molecules.added_at`.

**Run-level gap:**

```sql
SELECT cm.molecule_id
FROM collection_molecules cm
WHERE cm.collection_id = :collection_id
  AND NOT EXISTS (
    SELECT 1 FROM readout_data rd
    WHERE rd.run_id = :run_id AND rd.molecule_id = cm.molecule_id
  )
ORDER BY cm.added_at, cm.molecule_id
LIMIT :limit OFFSET :offset
```

**Protocol-level gap** (uncovered by *any* attaching run):

```sql
SELECT cm.molecule_id
FROM collection_molecules cm
WHERE cm.collection_id = :collection_id
  AND NOT EXISTS (
    SELECT 1 FROM readout_data rd
    JOIN run_collections rc ON rc.run_id = rd.run_id AND rc.collection_id = :collection_id
    JOIN runs r            ON r.id = rd.run_id AND r.protocol_id = :protocol_id
    WHERE rd.molecule_id = cm.molecule_id
  )
ORDER BY cm.added_at, cm.molecule_id
LIMIT :limit OFFSET :offset
```

**Correctness — use `NOT EXISTS`, never `NOT IN`.** `readout_data.molecule_id`
is nullable; a single NULL in a `NOT IN (…)` subquery makes the whole predicate
return *zero* rows (silent wrong-empty gap). `NOT EXISTS` with an equality join
is null-safe — `rd.molecule_id = cm.molecule_id` never matches a NULL, which is
exactly the intended semantics. The "remaining" count shown above the list is
free: `total − covered` from the coverage query.

### Architectural note (cross-context read)

This read model **joins `collection_molecules` (research-org) from screening
infra**. The **write** side — collection membership management — stays entirely
in research-org. This is a deliberate read-only reporting join, chosen over a
port-based set-intersection that would pull thousands of member UUIDs into Python
to intersect. Flagged here for review; revisit if the contexts must stay fully
decoupled at the persistence layer.

---

## 5. Domain value objects

Mirror `TargetRef` / `EffectiveTarget` in
`backend/src/cellar/domain/screening_assay/`:

- `CollectionRef(id, name, type)` — lightweight reference for responses.
- `CollectionCoverage(ref, covered: int, total: int)` with a `fraction` property
  (`None` when `total == 0`). Run-level.
- `EffectiveCollectionCoverage(ref, covered: int, total: int, run_count: int)` —
  the protocol roll-up shape.

---

## 6. Migration — `055_run_collections_m2m`

Chains from current head `054_favorites`. Follows the association-table template
from `051_protocol_run_targets_m2m.py`.

**upgrade():**
1. Create `run_collections` (composite PK; `run_id` FK CASCADE; `collection_id`
   FK **RESTRICT**).
2. Create index on `collection_id`.

**downgrade():**
1. Drop `run_collections`.

No backfill (new capability, no existing scalar to migrate).

---

## 7. Backend API surface

### Run

- `RunResponse` gains **`collections: list[CollectionCoverageResponse]`** where
  `CollectionCoverageResponse = { id, name, type, covered, total, fraction|null }`.
- `CreateRunRequest` gains **`collection_ids: list[uuid] = []`** (attach at
  creation; mirrors `target_ids`).
- **New endpoints** (mirror run-target endpoints):
  - `POST   /runs/{run_id}/collections/{collection_id}` — attach (idempotent, 204).
  - `DELETE /runs/{run_id}/collections/{collection_id}` — detach (204).
  - `GET    /runs/{run_id}/collections/{collection_id}/gap?offset&limit` —
    paginated `molecule_id`s not yet screened in this run (the §4 run-level gap).

### Protocol

- **New endpoint:** `GET /protocols/{protocol_id}/collection-coverage` →
  `list[EffectiveCollectionCoverageResponse]`
  (`{ id, name, type, covered, total, fraction|null, run_count }`), mirroring
  `GET /protocols/{protocol_id}/targets`.
- **New endpoint:** `GET /protocols/{protocol_id}/collections/{collection_id}/gap?offset&limit` —
  paginated `molecule_id`s not yet screened by **any** attaching run (the §4
  protocol-level gap).

Both gap endpoints return `molecule_id`s only; the frontend resolves them to
structures/names through the existing molecule-resolution path (the collection
detail page already does exactly this). The "remaining" total is `total −
covered` from the coverage payload, so the list header needs no extra count call.

All attach operations are idempotent (`ON CONFLICT DO NOTHING`). All endpoints
are workspace-scoped with the same defense-in-depth checks the target endpoints
use (verify both entities belong to the caller's workspace before mutating).

---

## 8. Backend components

**Repository** (`run_repository.py`): add `add_collection` /
`remove_collection` / `find_collection_refs_for_runs` — direct analogues of the
existing `add_target` / `remove_target` / `find_target_refs_for_runs`.

**Read model** (`coverage_query.py`, new): `CollectionCoverageQuery` with
`run_coverage(workspace_id, run_ids)`,
`protocol_coverage(workspace_id, protocol_id)`, the denominator size lookup, and
the two paginated gap methods `run_gap(...)` / `protocol_gap(...)` (§4).

**Application**
- `manage_run_collections.py` (new): `AddRunCollection` / `RemoveRunCollection`
  use cases — run-lock guarded, idempotent, emit `RunCollectionAdded` /
  `RunCollectionRemoved` audit events. Direct copies of `manage_run_targets.py`.
- `list_runs_with_counts.py`: extend `RunWithCounts` with
  `collections: list[CollectionCoverage]`, populated from one batched
  `run_coverage` call (no N+1) alongside the existing targets enrichment.
- `create_run.py`: accept `collection_ids`, write run-collection links.
- New protocol-coverage query use case feeding the new endpoint.

**Domain events** (`screening_assay/events.py`): `RunCollectionAdded` /
`RunCollectionRemoved` (`collection_id`, `user_id`) for the audit trail.

---

## 9. Frontend

### Reusable coverage component — `CoverageBar`

One presentational component used across all three surfaces:
`[type icon] Collection name` + a thin progress bar + `1,840 / 2,000 · 92%`, and
a **`160 remaining`** affordance that opens the gap drill-down.

- **Single neutral accent fill, NOT a red→green semaphore.** Low coverage early
  in a campaign is expected, not a problem; color-grading would falsely signal
  "bad". The % is the signal, the fill is just proportion.
- **Empty library (`total = 0`) → "—"**, no bar, no gap affordance.
- The `remaining` count sits **next to** (not inside) the "View not-yet-screened"
  action — a count, not an operate-on badge.

### Gap drill-down — `CoverageGapDialog`

Clicking "remaining" opens a dialog listing the **uncovered members** (molecule
cards/table reusing the existing molecule-resolution + structure rendering used
on the collection detail page), paginated via the gap endpoint. Run-detail bars
open the run-level gap; protocol roll-up bars open the protocol-level (cumulative)
gap. v1 is **view-only**; turning a gap into a cherry-pick collection or an export
is a natural follow-up (the compose/export machinery already exists) and is left
out of v1.

### Surfaces

1. **Run detail — "Collections" card** (beside the existing Targets card).
   Read-only: a `CoverageBar` per attached collection. Edit mode: a
   `CollectionMultiSelect` picker + the bars. Explicit add/remove gestures that
   persist immediately via the dedicated endpoints (no autosave-on-blur), exactly
   like the Targets card.
2. **Run list — "Library coverage" column.** Compact: each attached collection as
   a small pill `[icon] 92%`, full name + `1,840 / 2,000` in tooltip; overflow
   collapses to `+N` (same idiom as `TargetChips`).
3. **Protocol detail — "Library coverage" roll-up** (near the effective-targets
   display). The headline: a full-width `CoverageBar` per distinct attached
   collection with the **cumulative** %, captioned "across N runs". Sourced from
   `GET /protocols/{id}/collection-coverage`.

### Picker + hooks

- **`CollectionMultiSelect`** mirrors `TargetMultiSelect` (search → multi-select →
  removable chips with the type icon), sourced from the existing collections
  search API. All collection types are selectable (not restricted to libraries);
  **Library** is sorted/grouped first so the common case is front.
- **`use-run-collections.ts`** (`useAddRunCollection` / `useRemoveRunCollection`),
  reusing the generic link-hook factory (`create-target-link-hooks.ts`).
  Invalidates run detail + run list + protocol-coverage queries.

### Types

Update the hand-written `types/index.ts` (`Run`, add the coverage-ref shapes)
following the existing local convention; flag `pnpm generate:api` as the correct
path per CLAUDE.md, to be decided during implementation review.

---

## 10. Collection-type icons (companion deliverable)

Add `COLLECTION_TYPE_ICONS: Record<CollectionType, LucideIcon>` next to the
existing `COLLECTION_TYPE_LABELS`
(`frontend/src/features/research-organization/types/index.ts`), and use it
**everywhere collections render** — collection list, collection detail header,
collection picker dialog, `CollectionMultiSelect` chips, and the new
`CoverageBar`. Approved mapping:

| Type | Icon (lucide) | Reasoning |
|------|---------------|-----------|
| `library` | `Library` | Books on a shelf = compound library; the canonical case |
| `generic` | `Boxes` | A plain grouping, no special semantics |
| `reference_set` | `BadgeCheck` | Validated reference / standard compounds measured against |
| `hit_list` | `Flame` | Active "hot" hits from screening |
| `series` | `GitBranch` | A chemical series — branching analogs / SAR lineage |
| `distribution_set` | `Send` | Compounds slated to be shipped / distributed out |

Two deliberate avoidances: `Target` / `Crosshair` are reserved for the Targets
feature's visual language; `Share2` is too close to the "shared" visibility
badge, so `distribution_set` uses `Send`.

---

## 11. Decisions (resolved)

- **Roll-up semantics:** union over the runs that **attached** the collection
  only (not all protocol runs, not best-single-run).
- **Multiplicity:** multiple collections per run (mirrors targets).
- **Coverage representation:** Approach A — store only the link, compute live.
- **"Screened" set:** distinct `readout_data.molecule_id`; summary / well-less
  imports count.
- **Denominator:** full collection membership; `total = 0` → fraction `None` → "—".
- **Gap list:** in v1, view-only. Set difference via `NOT EXISTS` (null-safe);
  run-level and protocol-level (cumulative) variants; molecule-id paging resolved
  to structures through the existing path.
- **Attachment level:** run-level only; protocol view is pure roll-up.
- **FK on delete:** `RESTRICT` on `collection_id` (a referenced collection can't
  be silently deleted).
- **Aggregate vs repo-managed:** repo/application-managed, mirroring
  `run_targets`.
- **Lock guard:** block collection attach/detach on a locked run; allowed in any
  run status while unlocked (metadata, like targets).
- **Coverage color:** neutral fill, not a red→green semaphore.

---

## 12. Out of scope (v1)

- Direct protocol-level collection attach (only run-level + roll-up).
- Persisted/snapshotted coverage or any caching layer (add only if profiling
  demands).
- Run-import "collection" column — attach remains a UI/API action, not CSV import.
- Coverage on campaigns (separate surface; can reuse `CoverageBar` later).
- **Actions on the gap list** — turning the not-yet-screened set into a
  cherry-pick collection or a CSV export. The view-only gap drill-down ships in
  v1; the compose/export actions on it are the immediate follow-up.
- Accepting collection edits through `update_run` (use the dedicated endpoints).

---

## 13. Testing

- **Read model (integration):** per-run coverage counts distinct molecules;
  protocol roll-up unions across attaching runs **only** (a non-attaching run
  that screened a member does not inflate it); a molecule screened in two
  attaching runs counts once; `total = 0` yields fraction `None`; all queries
  workspace-scoped.
- **Gap list (integration):** run-level and protocol-level gaps return exactly
  the unscreened members (`covered + gap = total`); a `NULL`
  `readout_data.molecule_id` does **not** collapse the gap to empty (the
  `NOT EXISTS` null-safety guard); paging is stable; protocol gap excludes
  anything screened by any attaching run.
- **Repository:** attach is idempotent; detach removes the link; `RESTRICT`
  blocks deleting a referenced collection; `find_collection_refs_for_runs`
  batches correctly.
- **Application:** lock guard blocks attach/detach on a locked run; events emit
  only on real state change; `create_run` with `collection_ids`;
  `ListRunsWithCounts` returns coverage with no N+1.
- **API:** attach/detach endpoints (idempotent, workspace-scoped); run response
  carries coverage; `GET /protocols/{id}/collection-coverage` shape + run_count.
- **Frontend:** `CoverageBar` (fill proportion, empty-library "—", neutral
  color, "remaining" affordance); `CoverageGapDialog` (lists unscreened members,
  paginates, run vs protocol scope); `CollectionMultiSelect` (search,
  multi-select, library-first); run-detail Collections card; run-list coverage
  column overflow; protocol roll-up; `COLLECTION_TYPE_ICONS` rendered across
  list/detail/picker.
```