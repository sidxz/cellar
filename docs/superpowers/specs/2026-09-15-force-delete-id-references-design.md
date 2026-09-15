# Force delete: references without an FK — design

**Date:** 2026-09-15
**Status:** approved in chat 2026-09-15 (user: "looks good"); D1–D6 at the recommended defaults, D7 added while writing this spec
**Builds on:** `docs/backlog/admin-force-delete-protocol-dangling-refs.md` (handoff); analysis page https://claude.ai/artifact/RPgv7TFHNAG59RFvpjZZma (private)
**Verified against:** `main` at `13eb5c17`, dev DB at migration 080

---

## 0. What the analysis established

- **The runner can already act on id-only columns.** `CascadeRunner` filters on `child.<fk_column> IN (parent ids)` and never reads FK metadata (`infrastructure/cascade/cascade_runner.py:263-314`). The rule files skip non-FK columns instead ("rule removed"). New mechanism is needed only for references inside JSON, arrays, polymorphic links, and state-conditional references.
- **Tier 1 and the coverage test only see ForeignKeys.** The Tier-1 blocker scan (`inbound_refs.py:45-82`) and `tests/unit/cascade/test_fk_coverage.py:381-388` walk SQLAlchemy ForeignKeys, so a new id-only reference is never flagged.
- **The preview under-reports.** It recurses into 5 samples per level (`SAMPLE_LIMIT`, `cascade_runner.py:29,93-109`), while execute walks every row. The dialog's Confirm ignores block nodes (`frontend/src/shared/components/cascade-delete-dialog.tsx:100,143`).
- **Molecule force delete fails for every CDD-synced molecule.** `cdd_molecule_sync.molecule_id` is an FK with NO ACTION and no rule, so the final DELETE returns 409 (`persistence/unit_of_work.py:98-111`). Dev has 50,391 sync rows. Two things hide it:
  - The `IGNORED_FKS` entry misspells the table as `cdd_molecule_syncs`.
  - The test treats any FK into a Tier-1 table as covered, but force delete doesn't use Tier-1 RESTRICT.
- **A second NO ACTION FK sits under a leaf.** `merge_events.disclosure_request_id` points at `disclosure_requests`, whose rules are never walked because its cascade rule doesn't recurse.
- **Set-null writes no audit entry** (`cascade_runner.py:204-209,299-301`).
- **Closed and superseded campaigns aren't self-contained.**
  - They resolve protocol, readout and molecule labels live (`get_published_campaign.py:310-342,395-408`).
  - Row-lock triggers reject writes to their results, measurements, stages and stage overrides (migrations 027 and 074).
- **Refitting a run re-creates curves for a deleted molecule.** The fitter regroups `readout_data` by `(molecule_id, batch_id)` without an existence check (`fit_dose_response.py:274,331-375`).
- **Every run holds its data.** `readout_data.run_id` and `dose_response_curves.run_id` are NOT NULL, so "runs holding data for X" covers every measurement row.
- **Dev has no orphans for any in-scope reference, with one exception.** `campaign_measurement.source_curve_id` (44) and `source_readout_id` (24) already dangle. Each has a newer curve or readout in the same run, so refits and recomputes cause them, not deletes.

## 1. Decisions

| # | Question | Decision |
|---|---|---|
| D1 | Molecule with screening data or a campaign row | **Refuse.** The way out is a merge, or force-deleting the runs deliberately. |
| D2 | Draft campaigns | **Block** on channels and result rows, which users can remove. **Warn** on seed runs and measurement sources, which no operation removes and which re-resolve on the next refresh. Closed and superseded campaigns block on everything they cite. |
| D3 | CDD sync ledger row | **Deleted with the molecule** and audited. CDD stays the source, so a later sync may re-import the molecule, and the preview says so. No migration. |
| D4 | Files behind cascaded attachment rows | **Stay in storage.** The audit snapshot keeps `storage_key`. |
| D5 | Scope | Protocol, run and molecule force delete, including the tables those deletes remove, plus Tier-1 blocking for the same parents. Tier-1-only parents and non-admin delete paths are parked (§9). |
| D6 | Guard test | Classifies every uuid column without an FK **and** every JSON column. |
| D7 | Tier 1 and warn rules (added at spec time) | **Tier 1 refuses while any rule matches, warn included.** Tier 1 has no preview to show a warning, and RESTRICT already blocks on FK children whatever their ondelete. |

