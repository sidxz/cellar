# Spec: Plate Tracker Revamp — Strict Org Visibility, Legacy-Parity Tree, Comments, Kiosk Page, Full Data Cutover

**Date:** 2026-08-25 · **Status:** APPROVED 2026-08-25 · S7 + S8 + S9 shipped 2026-08-25 (branch `feat/plate-tracker-revamp`)
**Contexts touched:** Inventory (03), Audit & Compliance (06), Workspace Config (07)
**Builds on:** `2026-08-10-inventory-plate-org-loans-spec.md` (S1–S6, shipped). Sessions here continue the numbering: **S7–S12**.

## 1. Context

S1–S6 ported the legacy PHP plate tracker's *mechanics* (org ownership, loans with a real state machine, group hierarchy, kiosk API, insights, migration script). A second look against the legacy app (`~/workspace/legacy/intranet/web-files/sacnet/{apps,sn-admin/apps}/plate-tracker`, React viewer source `~/workspace/archive/react/plate-tracker`) and against the current intranet MySQL (`~/workspace/legacy/intranet/db`, database `sacnet_dev`, restored 2026-08-23) found what is still missing or worse than legacy:

| Gap | Legacy | Cellar today |
|---|---|---|
| Tree information density | vertical elbow tree, state-colored circles, HTML node cards (type-colored header, format, scientist, location, initial vol/conc, compound count) with **View / Checkout** actions, one library at a time, `initialDepth 5` | horizontal, 10 px circles, two text lines, all roots expanded |
| Group metadata | set carries state / format / location / vol / conc / scientist / compound count | `PlateGroup` has name / type / description only; migration squashes the rest into description |
| Comments | mandatory per-set comment at check-in + free comments on a transaction; 56 k activity rows | one `notes` string per loan; no feed anywhere |
| Kiosk | scan page | API only (S5); no page |
| Visibility | n/a (no orgs) | browse-all default with per-org opt-in privacy; **no admin bypass** |
| Audit | activity rows name the scientist | every plate/group/loan audit row is `SYSTEM` / nil actor (events carry no `user_id`) |
| Data | 2 259 plates, 84 sets, 17 libraries, 760 transactions (8 open), 1 258 set/plate comments | saclab-dev holds almost no plates; S6 script only *matches* plates, never creates them; closed history deliberately not migrated |

## 2. Resolved decisions (2026-08-25)

| Decision | Answer |
|---|---|
| Visibility | **Strict only.** An org sees its own plates + plates currently on loan to it. Workspace admins see everything. The `plates_private` toggle is deleted. |
| "Shared" | = on loan. No separate visibility-grant concept. |
| Tree | Mirror the legacy look (vertical, cards, one root at a time). Keep Cellar's side panel for CRUD. |
| Group metadata | First-class fields on `PlateGroup`. |
| Comments | In scope: append-only feed on loan / group / plate; mandatory per-group comment on return request. |
| Kiosk page | In scope, minimal. |
| Emails | **Out.** |
| Closed history | **Migrate** (closed transactions → closed loans; human comments → feed). |
| Target env | saclab-dev; the migration must **create** plates. All legacy data is owned by the **TAMU** org. |
| Source DB | the live `intranet-db` MySQL 8 container (`docker compose up intranet-db` in `~/workspace/legacy/intranet`, db `sacnet_dev`) — not the Oct-2024 dump. |

## 3. Visibility (S7)

Single enforcement point stays `application/inventory/plate_visibility.py`. Only the *computation* of the excluded set changes; every caller keeps its `excluded` plumbing.

```python
async def excluded_org_ids(self, workspace_id, auth) -> set[UUID]:
    if auth is None or auth.is_admin:
        return set()                                    # system calls + admins: nothing hidden
    all_ids = {o.id for o in await self._directory.list_orgs()}
    return all_ids - {auth.org_id}
```

