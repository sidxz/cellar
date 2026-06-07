# Campaign Targets Projection — Design

**Date:** 2026-06-07
**Status:** Approved (brainstorming) — ready for implementation plan
**Context:** Each run carries one or more targets (`run_targets`, the source of truth). A
campaign is built from runs via its measurements. Users want to see and **filter campaigns by
target** in the project campaign table. This adds a derived campaign→target relationship.

---

## Decision summary

| Question | Decision |
|----------|----------|
| What is a campaign's target set? | **Union of `run_targets` over the runs the campaign's measurements reference** (`source_run_id` ∪ `contributing_run_ids`). Truthful "what was measured." |
| Store it? | **No.** Computed at read time, never stored. Mirrors the established protocol pattern (`protocol_repository.find_effective_targets`, and the design note at `screening_assay/models.py:60-64`). |
| Cross-context sync / events? | **None.** No `campaign_targets` table, no `RunTargetsChanged` events. Avoids the denormalization-staleness trap and screening→research_organization event coupling. |
| Counter-screen / off-target noise | **Accepted for v1.** A counter-screened InhA campaign chips both InhA and the off-target. Filter semantics are EXISTS ("campaign involves target X"), which is correct and useful even with counter-screens. |
| Explicit "primary target" (intent) | **Deferred (YAGNI).** The protocol model's `direct` vs `inherited` duality could be mirrored later if chemists need "about" vs "touched". Not built now. |

### Non-goals

- No stored/materialized campaign→target table or column.
- No domain events to maintain a derived set.
- No explicit scientist-set "primary target" on the campaign (deferred).
- No change to how runs or protocols carry targets.

---

## Why derived, not stored

