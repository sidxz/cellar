# Research Organization Context

## Context Overview

Supporting subdomain for organizing research work — projects as logical groupings, compound collections for curation, saved searches for reproducible queries, and the electronic lab notebook for documenting experimental activities.

**Depends on:** Chemical Registration (molecule references), Screening & Assay (protocol/run references), Inventory (batch references), Workspace Config (Organization), Sentinel Auth (project access via entity ACLs)
**Depended on by:** Audit

---

## Aggregates

### Project

A logical grouping of related research work within a workspace — e.g., "EGFR Inhibitor Program", "COVID Antiviral Screen". Projects organize collections, protocols, runs, and ELN entries.

**Aggregate Root:** Project

**Inside boundary:** None.

**References (by ID):** Workspace (workspace_id)

**Access control:** Project access is managed via Sentinel's entity ACLs, not in Cellar. Each Project is registered as a resource in Sentinel (`service: "cellar", resource_type: "project"`). Cellar calls `auth.can("project", project_id, "view")` at query time.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| workspace_id | UUID | FK → Sentinel workspace |
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
| workspace_id | UUID | FK → Sentinel workspace |
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
| workspace_id | UUID | FK → Sentinel workspace |
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

A curated, per-compound pivot of screening results drawn from one or more Protocols / Runs. Campaigns produce an immutable artifact recording what was tested, what survived, and what was decided at a point in time. They drive the screening cascade by optionally emitting a frozen `Collection` of selected compounds for the next downstream campaign. Campaigns are the read contract for the DAIKON portfolio dashboard.

Full design spec: `docs/superpowers/specs/2026-05-10-screen-campaign-design.md`

**Aggregate Root:** Campaign

**Inside boundary:** CampaignChannel[], CampaignResult[], CampaignMeasurement[]

**References (by ID):** Project (project_id), Protocol (via channels), Collection (published_collection_id), User (created_by, closed_by), ElectronicSignature (signature_id), Campaign (supersedes_campaign_id, superseded_by_campaign_id)

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| workspace_id | UUID | FK → Sentinel workspace |
| project_id | UUID | FK → Project |
| name | string | Human-readable campaign name |
| description | text? | Optional free-text description |
| status | enum | `draft`, `closed`, `superseded` |
| compound_source | CompoundSource | Discriminated VO describing where compounds come from |
| publishes_collection | bool | Whether closing emits a frozen Collection |
| source_protocols | UUID[] | Snapshot of protocol_ids at close time (materialised from channels) |
| closed_at | timestamp? | Set when status → closed |
| closed_by | UUID? | FK → User who closed |
| signature_id | UUID? | FK → ElectronicSignature for close attestation |
| supersedes_campaign_id | UUID? | FK → Campaign this one replaces |
| superseded_by_campaign_id | UUID? | FK → Campaign that supersedes this one |
| published_collection_id | UUID? | FK → frozen Collection emitted on close |
| created_by | UUID | FK → User |
| created_at | timestamp | |
| updated_at | timestamp | |
| version | int | Optimistic-concurrency token |

#### CampaignChannel

An assay channel (one Protocol + one readout) that contributes a column of data to the Campaign pivot.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| campaign_id | UUID | FK → Campaign |
| protocol_id | UUID | FK → Protocol |
| readout_definition_id | UUID | FK → ReadoutDefinition within that Protocol |
| label | string | Display label for the column header |
| unit | string | Unit of measure (e.g. µM, %) |
| threshold | float? | Optional pass/fail threshold |
| z_prime | float? | QC metric — populated by ChannelResolver |
| display_order | int | Column ordering in the pivot view |

#### CampaignResult

One row in the Campaign pivot — one compound's aggregated results across all channels.

| Property | Type | Description |
|----------|------|-------------|
| id | UUID | |
| campaign_id | UUID | FK → Campaign |
| molecule_id | UUID | FK → Molecule |
| batch_id | UUID? | FK → Batch (most relevant batch) |
| decision | enum? | `selected`, `deprioritised`, `undecided` |
| notes | text? | Reviewer notes on the compound |

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

1. Only DRAFT campaigns are mutable — CLOSED and SUPERSEDED campaigns reject all mutating operations (enforced at domain layer and by a database trigger from migration 027 as defense-in-depth).
2. Closing requires at least one channel and at least one result.
3. Closing materialises the `source_protocols` snapshot from `campaign.channels[].protocol_id`.
4. Closing optionally emits a frozen `Collection` containing molecule_ids where `decision = SELECTED`, if `publishes_collection = True`.
5. Closed campaigns are NOT rewired on molecule merge; draft campaigns ARE (merge side-effect rewrites molecule_id references).
6. Manual-override measurements (`is_manual_override = True`) are preserved across re-resolve — the resolver skips those cells.
7. All channels are workspace-scoped via the parent Campaign's workspace_id.

#### State Transitions

```
draft ──[close + e-sig]──> closed
closed ──[supersede + e-sig]──> superseded
```

#### Domain Events

- `CampaignCreated` { project_id, name }
- `CampaignClosed` { closed_by, signature_id }
- `CampaignSuperseded` { superseded_by_campaign_id }
- `CampaignPublishedCollectionCreated` { collection_id }

#### Repository

`CampaignRepository` (protocol in `application/screening_campaign/`):

- `find_by_id_in_workspace(id, workspace_id) -> Campaign?`
- `find_by_project(project_id, workspace_id) -> list[Campaign]`
- `save(campaign) -> None` (insert or full reconciliation of owned entities)
- `is_locked(id) -> bool` (True when status is not DRAFT)

#### Persistence notes

- **Migration 027 DB trigger** — a PG trigger blocks any INSERT/UPDATE/DELETE on the `campaign` table (and its child entity tables) when `status != 'draft'`, providing defense-in-depth beyond the domain guard.
- **Non-deferrable unique index** on `(result_id, channel_id)` in `campaign_measurement` drives the id-preservation pattern: the SQL `INSERT … ON CONFLICT DO UPDATE` path in `SQLAlchemyCampaignRepository.save` matches existing measurements by this index, preserving their `id` so manual overrides survive re-resolve without a separate lookup table.