## 2. Outcome principles

Every in-scope reference gets exactly one outcome.

- **Block — never alter a frozen result.** Anything a closed or superseded campaign cites.
- **Block — never pull data out of a run.** Measurements that name the molecule or its batches.
- **Block — name a live link someone can clear:** draft campaign channels and rows, open requests, plate well maps, import-template defaults.
- **Cascade — rows that mean nothing without the target.** Compound flags, attachment rows, merged tombstones, finished requests, CDD sync rows. Each is snapshotted into the audit operation.
- **Set null — an optional pointer.** Only where "none" is a valid state; audited per row.
- **Leave — records and snapshots that carry their own labels.** Warn instead where a draft's provenance re-resolves on its own.

## 3. Engine (`backend/src/cellar/infrastructure/cascade/`)

### 3.1 `CascadeRule`

```python
Match = Callable[[Table, Sequence[uuid.UUID]], ColumnElement[bool]]

@dataclass(frozen=True)
class CascadeRule:
    child_table: str
    parent_table: str
    action: CascadeAction
    fk_column: str | None = None        # column on child_table holding the parent id
    match: Match | None = None          # predicate when the reference isn't a plain column
    covers: tuple[str, ...] = ()        # "table.column" references a match rule accounts for
    label_field: str | None = None
    display_label: str = ""
    recurse_into_entity: str | None = None
```

- **Validation (`__post_init__`):**
  - Exactly one of `fk_column` and `match` is set.
  - A `match` rule has a non-empty `covers`.
  - `set_null` requires `fk_column`.
- **`rule.where(table, ids)`** returns `table.c[fk_column].in_(ids)`, or `match(table, ids)`.
- **`rule.references`** returns `(f"{child_table}.{fk_column}",)`, or `covers`.
- **Workspace filter:** it still applies to `child_table` exactly as today.
- **Call sites:** every existing rule, and `tests/unit/infrastructure/cascade/test_registry.py`, uses keyword arguments, so no call site changes.
- **Docstrings:** the module docstrings in `rules.py` and each `rules_<context>.py` stop saying rules are FK edges. Rules describe references, FK or not.

### 3.2 One plan walk

`CascadeRunner.plan(parent_table, parent_id, workspace_id) -> CascadePlan` returns:

- **`deletes`:** `list[tuple[str, list[UUID]]]`, shallow-first. Apply reverses it, as today.
- **`nulls`:** `list[tuple[str, str, list[tuple[UUID, UUID]]]]`, where each entry is `(table, column, [(row_id, old_value)])`.
- **`blockers` and `warnings`:** `list[InboundReference]`, one entry per rule. Each entry counts the distinct matching rows across the whole walk, with up to 5 labelled samples.

How the walk behaves:

- **It evaluates rules for every collected id.** Samples are for display only.
- **It never revisits a `(table, id)`.** This matters for self-referencing cascades such as merged tombstones.
- **Every null is applied before any delete**, which keeps NO ACTION FKs safe whatever the delete order; a row the delete also removes gets no UPDATE audit entry, because its DELETE snapshot already holds the old value.
- **Id lists bind as one `uuid[]` parameter** (`column = ANY(:ids)`, helper `any_id` in `rules.py`). `IN (...)` binds one parameter per id, and asyncpg refuses more than 32,767 of them; one 384-well protocol with 86 plates already passes that. Checked on the dev DB: 40,000 ids fail through `IN` and pass as an array. The current runner uses `IN` everywhere, so large force deletes fail today.

