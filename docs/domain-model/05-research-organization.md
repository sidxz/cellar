# Research Organization Context

## Context Overview

Supporting subdomain for organizing research work — projects as logical groupings, compound collections for curation, saved searches for reproducible queries, and the electronic lab notebook for documenting experimental activities.

**Depends on:** Chemical Registration (molecule references), Screening & Assay (protocol/run references), Inventory (batch references), Workspace Config (Organization), Duar Auth (project access via entity ACLs)
**Depended on by:** Audit

---

**Cross-context link (S16, 2026-08-26):** Inventory `PlateGroup.collection_id` (optional, any tree level) points at a `Collection` as its physical realization. Collections stay abstract (membership = molecules); the plates, custody and storage live on the group side. `GET /collections/{id}/plate-groups` is the reverse read.

## Aggregates

### Project

A logical grouping of related research work within a workspace — e.g., "EGFR Inhibitor Program", "COVID Antiviral Screen". Projects organize collections, protocols, runs, and ELN entries.

**Aggregate Root:** Project

**Inside boundary:** None.

**References (by ID):** Workspace (workspace_id)

**Access control:** Project access is managed via Duar's entity ACLs, not in Cellar. Each Project is registered as a resource in Duar (`service: "cellar", resource_type: "project"`). Cellar calls `auth.can("project", project_id, "view")` at query time.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| workspace_id | UUID | FK → Duar workspace |
| name | string | |
| description | text? | |
| status | enum | `active`, `archived` |
| created_by | UUID | FK → User |
| created_at | timestamp | |

**Invariants:**
- Archived projects are read-only — no new entities can be linked to an archived project.
- Project names should be unique within a workspace.

**Domain Events:**
- `ProjectCreated` { project_id, name, workspace_id }
- `ProjectArchived` { project_id, archived_by }

---

### Collection (Library / Compound List)

A curated set of molecules for screening or analysis.

**Aggregate Root:** Collection

**Inside boundary:** molecule_ids[] (the membership set)

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| name | string | e.g., "Kinase Focused Library", "FDA Approved Drugs" |
| description | text? | |
| project_id | UUID? | FK → Project |
| owned_by_org_id | UUID? | FK → Organization (which org curated this) |
| molecule_ids | UUID[] | FK → Molecule (membership set) |
| created_by | UUID | FK → User |
| created_at | timestamp | |

**Invariants:**
- molecule_ids must reference active (non-tombstone) molecules. During merge, source molecule IDs are replaced with target molecule IDs (deduplicated).

**Persistence note:** Large collections (focused libraries) can contain 50,000+ molecules. At the persistence layer, use a join table (`collection_molecules`) rather than storing the UUID array inline. The aggregate interface should expose `add_molecule(id)`, `remove_molecule(id)`, `contains(id)`, `count()` — not expose the raw array. The `molecule_ids` field above represents the conceptual membership set, not a literal column.

**Domain Events:**
- `CollectionCreated` { collection_id, name, molecule_count }
- `CollectionMembersChanged` { collection_id, added_ids[], removed_ids[] }

---

### SavedSearch

**Aggregate Root:** SavedSearch

Stored query parameters for reproducible data retrieval. Has an independent lifecycle — not owned by any other aggregate.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| workspace_id | UUID | FK → Duar workspace |
| name | string | |
| project_id | UUID? | FK → Project |
| query | jsonb | Search criteria (structure, properties, activity ranges) |
| columns | jsonb? | Display column selection and ordering |
| visibility | enum | `private`, `project` |
| created_by | UUID | FK → User |

---

### ELNEntry (Electronic Lab Notebook)

**Aggregate Root:** ELNEntry

Unstructured documentation of research activities, linked to structured data across multiple contexts.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| workspace_id | UUID | FK → Duar workspace |
| project_id | UUID | FK → Project |
| title | string | |
| body | richtext/json | Structured content (text, tables, images, embeds) |
| template_id | UUID? | FK → ELNTemplate |
| status | enum | `draft`, `active`, `signed`, `archived` |
| author_id | UUID | FK → User |
| linked_entities | LinkedEntityRef[] | Cross-context entity references (see Value Objects) |
| created_at | timestamp | |
| updated_at | timestamp | |
| signed_at | timestamp? | |
| signed_by | UUID? | FK → User |

**Invariants:**
1. Once `status = signed`, the entry is immutable (like data locking on Run). Signing requires ElectronicSignature.
2. Linked entity references are resolved at read-time (cross-context references by ID).

**State Transitions:**
```
draft ──> active ──> signed
active ──> archived
signed ──> archived   (preserves signed state in audit trail)
```