- `OrgDirectory` (`infrastructure/duar/org_directory.py`, 5-min per-process cache) is injected in place of the policy repo. A directory failure **fails closed** (propagates → 503). `# ponytail:` an inclusion-scope refactor (`visible_owner_org_id: UUID | None`) would drop the directory dependency; do it only if the directory ever becomes unreliable.
- Plates with `owner_org_id IS NULL` remain visible to everyone (pre-S2 semantics; none exist after the S11 backfill).
- Borrowed-plate READ carve-out, hidden == 404 on plate/loan reads, 403 on org-scoped reads (tree, insights) for a foreign org — all unchanged. Admins now pass the 403 gates because their excluded set is empty.
- **Delete `plates_private`**: `OrgPlatePolicy` field, `org_plate_policies.plates_private` column (migration **066**), `OrgPlatePolicyRepository.list_private_org_ids`, DTO/body field, FE switch, and the "private-org" test fixtures. `OrgPlatePolicy` keeps `require_approval` / `confirmation` / `default_due_days`.
- FE: the org `<Select>` on Plates list, Plate Groups, Insights, and the `ALL_ORGS` filter option render **only when `me.is_admin`**; non-admins are pinned to `me.org_id`. Loans "All" tab stays (already filtered by `_loan_visible`).
- Orgs **disabled** in Duar stay excluded (the visibility directory instance is fetched with `include_disabled`); an org **deleted** from Duar is a known residual (its plates would become visible) until the inclusion-scope refactor — `docs/backlog/plate-visibility-inclusion-scope-refactor.md`. A directory failure surfaces as **503** (`ServiceUnavailableError`); Duar reachability from the backend is on the plate read path.

### 3.1 Owner-initiated lending (added 2026-08-25, user decision)

Strict visibility means a borrower org cannot see — and therefore cannot request — another org's plates. Cross-org loans are created by the **owner** org: `POST /api/v1/plate-loans` gains optional `borrower_org_id`. Omitted or equal to the caller's org → the existing borrower-initiated request. Different → an owner-initiated lend: allowed only when the caller is a workspace admin or every requested plate belongs to the caller's org; the borrower org must exist in the org directory (422 otherwise); items are approved on creation by the lender (`approved_by` = caller, `PlateLoanItemsApproved` emitted) and, when the owner policy's confirmation mode is `none`, go straight to `checked_out`. FE: the loan request dialog gets a "Borrower organization" select (default = my organization / self-checkout) and the primary button reads **Lend** when a foreign org is chosen. Borrower-initiated requests of hidden plates by barcode were rejected (barcode-probing oracle). The **owner org may cancel** items it has not handed over yet (`REQUESTED`/`APPROVED`) with the same authority as approving — a mis-lend is retractable by the lender; borrower cancel authority is unchanged (final-review ruling R7).

## 4. Audit actor (S7)

Root cause: `DomainEvent` has no `user_id`; `AuditRecordingService.handle_event` reads `getattr(event, "user_id", UUID(int=0))` and hardcodes `ActorType.SYSTEM`.

Fix at the shared layer, once:
- New `application/shared/actor_context.py`: `current_actor_id: ContextVar[UUID | None]` + `set_current_actor(user_id)` / `current_actor()`.
- `interface/dependencies/_core.py:187` (where `bind_user_context` is already called from `get_auth`) also calls `set_current_actor(auth.user_id)`.
- `handle_event`: `user_id = getattr(event, "user_id", None) or current_actor()`; `actor_type = USER if user_id else SYSTEM`; nil UUID only when neither exists. Events that already carry `user_id` (screening, research-org) are unaffected.
- Kiosk scans have no actor → stay SYSTEM (correct — device attribution is `last_seen_at`).
- FE `ENTITY_TYPE_OPTIONS` (`features/audit/components/audit-list.tsx`) gains `RegisteredPlate`, `PlateGroup`, `PlateLoan` (exact `aggregate_type` strings).

## 5. PlateGroup metadata (S8)

New optional fields on `PlateGroup` (domain + `plate_groups` columns, migration **067**):

| Field | Type | Notes |
|---|---|---|
| `state` | `str \| None` (≤ 50) | UI suggestions from CV `plate_group_state`; FE fallback `["Dry", "Solubilized", "Retired"]`. Not domain-validated (same stance as `group_type`). |
| `storage_location_id` | `UUID \| None` | FK `storage_locations.id`, `ON DELETE SET NULL`. |
| `initial_volume_ul` | `Decimal \| None` | `Numeric(10,2)`, ≥ 0 |
| `initial_concentration_mm` | `Decimal \| None` | `Numeric(10,2)`, ≥ 0 |
| `compound_count` | `int \| None` | ≥ 0 |
| `scientist` | `str \| None` (≤ 200) | Free-text display name. `# ponytail: text; upgrade to a member user_id when a by-id member lookup exists.` |