### 3.3 Preview

- **The tree is unchanged but narrower.** It is built as today, from `cascade` and `set_null` rules only.
- **Blocks and warnings move out of the tree.** They come from `plan()` instead.
- **`CascadePreview` returns `CascadePreviewResult(root, blockers, warnings)`**; it currently returns a `CascadeNode`.

### 3.4 Execute

`execute` calls `plan()`, then:

- **If there are blockers,** it raises `CascadeBlockedError(blockers)`, which replaces `CascadeExecutionError`. `CascadeDelete` returns `Failure(BlockedByDependenciesError(blockers))`, so the refusal is a 409 carrying the Tier-1 body.
- **Otherwise it snapshots and applies**, all in the caller's transaction, so an audit failure still rolls everything back:
  - **Deleted rows:** one DELETE entry each, as today.
  - **Nulled rows:** one UPDATE entry each, with `field_name` = column, `old_value` = previous id, `new_value` = None — except a row the delete also removes, which gets no UPDATE entry (its DELETE snapshot already holds the old value).
  - **Apply order:** every null before any delete, then deletes deepest-first, then the root.

### 3.5 Tier 1

- **Rule blockers:** `find_inbound_references` keeps its FK walk. It then adds one `InboundReference` for each rule registered on the parent, whatever the rule's action (D7). It skips rules whose `references` are an FK to that parent, because the FK walk already counted those.
- **`InboundReference` gains `display_label: str | None = None`.** FK blockers leave it `None`.

## 4. Rules

"Shows" is what the admin sees in the blocker or tree node. Every child table listed carries `workspace_id`.

### protocols

| Id | Action | Shows | Matches when | Label | Display label | Covers |
|---|---|---|---|---|---|---|
| P1 | block | `campaign` | a channel's `protocol_id` is the protocol, or its `readout_definition_id` is one of the protocol's readout definitions; any campaign state | `name` | Campaigns with a channel on this protocol | `campaign_channel.protocol_id`, `campaign_channel.readout_definition_id` |
| P2 | block | `import_templates` | `default_protocol_id` | `name` | Plate import templates defaulting to this protocol | (fk_column) |
| P3 | cascade | `compound_flags` | `protocol_id` | — | Compound flags | (fk_column) |
| P4 | cascade | `attachments` | `attachable_type = 'protocol'` and `attachable_id` | `file_name` | Attachments (files stay in storage) | `attachments.attachable_id` |

### runs (also walked for a protocol's runs)

| Id | Action | Shows | Matches when | Label | Display label | Covers |
|---|---|---|---|---|---|---|
| R1 | block | `campaign` | `status <> 'draft'`, and a `seed_runs` entry's `run_id`, or a measurement's `source_run_id` or `contributing_run_ids`, names the run | `name` | Closed or superseded campaigns citing this run | `campaign.seed_runs`, `campaign_measurement.source_run_id`, `campaign_measurement.contributing_run_ids` |
| R2 | warn | `campaign` | same, with `status = 'draft'` | `name` | Draft campaigns using this run (their cells re-resolve without it on the next refresh) | same |
| R3 | cascade | `attachments` | `attachable_type = 'run'` | `file_name` | Attachments (files stay in storage) | `attachments.attachable_id` |

`<> 'draft'` is deliberate: any future non-draft state blocks by default.

### molecules