The Campaign→Target relationship is fully derivable (`campaign → measurements → runs → run_targets`).
Storing it would be a denormalized cache needing invalidation across a **context boundary**
(`run_targets` lives in `screening_assay`; campaigns live in `research_organization`), driven by
cross-context events on every run add/remove/retarget. That is real coupling and a staleness trap,
bought for a performance win that does not exist at this scale (campaigns-per-project = tens). The
codebase already made this exact call one level down (protocol effective targets are "computed at
read time, never stored"); campaigns mirror it for a consistent mental model.

---

## Architecture

### Relationships (existing)

```
Target (screening_assay)
  ▲  run_targets (M:N, source of truth)
  │
Run ──< CampaignMeasurement.source_run_id / .contributing_run_ids[]
            │
        CampaignResult ──< Campaign (research_organization)
```

`find_by_project` / `find_by_workspace` already eager-load `Campaign → results → measurements`
(`lazy="selectin"`), so the run ids of a loaded campaign page are already in memory.

### 1. Read projection (chips data) — backend

- Add `targets: list[TargetRef]` to `CampaignResponse` (`interface/routes/_campaign_dtos.py`). It is a
  **derived, not-stored** field — the same shape as the existing `compound_sources`.
- New batched repository reader (in `campaign_repository.py`, mirroring `find_effective_targets`):
  given the page's campaigns, collect the distinct run ids from their measurements
  (`source_run_id` ∪ `contributing_run_ids`), run **one** query
  `SELECT run_id, target_id, <target fields> FROM run_targets JOIN targets WHERE run_id IN (…)`
  (workspace-scoped), and return `dict[campaign_id → list[TargetRef]]`, distinct per campaign and
  sorted by name.
- `ListCampaignsQuery` calls the existing list method, then the projection, and threads the map into
  `CampaignResponse.from_domain(campaign, targets=targets_by_campaign.get(campaign.id, []))`.
- Cost: **one extra query per page**, no N+1 (same lesson as the Phase-2 `member_ids` window query).

### 2. Filter (SQL, before pagination) — backend

- New `target_filter_subquery` mirroring the existing `tag_filter_subquery`: an `EXISTS` over
  `campaign → campaign_result → campaign_measurement → (source_run_id ∪ unnest(contributing_run_ids))
  → run_targets.target_id IN (selected)`, with a `match_all` flag for any/all.
- Applied inside `find_by_project` **and** `find_by_workspace`, **before** cursor pagination
  (identical placement to tag filtering).
- `GET /campaigns` gains `targets: list[uuid] | None = Query(None)` and
  `target_logic: Literal["any","all"] = Query("any")`, threaded through `ListCampaignsQuery` →
  repository, exactly like `tags` / `tag_logic`.

### 3. Frontend

- **Project campaign table** (`features/screen-campaign/components/campaign-list.tsx`): new "Targets"
  column rendering the existing `<TargetChips targets={c.targets} max={3} />` (em-dash when empty).
- **Target filter**: new `TargetFilter` component mirroring `TagFilter`
  (`{ targetIds: string[]; targetLogic: "any" | "all" }`; the any/all toggle appears only when
  >1 target selected), populated by the existing `useTargets` hook. Wired into
  `useCampaigns(projectId, { tags, tagLogic, targets, targetLogic })`.
- **Campaign detail header** (`features/screen-campaign/components/sections/header-strip.tsx`):
  render `<TargetChips>` (no filter).
- **Add-from-campaign picker** (`add-from-campaign-dialog.tsx`): chips only, to help pick by target.
  *Isolated / droppable task — lowest priority.*
- **Surface reality:** there is no standalone workspace-wide campaign list page (campaigns are only
  listed under a project + in the picker), so "all surfaces" = the four above. `find_by_workspace`
  still gets the filter param for parity/future use.

---

## Data flow (chips)

```
GET /campaigns?project_id=…[&targets=…&target_logic=…]
  → ListCampaignsQuery
      → campaign_repo.find_by_project(... targets, target_logic)   # filtered + paginated page
      → campaign_repo.project_targets(workspace_id, page_campaigns) # one batched query → map
  → CampaignResponse.from_domain(campaign, targets=map[campaign.id])
  → FE: <TargetChips targets={c.targets} />  +  <TargetFilter />
```

---

## Edge cases

- **Draft / empty campaign** (no measurements → no run ids) → empty `targets` → em-dash; excluded by
  any active target filter (the `EXISTS` fails). Same semantics as a runless protocol.
- **Measurement with `source_run_id = null`** but `contributing_run_ids` set → still contributes; both
  legs are unioned and deduped, in both the projection and the filter.
- **Shared target across runs** → deduped to one chip / one filter match.
- **Deleted target**: `run_targets` uses `ON DELETE RESTRICT` (migration 053), so a referenced target
  cannot vanish underneath the projection.

---

## Testing

**Backend**
- Repo projection: campaign with 2 runs / 3 targets (one shared) → 2 distinct `TargetRef`, sorted;
  campaign with no measurements → empty; `contributing_run_ids`-only measurement contributes.
- Filter subquery: `any` vs `all`; a counter-screen target matches (EXISTS semantics); a target on a
  run not in the campaign does not match.
- API: `CampaignResponse.targets` present; `?targets=&target_logic=` narrows the list correctly;
  pagination still works with the filter active.

**Frontend**
- `TargetFilter` unit (mirrors `TagFilter` tests): any/all toggle visibility, selection round-trip.
- Targets column renders `TargetChips` from `c.targets`; em-dash when empty.

---

## Performance notes

- Chips: one extra batched query per page (run ids already in memory from the eager-loaded aggregate).
- Filter: `EXISTS` uses `ix_run_targets_target` + `ix_campaign_measurement_source_run`. The
  `contributing_run_ids` array leg may warrant a GIN index **only if** filter latency proves to need
  it — do not pre-build (no silent cap; measure first).

---

## Exemplars to mirror

- Read-time union + provenance: `screening_assay/protocol_repository.py::find_effective_targets`.
- Tag filter subquery + any/all + pre-pagination placement: `research_organization/campaign_repository.py`
  (`tag_filter_subquery`, `find_by_project`).
- Derived not-stored DTO field: `CampaignResponse.compound_sources`.
- FE filter pattern: `features/tagging/components/tag-filter.tsx` (`TagFilterValue`, any/all toggle).
- FE chips: `features/screening-assay/components/target-chips.tsx`.