- `create()` / `update()` accept all six (update with the existing `...` sentinel convention). `PlateGroupUpdated` unchanged.
- **Derived, not stored:** `plate_format` per node = `"96"` / `"384"` / `"mixed"` / `null` from member plates — `array_agg(DISTINCT format)` added to the existing `count_plates_by_group` query. `created_at` exposed on the tree node.
- DTOs: `GroupTreeNodeResponse`, `PlateGroupResponse`, `CreatePlateGroupBody`, `UpdatePlateGroupBody` gain the fields (+ `plate_format`, `created_at` on responses). orval regen in the same change.
- The migration script's `seed_group_type_vocab` also seeds `plate_group_state` from legacy `set_state` values (verbatim casing). FE color maps normalize with `toLowerCase()`.

## 6. Tree (S8) — `frontend/src/features/inventory/components/plate-group-tree.tsx` rewrite

react-d3-tree 3.6 (already installed). Legacy parity items, each concrete:

| Aspect | Value |
|---|---|
| Orientation / paths | `vertical`, `pathFunc="elbow"` |
| Depth / zoom | `initialDepth={5}`, `zoom={0.7}`, `scaleExtent={{min: 0.1, max: 1.5}}`, `zoomable`, `collapsible` |
| Spacing | `nodeSize={{x: 320, y: 260}}`; translate `{x: width/2, y: 60}` (measured once from the container) |
| Root scope | **one root group at a time.** Root `<Select>` in the header (the legacy library picker); selection remembered in `localStorage` key `plate-groups.root.<orgId>` (try/catch); default = remembered else first root by name. No synthetic "All groups" node. Org `<Select>` remains, admin-only (§3). |
| Node circle | `r=25` (root `r=30`); fill = **state** color: solubilized `#7AB648`, dry `#99D2F2`, retired → `fill-muted` stroke only, unset → `CHART_COLORS.neutral`. Click / Enter / Space → `toggleNode()` (unchanged). |
| Node card | `<foreignObject x=30 y=-20 width=280 height=200>` → `div.bg-card.border.rounded` with a header bar colored by **type** (`TYPE_COLORS`: vendor `#FFBD50`, screening `#8F7EB5`, master_twin `#C3D9E4`, hit_collection `#E27D60`; other types → existing djb2 hash palette; keys lower-cased), name (bold, `title` = full name), type chip. Rows (skip when null): `{format}-well · {scientist}`, location name (`useStorageLocations()` lookup, same as plate detail), `Initial: {vol} µL, {conc} mM`, `{compound_count} compounds`, `{plate_count} plate(s)`, `created {date}`. `title` on the card = description. Card click / Enter → `onSelect(node)`. |
| Card actions | **Details** → `onSelect` (opens the existing side panel). **Request loan** (only when `plate_count > 0`) → opens `RequestLoanDialog` pre-set to group mode with this group. |
| Legend | two rows: states present (fixed colors + "unset") and types present (fixed/hash colors). |
| Memoization | `data` memoized on `[tree, rootId]` (tree resets expand state on identity change — existing rule). |
| Layout | replace `h-[calc(100vh-12rem)]` with a flex `min-h-0 flex-1` slot from `plate-group-dashboard.tsx` (closes `docs/backlog/plate-groups-tree-viewport-overflow-baseline.md`). |

Side panel (`plate-group-details.tsx`) shows the six fields; `plate-group-dialog.tsx` edits them: State `<Select>` (`useVocabularyTerms("plate_group_state")` + fallback), Location `<Select>` (`useStorageLocations()`, `__none__` sentinel — same pattern as `register-plate-dialog.tsx`), three numeric inputs, Scientist text. Explicit Save (no autosave).

## 7. Comments (S9)

### 7.1 Domain — `domain/inventory/comment.py`

```
Comment (entity, append-only)
  id, workspace_id
  target_type: CommentTarget = plate_loan | plate_group | plate
  target_id: UUID
  loan_id: UUID | None      # context link: a group/plate comment made during a loan carries the loan
  body: str (1..5000, stripped)
  author_id: UUID | None    # None only for migrated legacy authors
  author_name: str (≤200)   # denormalized at write time
  created_at
```