| Id | Action | Shows | Matches when | Label | Display label | Covers |
|---|---|---|---|---|---|---|
| M1 | block | `runs` | a `readout_data` row or curve of the run has the molecule | `run_date` | Runs with data for this molecule | `readout_data.molecule_id`, `dose_response_curves.molecule_id` |
| M2 | block | `campaign` | a result row has the molecule; any state | `name` | Campaigns with a row for this molecule | `campaign_result.molecule_id` |
| M3 | block | `synthesis_requests` | `molecule_id`, status not in fulfilled, rejected, cancelled, failed | `purpose` | Open synthesis requests (cancel or fulfil them first) | `synthesis_requests.molecule_id` |
| M4 | cascade | `synthesis_requests` | `molecule_id`, status in those four | `purpose` | Finished synthesis requests | same |
| M5 | block | `sample_requests` | `molecule_id`, status not in fulfilled, rejected, cancelled | `purpose` | Open sample requests (cancel them first) | `sample_requests.molecule_id` |
| M6 | cascade | `sample_requests` | `molecule_id`, status in those three | `purpose` | Finished sample requests | same |
| M7 | cascade | `compound_flags` | `molecule_id` | — | Compound flags | (fk_column) |
| M8 | cascade, recurse `molecule` | `molecules` | `merged_into_id` | `registration_number` | Merged registrations (tombstones) | (fk_column) |
| M9 | cascade | `attachments` | `attachable_type = 'molecule'` | `file_name` | Attachments (files stay in storage) | `attachments.attachable_id` |
| M10 | set_null | `reaction_steps` | `product_molecule_id` | — | Reaction steps (product link cleared) | (fk_column) |
| M11 | cascade | `cdd_molecule_sync` | `molecule_id` (real FK) | — | CDD sync records (a later CDD sync may re-import this molecule) | (fk_column) |

The open/finished split mirrors merge, which refuses while sample requests are active (`merge_handlers.py:249-280`). "Not in terminal" is the fail-safe form of that rule.

### batches (walked for a molecule's batches)

| Id | Action | Shows | Matches when | Label | Display label | Covers |
|---|---|---|---|---|---|---|
| B1 | block | `runs` | a well (through its plate), `readout_data` row or curve of the run has the batch | `run_date` | Runs with data for this molecule's batches | `wells.batch_id`, `readout_data.batch_id`, `dose_response_curves.batch_id` |
| B2 | block | `registered_plates` | an entry in the `well_map` object has the batch as `batch_id` | `barcode` | Inventory plates holding these batches | `registered_plates.well_map` |
| B3 | cascade | `attachments` | `attachable_type = 'batch'` | `file_name` | Attachments (files stay in storage) | `attachments.attachable_id` |
| B4 | set_null | `sample_requests` | `batch_id` | `purpose` | Sample requests (preferred batch cleared) | (fk_column) |
| B5 | set_null | `reaction_steps` | `batch_id` | — | Reaction steps (batch link cleared) | (fk_column) |

M1 and B1 can both name the same run; each line stays accurate, so they aren't merged.

### disclosure_requests (now walked)

- **Existing rule:** the `disclosure_requests.molecule_id` cascade rule gains `recurse_into_entity="disclosure_request"`.
- **DR1:** set_null on `merge_events.disclosure_request_id`, display label "Merge events (disclosure link cleared)".

### Left alone (no rule; each listed in `LEFT_ALONE` with its reason)

- **Snapshots:** `campaign.source_protocols`, `campaign_measurement.curve_snapshot` and `campaign_result.added_from` carry their own labels.
- **Stale provenance:** `campaign_measurement.source_curve_id` and `source_readout_id` are already replaced by every refit or recompute, and charts draw from the snapshot.
- **Never written:** `campaign_result.representative_batch_id`, `plates.parent_plate_id` and `plates.template_id`.
- **Names only:** `plates.plate_map` holds names, no ids.
- **Import log:** `bulk_registration_items.molecule_id` and `.batch_id` sit on rows that store the name and registration number.
- **Records of what happened:** `synthesis_requests.fulfilled_batch_id`, `sample_requests.fulfilled_sample_id` and `shipment_items.item_id`.
- **Chemistry snapshots and steps:**
  - `merge_events.snapshot` holds strings.
  - `reaction_steps.reagents` isn't rendered.
  - `reaction_steps.preceding_step_ids` is deleted with its route.
