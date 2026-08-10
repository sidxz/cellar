# Spec: Inventory Plates — Org Ownership, Loans, Groups & Insights (Legacy Plate Tracker Port)

**Date:** 2026-08-10 · **Status:** DRAFT — awaiting user review
**Contexts touched:** Inventory (03), Workspace Config (07), Sentinel boundary (08) + identity-service repo

## 1. Context

Replaces the legacy PHP plate tracker (`~/workspace/legacy/intranet/web-files/sacnet/{apps,sn-admin/apps}/plate-tracker` + `batch/plate-tracker`). Cellar already covers: plate registry (richer statuses/formats), well maps with real Batch/Molecule links, generic external-vault import (supersedes the 18 per-library scripts), CSV import wizard, layout export, mother→daughter lineage, storage location tree.

Net-new in this spec: **org ownership (from Sentinel), loan/checkout workflow with per-org policy, open group hierarchy, insights dashboard (d3 tree + Plotly charts), kiosk API, legacy migration**.

## 2. Resolved decisions

| Decision | Answer |
|---|---|
| Org source | Sentinel. Orgs = external partners with own email domains; domain-derived, one org per user — works as-is. No org switcher needed. |
| Cellar `Organization` aggregate | Untouched — stays provenance-only (vendors/CROs). UI copy must distinguish "Owner org" (Sentinel) from provenance orgs. |
| Visibility | Browse all, default filter = my org. Per-org opt-out: `plates_private=true` → others see only plates actively on loan to their org. |
| Workflow | Stages configurable per org (`OrgPlatePolicy`); kiosks optional. Owner org's policy governs its plates. |
| Volume/depletion | Dropped — not used. |
| Barcodes | Stored verbatim; scan resolution fallback chain (see §7); per-source extraction rules live in DataSource mapping. |
| Migration | Structure + open checkouts only; closed history stays in legacy DB. |
| Charts | react-d3-tree for hierarchy; Plotly for all other charts. |

## 3. Part A — Sentinel work (identity-service repo, release 0.20.0)

Verified state: JWTs already carry `oid`/`oslug`/`opub` (`service/src/auth/jwt.py:55-57,127-129`); Python SDK 0.19.0 (already pinned by Cellar) decodes and discards them; no service-key org endpoints exist.

1. **SDK:** add `org_id: UUID | None`, `org_slug: str | None`, `org_is_public: bool` to `AuthenticatedUser` (`sdk/src/sentinel_auth/types.py`); populate from claims in `middleware.py` and `authz_middleware.py`. Purely additive.
2. **Service:** new internal (service-key) endpoint on `INTERNAL_ROUTERS`: `GET /organizations` → `[{id, slug, name, is_public, enabled}]` (enabled only, unless `?include_disabled=1`). Nothing else moves off the admin listener.
3. Release as 0.20.0 (unified versioning); Cellar bumps pin.

## 4. Part B — Cellar domain model (inventory context unless noted)

### 4.1 `RegisteredPlate` additions
- `owner_org_id: UUID | None` — Sentinel org id (external-ref pattern, like `workspace_id`). Nullable; unowned plates behave as public.
- `group_id: UUID | None` — FK → `plate_groups`, SET NULL on group delete. A plate belongs to ≤1 group (tags cover cross-cutting labels). Invariant: plate's `owner_org_id` must match its group's.
- Default on registration: `owner_org_id = auth.org_id`.