**Domain Events:**
- `ELNEntrySigned` { entry_id, signed_by, signature_id }

---

### ELNTemplate

Reusable templates for standardized notebook entries. A configuration entity.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| name | string | e.g., "Synthesis Report", "Assay Results" |
| body | richtext/json | Template content with placeholders |
| created_by | UUID | FK → User |

---

### Campaign

A curated, per-compound pivot of screening results drawn from one or more Protocols / Runs, triaged through named **hit stages** — a funnel of AND-combined rules over the shared readout pool (e.g. Screening Hits → Confirmed Hits) — rather than one implicit per-readout hit flag. Campaigns produce a snapshot recording what was tested, what survived each stage, and what was decided at a point in time. Closing a campaign locks it read-only — no e-signature, no auto-published Collection — and a closed campaign can be reopened back to `draft` with a required reason, corrected, and closed again. Campaigns are the read contract for the DAIKON portfolio dashboard.

Full design spec: `docs/superpowers/specs/2026-05-10-screen-campaign-design.md`. Hit stages and soft close are specified in `docs/superpowers/specs/2026-09-11-campaign-hit-stages-and-soft-close-spec.md`, which supersedes that spec's §3 lifecycle, §5 close/e-signature, §6 published surface, and channel `hit_threshold`.

**Aggregate Root:** Campaign

**Inside boundary:** CampaignChannel[], CampaignResult[] (CampaignMeasurement[] and StageOverride{} owned per-result), CampaignStage[] (StageCriterion[] embedded per stage)

**References (by ID):** Project (project_id), Protocol (via channels), User (created_by, closed_by), Campaign (supersedes_campaign_id, superseded_by_campaign_id)

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| workspace_id | UUID | FK → Duar workspace |
| project_id | UUID | FK → Project |
| name | string | Human-readable campaign name |
| description | text? | Optional free-text description |
| status | enum | `draft`, `closed`, `superseded` |
| source_protocols | UUID[] | Snapshot of protocol_ids at close time (materialised from channels) |
| closed_at | timestamp? | Set when status → closed; cleared on reopen |
| closed_by | UUID? | FK → User who closed; cleared on reopen |
| close_note | text? | Optional note recorded at close; cleared on reopen |
| supersedes_campaign_id | UUID? | FK → Campaign this one replaces |
| superseded_by_campaign_id | UUID? | FK → Campaign that supersedes this one |
| created_by | UUID | FK → User |
| created_at | timestamp | |
| updated_at | timestamp | |
| version | int | Optimistic-concurrency token |

#### CampaignChannel

An assay channel (one Protocol + one readout) that contributes a column of data to the Campaign pivot. Channels no longer carry a hit rule — stages (below) define what counts as a hit.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| campaign_id | UUID | FK → Campaign |
| protocol_id | UUID | FK → Protocol |
| readout_definition_id | UUID | FK → ReadoutDefinition within that Protocol |
| label | string | Display label for the column header |
| unit | string | Unit of measure (e.g. µM, %) |
| normalization_applied | string? | Which normalization layer of the readout this channel reads (e.g. `percent_inhibition`); `None` = the raw layer. Meaningful only when `source_kind = READOUT_DATA` |
| intercept_key | string? | Which intercept of a dose-response curve this channel surfaces (e.g. `EC90`); `None` = the curve's primary intercept. Meaningful only when `source_kind = DOSE_RESPONSE_CURVE` |
| display_order | int | Column ordering in the pivot view |

#### CampaignResult

One row in the Campaign pivot — one compound's aggregated results across all channels.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| campaign_id | UUID | FK → Campaign |
| molecule_id | UUID | FK → Molecule |
| batch_id | UUID? | FK → Batch (most relevant batch) |
| decision | enum | `selected`, `deferred`, `rejected` |
| notes | text? | Reviewer notes on the compound |
| stage_overrides | map[UUID, StageOverride] | Manual per-stage hit/miss overrides, keyed by `stage_id` — see StageOverride below |

#### CampaignMeasurement

One cell in the Campaign pivot — a single channel value for a single compound. Owned by a CampaignResult.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| result_id | UUID | FK → CampaignResult |
| channel_id | UUID | FK → CampaignChannel |
| value_numeric | float? | Numeric measurement value |
| value_qualifier | string? | Qualifier prefix: `<`, `>`, `~` |
| value_text | string? | Text value when not numeric (e.g. ND) |
| unit | string | Unit (must not be empty — use `"-"` only as a placeholder for ND cells) |
| is_manual_override | bool | True if a reviewer manually set this value (preserved across re-resolve) |
| source_readout_data_ids | UUID[] | Source ReadoutData rows used by ChannelResolver |