No update/delete (legacy had none; audit alignment). `Comment.create(...)` emits `CommentAdded(user_id=author_id, target_type, target_id, loan_id)`.

### 7.2 Persistence — migration **068**

Table `plate_comments` (Entity + Workspace mixins, no version): columns above; `target_type` String(20); indexes `(workspace_id, target_type, target_id, created_at)` and `(workspace_id, loan_id)`. No FK on `target_id` (polymorphic), FK on `loan_id → plate_loans.id ON DELETE SET NULL`.

### 7.3 Application

- `AuthContext` protocol gains `name: str` and `email: str` (Duar `RequestAuth` already has them; `/me` reads them via `getattr`). Sweep **all** structural implementers: `FakeAuth`, export `_AuthShim`, any test stubs (memory: protocol wideners must sweep every implementer).
- `AddComment(target_type, target_id, loan_id?, body)`: `require_authenticated` → `require_editor` → load target and apply the existing visibility predicate for that type (plate: `can_view` with borrowed set; group: `can_view_owner`; loan: `_loan_visible`) — hidden == 404; if `loan_id` given it must be visible too and, for group/plate targets, actually contain the target. Author = `auth.user_id` / `auth.name or auth.email`.
- `ListComments(target_type, target_id)` and `ListComments(loan_id=…)`: viewer + same visibility; newest first; no pagination (`# ponytail:` add cursor when a target exceeds a few hundred comments).
- `RequestReturn` (existing `items:request-return`) body gains `comments: list[{group_id, body}]` and optional `plate_comments: list[{plate_id, body}]`. Server rule: for every distinct non-null `group_id` among the plates whose items are being return-requested, a non-empty `comments` entry must exist → else `ValidationError` (422) listing the missing group names. Comments are written in the same UoW as the state change, each with `loan_id` set. Kiosk `confirm` and admin `confirm-in` are untouched (no mandatory comment — matches legacy override behavior).

### 7.4 API

- `GET /api/v1/comments?target_type=&target_id=` · `GET /api/v1/comments?loan_id=` → `list[CommentResponse{id, target_type, target_id, loan_id, body, author_id, author_name, created_at}]`
- `POST /api/v1/comments` `{target_type, target_id, loan_id?, body}` → 201 `CommentResponse`
- `POST /api/v1/plate-loans/{id}/items:request-return` `{item_ids?, comments: [{group_id, body}], plate_comments?: [{plate_id, body}]}`

### 7.5 Frontend