### 4.2 `PlateGroup` — new aggregate (the open hierarchy)
Fields: `id, workspace_id, owner_org_id, name, parent_group_id?, group_type?, description?, created_by, created_at/updated_at/version`.
- Adjacency-list tree; any group may be root; any group may nest (no forced VENDOR root, no auto-naming — the two legacy rigidities we're dropping).
- `group_type` = optional term from a `plate_group_type` ControlledVocabulary (seed: vendor, screening, master_twin, hit_collection — extensible per workspace).
- Invariants: parent in same workspace + same owner org; no cycles (validated on reparent); name unique per `(workspace, owner_org, parent)` (NULLS NOT DISTINCT, as in migration 049).
- Events: `PlateGroupCreated/Updated/Moved/Deleted`.

### 4.3 `PlateLoan` — new aggregate (borrowing)
Root: `id, workspace_id, owner_org_id, borrower_org_id, requested_by, approved_by?, due_date?, notes?, status (OPEN|CLOSED), closed_at?`. Items (owned entities): `LoanItem {id, loan_id, plate_id, status, status_changed_at}`.
- `borrower_org_id` = requester's org from token (internal loan when equal to owner org — the common case).
- All plates in one loan share `owner_org_id` (validated at request).
- **One active loan-item per plate** (legacy's structural invariant, kept): partial unique index on `loan_items(plate_id) WHERE status IN ('requested','approved','checked_out','return_pending')`.
- Custody is **derived** from the active item — never duplicated into `PlateStatus` (which remains physical lifecycle).
- Loan `status` → CLOSED when every item is terminal; emits `PlateLoanClosed`.
- Events: `PlateLoanRequested/ItemApproved/ItemDenied/ItemCheckedOut/ItemReturnRequested/ItemReturned/Cancelled/Closed` — notification hooks for a later phase.

**Item state machine** (legacy mapping in §12):

```
REQUESTED ──approve──▶ APPROVED ──confirm-out──▶ CHECKED_OUT ──request-return──▶ RETURN_PENDING ──confirm-in──▶ RETURNED
    │ deny → DENIED         │ cancel → CANCELLED
    │ cancel → CANCELLED
```

**Policy collapse rules** (evaluated against the *owner org's* `OrgPlatePolicy`):
- `require_approval=false` → items are created directly in APPROVED.
- `confirmation=none` → APPROVED auto-advances to CHECKED_OUT; RETURN_PENDING auto-advances to RETURNED (i.e. self-serve).
- `confirmation=admin_confirm` → an authorized user confirms handout/return in the UI.
- `confirmation=kiosk_scan` → a kiosk scan performs the confirm transitions (legacy ceremony).

**Approval authority:** RBAC action `inventory.plate_loans.approve` (Sentinel RoleClient, as elsewhere) **and** `auth.org_id == loan.owner_org_id`; workspace `owner|admin` role bypasses the org check (Sentinel orgs have no roles — this composition replaces them).

### 4.4 `OrgPlatePolicy` — new aggregate (per-org config)
Keyed `(workspace_id, org_id)`; read path returns defaults when no row exists.
Fields: `require_approval: bool = true`, `confirmation: kiosk_scan|admin_confirm|none = admin_confirm`, `default_due_days: int | None = 14`, `plates_private: bool = false`.
Legacy-equivalent config = `{true, kiosk_scan, 14, false}`.

### 4.5 `KioskDevice` — new aggregate
`id, workspace_id, org_id, name, token_hash (sha256), is_active, last_seen_at?, created_by`. Token generated once, shown once, admin-revocable. A device acts only on plates whose owner org matches its org.

## 5. Visibility rules (single enforcement point)

One application-layer `PlateVisibilityService` used by ListPlates / GetPlate / groups tree / insights / loan browse:
- Plate visible to user U iff: plate's owner org is not private, **or** U's org == owner org, **or** plate has an active loan with `borrower_org_id == U.org`.
- Private-org check for org-scoped reads (tree/insights for org X): member-only → 403 otherwise.
- Default list filter everywhere: `owner_org_id == auth.org_id` (plus borrowed-by-us), widenable to "All orgs" (which still applies the privacy rule).

## 6. Org directory (Cellar infrastructure)

`infrastructure/sentinel/OrgDirectory`: fetches `GET /internal/organizations` with the service key, per-process in-memory TTL cache (5 min; Valkey/redis only if cross-process staleness ever matters). Exposed as `GET /api/v1/orgs` → `[{id, slug, name}]` for FE pickers, chart legends, policy admin. Org *names* are never persisted in Cellar tables — always resolved through the directory (ids only in DB).

## 7. Barcode scan resolution

Single resolver used by kiosk scan + barcode search: try in order, first hit wins (barcodes are unique per workspace, so this is deterministic):
1. exact match;
2. if input is all digits and shorter than 6: left-pad with `0` to width 6 (our org's legacy convention — legacy `str_pad(…,6,"0",LEFT)`);
3. strip-leading-zeros variant.

Fallbacks fire only when exact match fails, so orgs with other conventions are unaffected. No per-org config unless a real collision ever appears (then: per-org pad width on `OrgPlatePolicy`). Import-side barcode *extraction* (name segment index + pad width) is per-source DataSource mapping config, not code.

## 8. Persistence (new migrations)

- `registered_plates` + `owner_org_id uuid NULL` (index `(workspace_id, owner_org_id)`), `group_id uuid NULL FK plate_groups ON DELETE SET NULL` (indexed).
- `plate_groups`: mixins + `owner_org_id, name varchar(300), parent_group_id FK self, group_type varchar(100) NULL, description text NULL, created_by`; unique `(workspace_id, owner_org_id, parent_group_id, name) NULLS NOT DISTINCT`; index on parent.
- `plate_loans`: mixins + `owner_org_id, borrower_org_id, requested_by, approved_by NULL, due_date date NULL, notes text NULL, status varchar(10), closed_at NULL`; index `(workspace_id, status)`, `(borrower_org_id)`, `(owner_org_id)`.
- `plate_loan_items`: `loan_id FK CASCADE, plate_id uuid, status varchar(20), status_changed_at`; partial unique on `(plate_id) WHERE status IN (…active…)`; index `(loan_id)`.
- `org_plate_policies`: `workspace_id, org_id, require_approval bool, confirmation varchar(20), default_due_days int NULL, plates_private bool`; unique `(workspace_id, org_id)`.
- `kiosk_devices`: `workspace_id, org_id, name, token_hash char(64), is_active bool, last_seen_at NULL, created_by`; unique `(workspace_id, name)`.

## 9. Application use cases

Groups: `CreatePlateGroup / UpdatePlateGroup / MovePlateGroup / DeletePlateGroup / GetGroupTree / AssignPlatesToGroup / RemovePlatesFromGroup`.
Loans: `RequestPlateLoan` (plates via group pick, pasted names/barcodes, or CSV upload — legacy parity; CSV gets a Download Template button), `ApproveLoanItems / DenyLoanItems` (per-item + approve-all), `ConfirmCheckout / RequestReturn / ConfirmReturn / CancelLoanItems`, `ListLoans / GetLoan / ListOverdueLoans`.
Policy/admin: `GetOrgPlatePolicy / SetOrgPlatePolicy`, `CreateKioskDevice / RevokeKioskDevice / ListKioskDevices`.
Kiosk: `ResolveScan` (resolver §7 + pending-item lookup), `ConfirmScan` (drives APPROVED→CHECKED_OUT or RETURN_PENDING→RETURNED).
Insights: `GetPlateInsights(org_id)` read model → `{by_status, by_type, by_location, group_sizes, loan_activity_weekly, overdue_count}`.

All follow the standard railway + workspace-scoping + auth-guard checklist in `docs/backend-code-guidelines.md`.

## 10. API routes

- `/api/v1/plate-groups` CRUD + `GET /tree?org_id=` + `POST /{id}/plates` / `DELETE /{id}/plates`.
- `/api/v1/plate-loans` `POST` (request) / `GET` (filters: mine, org, status, overdue) / `GET /{id}` / `POST /{id}/items:approve|deny|confirm-out|request-return|confirm-in|cancel`.
- `/api/v1/org-plate-policies` `GET /{org_id}` / `PUT /{org_id}`; `/api/v1/kiosk-devices` CRUD.
- `/api/v1/kiosk/scan` + `/api/v1/kiosk/confirm` — authed by `X-Kiosk-Token` (hash lookup), no Sentinel session (kiosk page is user-built later; the API contract is fixed here).
- `/api/v1/orgs` (directory, §6). `/api/v1/plates/insights?org_id=`.
- Orval regen in the same change as each route lands (no hand-rolled DTO mirrors).

## 11. Frontend

- **Plates list:** Owner-org column; org filter chip defaulting to "My org"; custody chip per row (on loan → borrower + due date).
- **Plate dashboard (new page):** org selector (default mine) → react-d3-tree of groups (node = group, size/color by plate count + group_type; click → details panel: metadata, plates, activity) + Plotly insight charts (plates by status/type, loan activity over time, overdue stat, storage occupancy, top groups). Follow the dataviz skill at build time.
- **Loans:** My requests / Approvals queue (owner-org gated) / all-org history; request flow with the three plate-selection modes; explicit confirm gestures (no autosave).
- **Plate detail:** custody + loan history timeline; rendered CODE128 barcode (small client lib, build-time pick).
- **Admin:** org plate policy form (proper controls, no JSON), kiosk device management (token shown once).
- Names everywhere, never UUIDs (org picker by name via `/orgs`; plates by barcode/label).

## 12. Migration (legacy MySQL → Cellar), `backend/scripts/migrate_legacy_plate_tracker.py`

One idempotent script (re-runnable, natural-key skips), args: legacy DSN, workspace id, internal org id.
1. **Plate matching:** legacy `cdd_plate_id` → `cdd_plate_sync` → Cellar plate; fallback barcode (with §7 padding). Unmatched → report.
2. **Ownership:** all matched plates → `owner_org_id = internal org`.
3. **Groups:** legacy `SET` tree (via `SET_PARENT`) → `PlateGroup` tree per library (library → root group). `set_type` → CV terms; `set_state/scientist/generating_conditions` → description text. `SET_PLATE` → `plate.group_id`.
4. **Role/status mapping:** `plate_role` → `PlateType`: VENDOR→compound_storage, MASTER→mother, MASTER_TWIN→replicate, SCREENING→assay, HIT_COLLECTION→cherry_pick. `plate_status`: Active→stored; Inactive→depleted + tag `legacy:inactive`.
5. **Open checkouts:** OPEN `TRANSACTIONS` × `TRANSACTION_PLATE` → one `PlateLoan` each; `p_status` map: COUT_REQ→requested, COUT_WSCAN→approved, ASSIGNED→checked_out, CIN_REQ/CIN_WSCAN→return_pending. Requester matched legacy UIN → account.email → Sentinel user; unmatched → listed for manual resolution. `due_date = last_activity_date + 14d`.
6. Closed transactions/activity log: **not migrated** (legacy DB kept read-only).
7. Output: summary counts + unmatched report. Cutover runbook: freeze legacy → run → spot-check → announce.

## 13. Out of scope (deliberate)

- Volume/depletion tracking (user: unused).
- Email notifications — domain events are emitted from day 1; notifier is a later phase.
- Kiosk web page itself (user-built against §10 contract).
- Closed-history import; label-print layouts; org switcher (one org per user by construction).

## 14. Session plan (batch 3–5 per conversation; layer order per CLAUDE.md)

| # | Session | Contents |
|---|---|---|
| S1 | Sentinel org surfacing | SDK org fields + internal orgs endpoint + 0.20.0 release; Cellar pin bump, `AuthContext.org_id/org_slug`, OrgDirectory + `/orgs`, FE `useOrgs` |
| S2 | Ownership, policy & visibility | `owner_org_id` (+backfill), `OrgPlatePolicy` + admin UI, `PlateVisibilityService`, org filter on plates list |
| S3 | Groups | `PlateGroup` domain→API, tree read model, FE tree page (react-d3-tree) + group management |
| S4 | Loans | `PlateLoan` domain + policy-driven machine → API → FE flows + custody chips |
| S5 | Kiosk + insights | `KioskDevice` + kiosk endpoints; insights read model + Plotly dashboard, overdue |
| S6 | Migration | Script + dry-run against legacy dump + cutover runbook |

Pre-existing drift noted during exploration (NOT this spec's scope, backlogged): `RegisteredPlate.custom_fields` never persisted; `cdd_plate_sync.cdd_statistics` column absent from ORM.