Hit/miss is no longer stored on the cell. It is computed per (result, stage) by Stage evaluation, below, and is never persisted.

#### CampaignStage

A named, ordered AND-combination of rules over the campaign's channels — the unit of the hit-triage funnel (e.g. "Screening Hits" → "Confirmed Hits"). Stages don't own channels: any stage may reference any channel, including the same readout with a different cutoff in a later stage. Owned by Campaign; mutable only while the campaign is `draft`.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| campaign_id | UUID | FK → Campaign |
| name | string | Trimmed, non-empty, ≤ 120 chars; unique per campaign, case-insensitive |
| parent_stage_id | UUID? | FK → CampaignStage in the same campaign; optional — see Stage evaluation |
| display_order | int | ≥ 0; new stages append at max + 1 |
| criteria | StageCriterion[] | 0–10 criteria. A stage with zero criteria passes its whole population — a scaffold state, flagged in the UI as "no criteria yet" |

**Invariants:**
- Every `criteria[].channel_id` must be a channel of the same campaign; removing a channel strips any criterion referencing it from every stage.
- `parent_stage_id` must name a stage of the same campaign, may not be the stage itself, and may not create a cycle (checked by walking the parent chain up from the proposed parent).
- A stage that is another stage's parent cannot be removed (`ConflictError`) until its children are removed first. Removing a stage also clears every result's `StageOverride` for it.

#### StageCriterion

Frozen value object — one AND-ed rule inside a `CampaignStage`.

| Property | Type | Description |
|----------|------|-------------|
| channel_id | UUID | FK → CampaignChannel; must belong to the same campaign |
| operator | string | One of `lt`, `lte`, `gt`, `gte`, `between` — unlike `HitCriterion`, the string-based `in` operator is not accepted |
| value | float \| [float, float] | Numeric for the four comparisons; `[low, high]` with `low <= high` for `between` |

`is_met(value)` delegates to the shared `domain.shared.hit_criterion.compare(operator, value, target)` function — one comparison implementation reused by both `StageCriterion` and `HitCriterion` (still used by run-import filtering and protocol recommendations). Duplicate criteria on the same channel within one stage are allowed (equivalent to a `between`, expressed as two bounds).

#### StageOverride

Frozen value object, owned by `CampaignResult` and keyed by `stage_id` — a manual, audited promote/demote of one compound's outcome for one stage.

| Property | Type | Description |
|----------|------|-------------|
| result_id | UUID | FK → CampaignResult (the owning result) |
| stage_id | UUID | FK → CampaignStage |
| forced_outcome | enum | `hit` or `miss` only |
| reason | string | Required, non-empty |
| overridden_by | UUID | FK → User |
| overridden_at | timestamp | UTC |

`CampaignResult.stage_overrides` is a `dict[stage_id, StageOverride]`. `set_stage_override(...)` replaces any existing override for the stage; `clear_stage_override(stage_id)` removes one.

#### Stage evaluation

Pure, unpersisted computation (`domain/research_organization/stage_evaluation.py::evaluate_stages`), recomputed on every read from the live campaign, results, and stages — nothing here is written to the database.

Per (result, stage), stages are visited parents-first (the parent links form a forest, so this always terminates):

1. **Population.** A root stage (no parent) evaluates every result. A child stage evaluates only compounds whose parent's *final* outcome (after any override) is `hit`; every other compound is `not_in_stage`, with no checks recorded.
2. **Checks.** For a result in play, each criterion is checked against the result's measurement on its channel: a missing measurement, an `nd`/`excluded` qualifier, or a `None` value all read as `untested`; otherwise the check is `pass`/`fail` from `StageCriterion.is_met`. Censored values (`<`, `>` qualifiers) compare by their plain numeric value — the same simplification the pre-stages hit-call logic used.
3. **Combine (AND).** Any `fail` → `miss`; else any `untested` → `untested`; else `hit`.
4. **Override.** A `StageOverride` on the result for this stage replaces the computed outcome with its `forced_outcome` (`overridden = true`) — even when the computed outcome was `not_in_stage`, so a forced hit pulls the compound into the stage's own population and into its children's evaluation.

| Outcome | Meaning |
|---------|---------|
| `hit` | All criteria passed, or overridden to hit |
| `miss` | At least one criterion failed, or overridden to miss |
| `untested` | In the stage's population but missing data for at least one criterion, with none failing |
| `not_in_stage` | Excluded by the parent chain (not a hit on the parent) and not overridden in |