- `CommentFeed` component (`features/inventory/components/comment-feed.tsx`): props `{target: {type, id}} | {loanId}`; list (author_name, `formatDateTime`, body) newest first + "Add comment" textarea/button (hidden for viewers). Placements: **LoanCard** (collapsible "Comments (n)"), **group side panel** ("Comments" section — the group's comments across loans; each entry with a `loan_id` links to `/inventory/loans#…`), **plate detail** ("Comments" card).
- **Request return** on LoanCard becomes `RequestReturnDialog`: one required textarea per distinct group among the selected (or all eligible) items, labeled with the group name and its plate barcodes; an optional per-plate expander; submits the extended body. Zero-group loans submit with an empty `comments` list.

## 8. Kiosk page (S10)

`frontend/src/app/kiosk/page.tsx` — outside `(dashboard)`, therefore no `AuthzGuard`, no app chrome. `customInstance` with `headers: {"X-Kiosk-Token": token}` (caller headers win; unauthenticated pages add no Duar headers).

- **Token screen** (no token in `localStorage["kiosk.token"]`): one password input + Save. A small "Change device" link on the scan screen returns here.
- **Scan screen**: "Ready to scan" + autofocused text input (`autocomplete=off`); Enter → `POST /kiosk/scan {barcode}` → on success **immediately** `POST /kiosk/confirm {loan_id, item_id}` (one scan = one action, as legacy). Result overlays: green "Checked out" / "Checked in" with plate label, borrower org, due date, auto-clears after 3 s; red with the server `detail` (404 → "Plate not recognized for this device's organization", 409 → message) auto-clears after 5 s; 403 → clear the stored token and show the token screen. Input disabled while a request is in flight; refocused after every result.
- Not built: legacy's post-scan "plate status" table (a kiosk token cannot read loans). Add if asked.

## 9. Migration v2 (S11) — `backend/scripts/migrate_legacy_plate_tracker.py`

Same script, same shape: functional core → apply phases in **one** `AsyncUnitOfWork`, `--dry-run` = rollback, CSV reports either way. New/changed behavior:

| # | Phase | Change |
|---|---|---|
| 0 | args | `--legacy-dsn mysql://…@127.0.0.1:3306/sacnet_dev`, `--internal-org-id` = TAMU, new `--site-name` / `--building-name` (storage roots), `--user-map` now **optional**. |
| 1 | storage | Site → Building → Room `{room_no}` → Freezer `{freezer}` from `APPS_PLATE_TRACKER_LOCATION` (`UNKNOWN/UNKNOWN` → null). Idempotent by name-under-parent. |
| 2 | plates | unmatched legacy plates are **created**: `RegisteredPlate.register(barcode=verbatim, plate_label=plate_name, format = plate's (Invalid → its set's → 96), plate_type by role, registered_by=actor, owner_org_id=TAMU, storage_location_id = its set's location)`, then status/tag as today (`Inactive` → `DEPLETED` + `legacy:inactive`). When `cdd_plate_id` is set, `CddPlateSyncRepository.bulk_upsert({cdd_plate_id, plate_id})` under `--cdd-vault-id` so a later CDD plate import merges instead of duplicating. |
| 3 | groups | libraries/sets → groups as today, plus §5 fields from `SET`: `state=set_state`, location, `initial_volume`, `initial_concentration`, `compound_count=no_of_compounds`, `scientist` = legacy account first+last name; `generating_conditions` / `compound_file` / `comments` folded into `description`. Seeds `plate_group_type` **and** `plate_group_state` CVs. |
| 4 | open loans | unchanged (8 open transactions, 53 plates). |
| 5 | closed history | each `CLOSED` transaction → `PlateLoan(owner=borrower=TAMU, requested_by = user-map hit or `--actor-id`, due = created + 14 d, status CLOSED)`. Items reconstructed from the system lines: plate name parsed from `"(System Generated Comment) Plate <name> has been {approved…\|approved for check-in…\|scanned out…\|scanned back in…\|denied.}"` (every closed transaction has them — verified); final item status `returned` (scanned back / closed by override) or `denied`; `status_changed_at` / loan `created_at` / `closed_at` from `act_date` (written with a post-save UPDATE since the repo does not map `created_at`). `notes = "Legacy transaction <id> · requester: <name>"` — also the idempotency marker (transactions whose marker already exists are skipped). |
| 6 | comments | non-system `ACTIVITY_LOG` rows (≈ 1 300): `SET_CMT` → `plate_group` target (strip `"[SET] <name> : "`), `PLATE_CMT` → `plate` target (strip `"[PLATE] <name> : "`), human `T_CMT`/`T_REQ_CMT` → `plate_loan` target; all with `loan_id` = the migrated loan for that `transaction_id`, `author_id` = user-map hit or null, `author_name` from `account`, `created_at = act_date`. |
| 7 | reports | existing CSVs + `created_plates.csv`, `closed_loans_unparsed.csv` (any system line the parser rejects — expected empty), summary counters for each phase. |

Unit tests cover the new pure functions (format fallback, system-line parser, comment prefix stripping, closed-loan reconstruction); the mandatory dry-run remains the integration gate.

## 10. Cutover (S12, operator + agent)

1. `cd ~/workspace/legacy/intranet && docker compose up -d intranet-db` (already up during this design; `sacnet_dev` data current to 2026-08-23).
2. Tunnel to saclab-dev Postgres; export `DATABASE_URL` for the script; confirm alembic head ≥ 068 there.
3. Build `user_map.csv` for the 6 open-transaction requesters (all `@tamu.edu`, emails in legacy `account`) — optional for the rest.
4. `uv run python scripts/migrate_legacy_plate_tracker.py --dry-run …` → review `unmatched_plates.csv` (expected ≈ 0 now), `closed_loans_unparsed.csv` (expected empty), counters (≈ 2 259 plates, 101 groups, 8 open + 752 closed loans, ≈ 1 300 comments).
5. Real run; spot-check in the UI: tree for SAC1, a closed loan's history + comments, a kiosk scan on a dev device.
6. Update tracking issue, memory, backlog; record deviations in a sync note at the end of this file.

## 11. Out of scope (deliberate)

Emails/notifications · volume-reduction editor (never persisted in legacy) · vendor / `SET_VENDOR` tables (write-only in legacy) · well tables (empty in prod) · per-library CDD mappers (generic DataSource import) · printing · plate-level `initial_conc`/`initial_vol` (12 non-zero rows) · a kiosk status table · comment edit/delete · a "share without loan" grant.

## 12. Session plan (layer order per CLAUDE.md; each session = its own plan under `docs/superpowers/plans/`)

| Session | Scope | Migrations |
|---|---|---|
| **S7** | strict visibility + admin bypass, delete `plates_private`, admin-only org selectors, actor ContextVar + audit fix, audit entity filter | 066 |
| **S8** | `PlateGroup` metadata fields + derived format, tree rewrite, root selector, legend, group dialog/panel fields, viewport fix, CV `plate_group_state` | 067 |
| **S9** | `Comment` entity + repo + use cases + routes, `AuthContext.name/email` widener, request-return comment rule, `CommentFeed`, `RequestReturnDialog` | 068 |
| **S10** | `/kiosk` page | — |
| **S11** | migration v2 (storage, plate creation + `cdd_plate_sync`, group metadata, closed history, comments, reports) + unit tests | — |
| **S12** | dry-run + real cutover on saclab-dev, docs/memory/issue updates | — |

## S7 sync note (2026-08-25) — shipped reality vs. §3/§3.1/§4

- Excluded set is computed from `OrgDirectoryPort` (`application/shared/org_directory.py`, satisfied by the Duar `OrgDirectory`) resolved via the Lagom container (`register_core`, guarded so `create_container(overrides={OrgDirectoryPort: stub})` wins in tests); the `/api/v1/orgs` route still uses the interface-layer `OrgDirectory` singleton — two instances, two 5-min caches (ponytail-marked in `infrastructure/di/_core.py`).
- `PlateVisibilityService()` with no directory is legal for `auth=None`/admin callers (Temporal worker, admin-only integration test) and raises `RuntimeError` otherwise; a directory HTTP failure propagates as a 500 rather than the 503 written in §3 — still fail-closed.
- Migration 066 drops `plates_private`; `PUT /org-plate-policies/{org}` returns 422 if a client still sends it (regression test).
- **§3.1 owner-initiated lending shipped in the same session** (`borrower_org_id` on `POST /plate-loans`; borrower validated against the directory; auto-approved by the lender; FE "Borrower organization" select + **Lend** button). Cross-org loan test scaffolding uses an admin scoped to the borrower org where a `requested` loan is needed.
- Audit actor precedence: `event.user_id` (non-nil) → request `current_actor()` (ContextVar set in `get_auth`) → nil/SYSTEM. Kiosk and worker paths stay SYSTEM by design. The API test app does not subscribe the audit catch-all; `TestAuditActor` wires it with class-scoped fixtures, and a ContextVar-setting dependency override must be `async def` (sync deps run on a threadpool Context copy).
- FE: org selectors on Plates / Plate Groups (+Insights) and the Org Policies button render only for `me.is_admin` (gated in both the error-state and normal renders of the plate list); audit filter gained `RegisteredPlate` / `PlateGroup` / `PlateLoan`.
- Test-harness deviations: `test_children_exclude_foreign_org_child` restructured stricter (children listing gates on parent visibility); hidden-plate tests use `editor_client_own_org`; the stub org directory now lists `abbvie`/`tamu`/`partner`.
- Environment: `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock` is required for testcontainers on this Mac; lint gates are scoped to touched files because repo-wide `pnpm lint`/ruff are red on `main` (backlog).
- Full backend suite at the end of S7: 3873 passed / 11 failed, all pre-existing (`docs/backlog/preexisting-test-lint-failures-main.md`, now also listing `test_molecules.py`).

## S8 sync note (2026-08-25) — shipped reality vs. §5/§6

- Measurements are `float` / SQLAlchemy `Float` (inventory convention — `batches.amount_value`, `samples.concentration_value`), not the `Numeric(10,2)` written in §5 (ruling R8). Limits as specified: state ≤ 50, scientist ≤ 200, volume/concentration/compound_count ≥ 0; blank strings → NULL.
- `plate_format` is derived per tree node from `array_agg(DISTINCT registered_plates.format)` (`plate_formats_by_group`, org-scoped like the count query) via `derive_format` (`None` / single value / `"mixed"`); `created_at` is exposed on group + tree-node responses. Migration **067** (`067_plate_group_metadata`, FK `fk_plate_groups_storage_location` ON DELETE SET NULL).
- `plate_group_state` vocabulary: seeded by the legacy migration script (generalized `seed_vocab`); a fresh workspace relies on the FE fallback `["Dry", "Solubilized", "Retired"]` until an admin creates the vocabulary.
- Tree: root selection lives in the dashboard header (`localStorage` key `plate-groups.root.<orgId>`, try/catch), the tree view takes a single `root`; cards are a `<foreignObject>` `PlateGroupCard` (type-colored header with fixed dark text; unknown types use the hash palette); the viewport overflow was fixed by recalibrating the fixed offset to `16.25rem` (ruling R9; backlog `plate-groups-tree-viewport-overflow-baseline.md` closed and deleted) rather than a flex-slot refactor; browser-verified scroll overflow 0 at 1600×900.
- `RequestLoanDialog` gained `initialGroupId` so a card's "Request loan" opens in group mode pre-selected.
- Review follow-ups (fix wave `1e1dc585..d5c90b3f`): `storage_location_id` on group create/update is validated against the workspace (404 when missing; the identical pre-existing gap on plates is `docs/backlog/plate-storage-location-unvalidated.md`); `Retired` has its own swatch (`#94a3b8`); numeric body fields reject NaN/±Inf (`allow_inf_nan=False`) and an app-wide `RequestValidationError` handler now sanitizes non-finite floats before echoing (FastAPI's default 500'd on them); `pickRoot`, the card and the loan-dialog preselect are unit-tested; the viewport backlog item is reopened as "stopgap applied, flex-slot refactor still open".
- Suites at the end of S8: backend 3896 passed / 11 pre-existing failures; frontend 1029/1029; tsc clean.

## S9 sync note (2026-08-25) — shipped reality vs. §7

- `Comment` keeps a `version` column (never bumped) so it rides the generic `SQLAlchemyRepository` (ruling R13). Migration **068** `plate_comments`; `loan_id` FK ON DELETE SET NULL; `target_id` has no FK (polymorphic, same stance as `plate_loan_items.plate_id`).
- A comment posted directly on a loan is stored with `loan_id = target_id`, so the loan feed (`?loan_id=`) lists loan, group and plate comments made in that loan's context in one query.
- `POST /plate-loans/{id}/items:request-return` has its own `RequestReturnBody` (`item_ids?`, `comments[{group_id, body}]`, `plate_comments[{plate_id, body}]`); the other five verbs keep the shared `extra=forbid` body (R14). Enforcement lives in `_LoanItemsUseCase._validate` (before the state change) and the comments are written in `_after_save` inside the same unit of work (R16). Ungrouped plates need no comment, so existing clients sending `{}` keep working.
- `LoanItemResponse` gained `group_id`/`group_name` (R15) through one batched `enrich_loans(plate_repo, group_repo)` shared by `GetLoan`, `ListLoans` and every verb — a borrower cannot browse the owner's tree under strict visibility, so the loan itself carries the labels the return dialog needs.
- Plate-target comment reads AND writes use the borrowed carve-out (R17) — the documented exception to `plate_visibility.py`'s write narrowing; group and loan targets use `can_view_owner` / `_loan_visible`.
- `AuthContext` gained `name`/`email` (implementers swept: `FakeAuth`, export `_AuthShim`); `/me` reads them directly.
- FE: `CommentFeed` (`scope` = target or loan context, `composerTarget` decides where a new comment posts) on the loan card (collapsible, lists the loan context, posts to the loan), the group side panel and the plate detail; `RequestReturnDialog` gates submission on one non-blank note per group and sends optional per-plate notes; `useLoanItemsAction` invalidates the comments query.
- Suites at the end of S9: backend 3927 passed / 11 pre-existing failures; frontend 1045/1045; tsc clean. Browser E2E (request → approve → confirm-out → return with notes) passed.