- **Always deleted together:** `readout_data.well_id` goes with its wells.
- **Filters on a missing id match nothing, and pruning them would widen results:** `saved_searches.query`, `saved_searches.columns` and `export_jobs.query_snapshot`.
- **Caches:**
  - `sar_activity_projections.channel_spec`, `sar_activity_values.molecule_id` and `sar_activity_values.snapshot` go stale for a separate reason, parked in §9.
  - `rgroup_assignments.molecule_id`, `scaffold_tree_jobs.result_json` and `umap_jobs.*` are keyed on membership and recompute.
- **JSON configs that reference definitions by name:** `runs.hit_criteria`, `runs.conditions`, `protocols.recommended_hit_criteria`, `readout_definitions.dose_response_config`, `readout_definitions.normalizations`, `run_import_templates.column_mapping` and `dose_response_curves.dose_response_config_snapshot`.
- **Import-template mappings:** when a template defaults to the protocol, P2 blocks first. The other case is parked with unchecked writers (§9).
- **Audit:** `audit_entries.entity_id` and `audit_operations.entity_id` are append-only by design.
- **Everything else:** external identity (Duar users, orgs, workspaces), or a parent that force delete never removes, with the backlog file named in the reason.

## 5. FK-side fixes

- **M11:** add the rule and delete the misspelled `("cdd_molecule_syncs", "molecule_id", "molecules")` entry from `IGNORED_FKS`.
- **DR1:** add it, together with recursion on disclosure requests.
- **Stale entries:** delete four `IGNORED_FKS` entries that name columns which no longer exist: `registered_plates.run_id` (the link is `plates.registered_plate_id`), `batches.storage_location_id`, `protocols.target_id` (now the `protocol_targets` table) and the misspelled `cdd_molecule_syncs.molecule_id`.
- **Model imports:** the coverage test loads every module under `infrastructure/persistence/sqlalchemy` instead of a hand-kept list, so a new model's columns can't escape classification. The existing FK test still passes with the full set (checked).

## 6. Guard tests (`tests/unit/cascade/test_fk_coverage.py`)

1. **Id-only references are classified.** This covers every `Uuid` or `ARRAY(Uuid)` column in `Base.metadata` without a ForeignKey (ignoring `id`, `workspace_id`, `created_by` and `updated_by`), and every JSON or JSONB column. Each must appear in some rule's `references`, or in `LEFT_ALONE: dict[str, str]` (`"table.column"` → reason). On failure, the message lists the unclassified columns and both fixes.
2. **Every FK into a force-deleted table is handled.**
   - Walk from each Tier-2 root (`protocols`, `runs`, `molecules`) through cascade rules to find the tables removed and the tables whose rules get consulted.
   - Every FK into a removed table needs either a rule on a consulted parent or a DB ondelete of CASCADE or SET NULL.
   - This replaces the `TIER1_PARENT_TABLES` shortcut for those tables; the shortcut stays for Tier-1-only parents.
3. **No stale keys.** Every `LEFT_ALONE` and `IGNORED_FKS` key names an existing table and column, which catches the `cdd_molecule_syncs` kind of typo.

## 7. API and frontend

- **Preview endpoint:** `POST /api/v1/admin/{entity_type}/{entity_id}/cascade-preview` returns `CascadePreviewResponse`. That is `CascadeNodeResponse` plus `blockers` and `warnings`, both `list[BlockerPayload]`. Additive at the top level.
- **Blocker payload:** `BlockerPayload` gains `display_label: str | None`, and the Tier-1 409 body carries it too. Additive.
- **Delete endpoint:** `DELETE /api/v1/admin/{entity_type}/{entity_id}/cascade` refuses with 409 and the Tier-1 body, instead of 422 "Blocking rule fired".
- **Types:** regenerate orval (`pnpm generate:api`, backend up), and revert files whose only change is the OpenAPI version stamp.
- **`cascade-delete-dialog.tsx`:**
  - Blockers and warnings appear above the confirm fields, each with display label, count and sample labels.
  - While blockers exist, Confirm is disabled and the copy says to resolve them first.
  - A 409 at execute means a reference appeared after the preview. The dialog shows the returned blockers (via `getDeleteBlockedError`) and refetches the preview.
  - The blocker list becomes one component shared with `admin-delete-button.tsx`.