Funnel counts (`tally_stage_counts`) read `population = hit + miss + untested` (for a root stage, every result) alongside `not_in_stage` and an `overridden` tally — e.g. "of 12 screening hits: 7 hit, 3 miss, 2 untested."

#### CompoundSource

Discriminated value object describing where Campaign compounds come from. One of:

| Kind | Fields | Notes |
|------|--------|-------|
| `ExplicitListSource` | `molecule_ids: UUID[]` | Manually curated set |
| `CollectionSource` | `collection_id: UUID` | Members of a Collection at resolve time |
| `DerivedFromCampaignSource` | `campaign_id: UUID`, `decisions: enum[]` | Compounds from a prior Campaign filtered by decision |
| `SavedSearchSource` | `saved_search_id: UUID` | Executes a SavedSearch at resolve time (not yet wired in v1 — rejects with ValidationError) |

---

#### Invariants

1. Only DRAFT campaigns are mutable — CLOSED and SUPERSEDED campaigns reject all mutating operations (enforced at the domain layer and by a database trigger from migration 027, extended by migration 074 to cover stages and overrides, as defense-in-depth).
2. Closing requires at least one channel and at least one result.
3. Closing materialises the `source_protocols` snapshot from `campaign.channels[].protocol_id`.
4. Reopening a closed campaign requires a non-empty reason, returns status to `draft`, and clears `closed_at` / `closed_by` / `close_note`. Superseded campaigns cannot be reopened.
5. Closed campaigns are NOT rewired on molecule merge; draft campaigns ARE (merge side-effect rewrites molecule_id references).
6. Manual-override measurements (`is_manual_override = True`) are preserved across re-resolve — the resolver skips those cells.
7. All channels are workspace-scoped via the parent Campaign's workspace_id.

#### Lifecycle

Statuses stay `draft → closed → superseded`, plus a `closed → draft` reopen edge:

| Action | From → To | Input | Notes |
|--------|-----------|-------|-------|
| Close | `draft → closed` | `note: string?` | Requires ≥ 1 result and ≥ 1 channel; snapshots `source_protocols`; no signature, no published Collection |
| Reopen | `closed → draft` | `reason: string` (required) | Clears `closed_at`, `closed_by`, `close_note`; emits `CampaignReopened` |
| Supersede | `closed → superseded` | — | Unchanged. Superseded is terminal — a superseded campaign cannot be reopened |

`closed` still means read-only: writes to results, measurements, stages, and stage overrides are rejected by the domain guard (`Campaign._ensure_draft`), the application-layer `CampaignLockGuard` (raises `DataLockedError` → HTTP 423), and a database trigger (migration 027, extended by 074 for the two new tables) as defense-in-depth. Close and reopen are each recorded as a domain event (`CampaignClosed`, `CampaignReopened`) for the audit trail; there is no dedicated reopen/close history view beyond that trail.

#### State Transitions

```
draft ──[close]──> closed
closed ──[supersede]──> superseded
closed ──[reopen]──> draft
```

#### Domain Events

- `CampaignCreated` { project_id, name }
- `CampaignClosed` { closed_by, note }
- `CampaignReopened` { reopened_by, reason }
- `CampaignSuperseded` { superseded_by_campaign_id }

#### Repository

`CampaignRepository` (protocol in `application/screening_campaign/`):

- `find_by_id_in_workspace(id, workspace_id) -> Campaign?`
- `find_by_project(project_id, workspace_id) -> list[Campaign]`
- `save(campaign) -> None` (insert or full reconciliation of owned entities)
- `is_locked(id) -> bool` (True when status is not DRAFT)

#### Persistence notes

- **Migration 027 DB trigger** (extended by migration 074 to cover `campaign_stage` / `campaign_stage_override`) — a PG trigger blocks any INSERT/UPDATE/DELETE on the `campaign` table (and its child entity tables) when `status` is not `draft`, providing defense-in-depth beyond the domain guard.
- **Non-deferrable unique index** on `(result_id, channel_id)` in `campaign_measurement` drives the id-preservation pattern: the SQL `INSERT … ON CONFLICT DO UPDATE` path in `SQLAlchemyCampaignRepository.save` matches existing measurements by this index, preserving their `id` so manual overrides survive re-resolve without a separate lookup table.
- **Stages and overrides reconcile the same way as channels/measurements** — `campaign_stage` rows are matched by `id` (ordered by `display_order`, cascade delete-orphan), `campaign_stage_override` rows by `(result_id, stage_id)` — both on `Campaign.save`, no dedicated stage repository.
