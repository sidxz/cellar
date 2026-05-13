# Screen Campaign — Design Spec

**Status:** Draft (design only — implementation not started)
**Date:** 2026-05-10
**Bounded context:** `research_organization` (BC #05) — new aggregate alongside Project / Collection / SavedSearch / ELNEntry
**Out of scope for v1:** bulk import from external CSV bypassing Runs; cross-campaign SAR queries; DAIKON transport mechanism
**Plan:** `docs/superpowers/plans/2026-05-10-screen-campaign.md`

---

## 1. Purpose

A **Campaign** is a curated, immutable, per-compound pivot of screening results, drawn from one or more `Protocol` / `Run` records. It exists to:

1. Produce a frozen artifact that records "what was tested, what survived, what was decided" at a point in time.
2. Drive the screening cascade by emitting a **frozen `Collection`** of selected compounds, which feeds the next downstream campaign.
3. Serve as the read contract for the **DAIKON** portfolio dashboard, which renders the cascade DAG.

Campaigns answer questions like:
- "Show me all compounds tested under Protocol A with IC50 < 1 µM that we decided to advance."
- "Snapshot the full profile (IC50 from target binding, EC50 from cellular, % inh @ 10 µM) of these 50 leads, freeze it, and ship to DAIKON."

---

## 2. Aggregate Model

### `Campaign` (aggregate root)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `workspace_id` | UUID | |
| `project_id` | UUID | Required — campaigns belong to a project |
| `name` | string | |
| `description` | text? | |
| `status` | enum | `draft`, `closed`, `superseded` |
| `compound_source` | jsonb | Discriminated: see §2.5 |
| `publishes_collection` | bool | Default `true` — emit frozen Collection at close |
| `source_protocols` | jsonb | Materialized at close: `[{id, name, version, target_id, target_name}, …]` |
| `closed_at` | timestamp? | |
| `closed_by` | UUID? | FK → User |
| `signature_id` | UUID? | FK → ElectronicSignature |
| `supersedes_campaign_id` | UUID? | Self-reference |
| `superseded_by_campaign_id` | UUID? | Set when this campaign is itself superseded |
| `published_collection_id` | UUID? | FK → Collection — the frozen output |
| `version` | int | Optimistic concurrency |
| `created_at`, `created_by` | | |

### `CampaignChannel` (owned entity — one "column" in the snapshot)

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `campaign_id` | UUID | |
| `label` | string | e.g., "IC50 (target binding)" |
| `display_order` | int | |
| `protocol_id` | UUID | FK → Protocol. Identifies the specific version directly (no separate version field) |
| `readout_definition_id` | UUID | FK → ReadoutDefinition |
| `source_kind` | enum | `readout_data` \| `dose_response_curve` |
| `selection_rule` | enum | `latest_approved_run`, `mean_across_runs`, `geometric_mean`, `manual_pick` |
| `qc_filter` | jsonb? | e.g., `{min_z_prime: 0.5, require_approved: true}` |
| `hit_threshold` | `HitCriterion` VO? | Carried forward from protocol as a suggestion; channel owns its own copy thereafter |
| `qualifier_handling` | enum | `include_qualified`, `exclude_qualified`, `treat_as_limit` |

### `CampaignResult` (snapshot row — one per compound by default)

| Field | Type | Notes |
|---|---|---|
| `id`, `campaign_id`, `molecule_id` | | |
| `representative_batch_id` | UUID? | The batch picked (auto or manual) for this compound |
| `decision` | enum | `selected`, `deferred`, `rejected` (default `deferred`) |
| `decision_reason` | text? | |
| `notes` | text? | |

### `CampaignMeasurement` (one cell — owned by `CampaignResult`)

| Field | Type | Notes |
|---|---|---|
| `id`, `result_id`, `channel_id` | | |
| `value` | float? | Null if `nd` / no data |
| `value_qualifier` | enum | `=`, `<`, `>`, `nd`, `excluded` |
| `unit` | string | Denormalized from the readout definition |
| `hit_call` | enum? | `hit`, `miss`, `inconclusive`, null when no threshold |
| `is_manual_override` | bool | If true, this cell is not recomputed when channel rules change |
| `source_run_id`, `source_curve_id`, `source_readout_id` | UUIDs? | Traceability only — never re-read for the value |
| `protocol_name_snapshot` | string | |
| `protocol_version_snapshot` | int | |
| `run_date_snapshot` | date? | |

### 2.5 `compound_source` discriminator

```jsonc
// kind: explicit_list
{ "kind": "explicit_list", "molecule_ids": ["...", "..."] }

// kind: collection
{ "kind": "collection", "collection_id": "...", "seeded_at": "2026-05-10T..." }

// kind: saved_search
{ "kind": "saved_search", "saved_search_id": "...", "executed_at": "..." }

// kind: derived_from_campaign — the cascade arrow
{ "kind": "derived_from_campaign", "campaign_id": "...", "decision_filter": ["selected"] }
```

Re-seeding mid-draft is **destructive** — drops existing `CampaignResult` rows and re-creates from the new source. UI guard required.

---

## 3. Lifecycle

```
draft ──[close + e-sig]──> closed
closed ──[supersede + e-sig]──> superseded
        (new Campaign created with supersedes_campaign_id = this.id)
```

- **`draft`** — channels, results, measurements, source, decisions all mutable. Optimistic concurrency.
- **`closed`** — immutable via `CampaignLockGuard`. Optional PG trigger as defense-in-depth.
- **`superseded`** — same lock, plus `superseded_by_campaign_id` back-pointer.

**Close pre-conditions:**
- ≥ 1 `CampaignResult` row
- every Channel passes validation
- caller holds `cellar:campaign:close` capability (Sentinel)
- e-signature captured

**Cascade integrity is human-driven.** Superseding Campaign A does **not** auto-rewire downstream campaigns that seeded from A's derived Collection. DAIKON shows the supersession; re-running downstream is an explicit human decision.

**Domain events:**
`CampaignCreated`, `CampaignChannelChanged`, `CampaignResultsReseeded`, `CampaignClosed`, `CampaignSuperseded`, `CampaignPublishedCollectionCreated`.

---

## 4. Build-phase mechanics

### Compound seeding (draft creation or re-seed)

1. Resolve `compound_source` → molecule list.
2. Bulk-insert one `CampaignResult` per molecule with `decision = deferred`.
3. For each existing channel, resolve measurements (see below).

### Channel resolution `(channel, molecule) → CampaignMeasurement`

1. Find candidates: `ReadoutData` or `DoseResponseCurve` rows matching `(molecule_id, channel.protocol_id, channel.readout_definition_id)`.
2. Apply `qc_filter`.
3. Apply `selection_rule`.
4. Apply `qualifier_handling` to censored values.
5. Compute `hit_call` from `hit_threshold` if set.
6. Persist cell with `is_manual_override = false`, traceability FKs, and `_snapshot` columns.

Empty candidates → `value = null`, `value_qualifier = 'nd'`, `hit_call = null`.

### Recomputation triggers (background job, idempotent)

| Trigger | Action |
|---|---|
| Channel added | Resolve for all results, that channel only |
| Channel `selection_rule` / `qc_filter` / `hit_threshold` edited | Resolve for that channel × results where `is_manual_override = false` |
| Result added | Resolve for that result × all channels |
| Channel removed | Delete all measurements for that channel |
| Source data changed (Run unlocked + re-fitted) | **No auto-update.** Screener must explicitly "refresh from sources" |
| User clicks "refresh from sources" | Resolve for all channels × results where `is_manual_override = false`. Manual overrides preserved. |

### Manual edits in draft (set `is_manual_override = true`)

Cells with `is_manual_override = false` (the default — accepting the auto-resolution) remain subject to recompute. Only explicit user edits flip the flag.

- Override `representative_batch_id`.
- Hand-pick a specific run / curve for a cell.
- Set `value_qualifier = 'excluded'`.
- Edit `value` directly (rare — UI warns; preserved for parity with paper records).

---

## 5. Close, immutability, e-signature

### `CampaignLockGuard.guard_write(campaign_id)`

Mirror of `DataLockGuard`. Every repository method touching `campaign`, `campaign_channel`, `campaign_result`, `campaign_measurement` checks `Campaign.status`. If `closed` or `superseded`, returns `CampaignLockedError`. Single enforcement point.

### `CloseCampaignService`

1. Validate close pre-conditions (§3).
2. Capture `ElectronicSignature` via Audit context.
3. Re-resolve every cell where `is_manual_override = false` — guarantees the final canonical state.
4. Materialize `source_protocols` jsonb (distinct protocol_ids → `{id, name, version, target_*}`).
5. Set `status = closed`, `closed_at`, `closed_by`, `signature_id`.
6. If `publishes_collection = true`: build `Collection` with `is_frozen = true`, `derived_from_campaign_id = this.id`, name `"Hits — {campaign.name}"`, membership = `{result.molecule_id for result in results if result.decision == "selected"}`. Store `published_collection_id`.
7. Emit `CampaignClosed`. Write `AuditOperation`.

### `SupersedeCampaignService`

1. Caller provides a new `Campaign` (must already be `closed`).
2. Old campaign: `status = superseded`, `superseded_by_campaign_id = new.id`.
3. Old campaign's published Collection stays as-is (historical artifact).
4. Emit `CampaignSuperseded`. Audit operation written.

### Cross-context invariants

- **Closed campaigns are NOT rewired on molecule merge.** `CampaignResult.molecule_id` is preserved as it was at close. Reads can annotate "later merged into X"; the row stays put. Draft campaigns do rewire (matches `Collection` behavior).
- **`Collection.is_frozen`** (new field, default `false`): when `true`, all `add_molecule` / `remove_molecule` / `replace_members` operations reject with `CollectionFrozenError`. Pre-existing collections unaffected.
- **`Collection.derived_from_campaign_id`** (new field, nullable): links the frozen Collection back to its origin campaign.

---

## 6. DAIKON publishing surface

Stable read endpoint: `GET /api/campaigns/{id}/published`. Auth: standard workspace token (future: DAIKON service token). Returns one JSON document per closed campaign — the external contract.

```json
{
  "campaign": {
    "id": "...",
    "name": "...",
    "description": "...",
    "project": {"id": "...", "name": "..."},
    "status": "closed",
    "closed_at": "2026-05-10T...",
    "closed_by": {"id": "...", "name": "..."},
    "signature": {"id": "...", "signed_at": "..."},
    "supersedes_campaign_id": null,
    "superseded_by_campaign_id": null
  },
  "compound_source": {
    "kind": "derived_from_campaign",
    "ref": {"campaign_id": "...", "decision_filter": ["selected"]},
    "description": "Hits from primary screen XYZ"
  },
  "source_protocols": [
    {"id": "...", "name": "EGFR Binding Assay", "version": 3, "target": {"id": "...", "name": "EGFR"}}
  ],
  "channels": [
    {
      "id": "...",
      "label": "IC50 (target binding)",
      "display_order": 0,
      "protocol_ref": {"id": "...", "name": "...", "version": 3},
      "readout": {"id": "...", "name": "IC50", "unit": "nM", "data_type": "numeric"},
      "source_kind": "dose_response_curve",
      "selection_rule": "latest_approved_run",
      "qc_filter": {"min_z_prime": 0.5, "require_approved": true},
      "hit_threshold": {"readout_name": "IC50", "operator": "lt", "value": 1000}
    }
  ],
  "results": [
    {
      "molecule": {"id": "...", "primary_id": "CVT-000142", "name": "...", "structure_smiles": "..."},
      "representative_batch": {"id": "...", "name": "BAT-000171"},
      "decision": "selected",
      "decision_reason": "Best in series",
      "notes": "Watch hERG follow-up",
      "measurements": [
        {
          "channel_id": "...",
          "value": 42.0,
          "value_qualifier": "=",
          "unit": "nM",
          "hit_call": "hit",
          "is_manual_override": false,
          "source": {
            "run_id": "...",
            "run_date": "2026-05-01",
            "protocol_name": "EGFR Binding Assay",
            "protocol_version": 3
          }
        }
      ]
    }
  ],
  "published_collection": {"id": "...", "name": "Hits — EGFR Round 2", "size": 12}
}
```

**Pagination:** `?cursor=...&page_size=N` cursor over `results[]` for campaigns > 1k compounds. Top-level fields always returned.

**Caching:** ETag / Last-Modified keyed on `closed_at` (closed campaign = perfect cache key — immutable artifact).

**Transport** (webhook push vs. DAIKON pull, auth, service-token rotation): out of scope for v1. Contract is the artifact.

---

## 7. UI surface

Feature folder: `frontend/src/features/screen-campaign/`. Three screens.

1. **Campaign list (per project)** — table: name, status chip, channel count, compound count, closed_at. Row actions: view / resume draft.
2. **Campaign builder (draft)** — three-pane layout:
   - Left: compound list with add / remove / exclude.
   - Top: channel strip with per-channel "configure" popover.
   - Center: AG Grid pivot — rows = compounds, columns = channels, cells = value + qualifier + hit_call chip + manual-override indicator.
   - Right: per-row decision + notes panel.
   - Toolbar: re-seed, refresh from sources, close & sign.
3. **Campaign view (closed / superseded)** — read-only AG Grid, supersede action, "Published to DAIKON" indicator, JSON download.

Stack: AG Grid Community + TanStack Query + RHF + Ketcher (all in stack today). No new deps.

---

## 8. Persistence / migrations

New tables, all workspace-scoped, all with `version int` for optimistic concurrency:

- `campaign`
- `campaign_channel`
- `campaign_result`
- `campaign_measurement`

Modify `collection`:
- `is_frozen bool NOT NULL DEFAULT false`
- `derived_from_campaign_id UUID NULL`, FK → `campaign.id`

Indices:
- `campaign(workspace_id, project_id)`
- `campaign(supersedes_campaign_id)`
- `campaign_channel(campaign_id, display_order)`
- `campaign_result(campaign_id, molecule_id)` UNIQUE within `(campaign_id, molecule_id)` if `representative_batch_id` is rolled up to compound (v1 default).
- `campaign_measurement(result_id, channel_id)` UNIQUE
- `campaign_measurement(source_run_id)` — for "show all campaigns citing this run"

Single Alembic migration. Optional PG trigger on `campaign_result` / `campaign_measurement` blocking writes when parent `campaign.status ∈ ('closed','superseded')` — defense-in-depth.

---

## 9. Testing approach

Mirror existing test layout (`backend/tests/{unit,integration,api}`).

**Domain unit tests:**
- Channel resolution: `latest_approved_run`, `mean_across_runs`, `geometric_mean`, `manual_pick`.
- `qualifier_handling` variants.
- `hit_call` computation against `HitCriterion`.
- `is_manual_override` preserved under `selection_rule` / `qc_filter` / `hit_threshold` changes.
- Frozen Collection rejects mutations.
- `CampaignLockGuard` rejects writes for closed / superseded.
- Supersession invariants (back-pointer set, old campaign locked, downstream not rewired).

**Integration tests:**
- Full close flow with real `Run` + `ReadoutData` + `DoseResponseCurve` fixtures, e-sig path, published Collection creation.
- Re-seed destructive flow.
- Recomputation idempotency (run twice → same state).
- Molecule merge: rewires draft campaigns, does NOT rewire closed campaigns.
- Superseded campaign's published Collection retained.

**API tests:**
- `POST /campaigns` (draft).
- `PATCH /campaigns/{id}/channels`.
- `POST /campaigns/{id}/close`.
- `POST /campaigns/{id}/supersede`.
- `GET /campaigns/{id}/published` JSON schema validation.

**No E2E in this spec.** Frontend lives behind a feature flag during build-out.

---

## 10. Layered structure

Follows the cellar DDD layering exactly (`docs/patterns-and-conventions.md`).

- **Domain** (`backend/src/cellar/domain/research_organization/`):
  `campaign.py`, `campaign_channel.py`, `campaign_result.py`, `campaign_measurement.py`, `compound_source.py` (VO), `selection_rule.py` (enum), `campaign_lock_guard.py`, `events.py` (extended), `repository.py` (extended).
- **Application** (`backend/src/cellar/application/research_organization/`):
  `create_campaign.py`, `update_campaign_channel.py`, `reseed_campaign.py`, `recompute_channel.py`, `set_campaign_decision.py`, `close_campaign.py`, `supersede_campaign.py`, `get_published_campaign.py`.
- **Infrastructure** (`backend/src/cellar/infrastructure/persistence/sqlalchemy/`):
  ORM mappings, repository implementations, channel resolution query layer.
- **Interface** (`backend/src/cellar/interface/routes/`):
  `campaigns.py` — CRUD on drafts, close, supersede, publish endpoint.
- **Frontend** (`frontend/src/features/screen-campaign/`):
  list page, builder, view page; orval-generated types from the new OpenAPI surface.

---

## 11. Open follow-ups (post v1)

- DAIKON transport (webhook, service token rotation, replay).
- Cross-campaign SAR queries (SAR Analysis context).
- External CSV import path (Run-first today, direct import later if user demand emerges).
- Campaign templates (reusable channel sets — "the standard kinase panel").
- ELN entry auto-generation from closed campaign (currently handled via generic `LinkedEntityRef`).