- **Daikon: unaffected.** It calls campaign endpoints only (`daikon-gen3/src/daikon/contexts/integration/screening_runs.py`), so no notice is needed.

## 8. Tests

**Integration** (`tests/integration/cascade/`, testcontainers at alembic head):
- **Protocol:**
  - A draft campaign has a channel on it: the preview lists the campaign, execute returns the blockers, nothing is deleted.
  - An import template defaults to it: blocked.
  - It has compound flags and an attachment: both are deleted, with DELETE audit entries.
- **Run:**
  - It seeds a closed campaign: blocked.
  - It seeds a draft campaign: warning only. The delete proceeds and `seed_runs` is untouched.
  - A closed campaign cites the protocol's 6th run: the protocol preview lists it and execute refuses. This proves the walk is exhaustive.
- **Molecule:**
  - With readout data: blocked.
  - With a campaign row: blocked.
  - With an open sample request: blocked. With a finished one: deleted.
  - A batch in a plate well map: blocked.
  - A merged tombstone: deleted.
  - A CDD sync row: deleted, no 409.
  - A reaction-step product link: nulled, with an UPDATE audit entry.
- **Set-null audit** on an existing FK rule (successor protocol lineage): an UPDATE entry.
- **Tier 1:** a protocol whose only reference is a compound flag returns a 409 naming it.
- **Bind cap:** a protocol delete whose run has 33,000 wells.

**API** (`tests/api/test_admin_delete.py`): the preview returns `blockers` and `warnings`, and a blocked cascade delete returns the 409 body.

**Unit:** `CascadeRule` validation.

**Frontend** (vitest):
- Confirm is disabled while blockers exist.
- Warnings render.
- A 409 at execute renders its blockers.

## 9. Parked (backlog files written with this spec)

| File | What |
|---|---|
| `docs/backlog/non-admin-deletes-leave-id-references.md` | `DeleteRun` checks no campaigns; plate-template, draft route, draft request and step deletes leave pointers |
| `docs/backlog/tier1-only-parents-id-references.md` | Plate templates, projects, synthesis routes and requests, config referenced by name; Tier 1 skips the normal deletes' guards |
| `docs/backlog/sar-activity-projection-cache-no-data-version.md` | Cache key has no data version; stale after deletes, refits and re-imports |
| `docs/backlog/scaffold-tree-cache-no-workspace-filter.md` | Cache lookup matches `ids_hash` alone |
| `docs/backlog/writers-accept-unchecked-ids.md` | Campaign, readout, curve and synthesis-route writers take ids without checking them |
| `docs/backlog/campaign-reopen-reclose-rewrites-cells.md` | Re-close re-resolves every cell; close nulls three measurement fields |
| `docs/backlog/model-db-fk-drift.md` | Two FKs declared only in models; one only in the DB |
| `docs/backlog/run-force-delete-confirmation-name.md` | Typed confirmation uses nullable `runs.notes` |
| `docs/backlog/collection-freeze-unused.md` (appended) | Collection header links to `/campaigns/{id}`, a route that doesn't exist |

## 10. Delivery

- **Branch:** one branch, `feat/force-delete-id-references`, with this spec as its first commit.
- **Review:** one whole-branch review at the end.
- **Migration:** none.
- **Order:**
  1. Engine: rule validation, plan walk, set-null audit, array-bound ids.
  2. Tier 1.
  3. Rules and guard tests.
  4. API.
  5. Dialog.
