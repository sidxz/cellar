# Spec: Loans & Plates UX Pass — from ledger to work queue (S13–S14)

**Date:** 2026-08-25 · **Status:** APPROVED 2026-08-25 (proposals L1–L7, P1–P5, D1–D4, X1–X2 ruled "agree" in chat)
**Contexts touched:** Inventory (03) — frontend only
**Builds on:** `2026-08-25-plate-tracker-revamp-spec.md` (S7–S12). Sessions continue the numbering: **S13** loans, **S14** plates.
**Tracking:** sidxz/cellar#71

## 1. Problem

Against the migrated TAMU data (2 259 plates, 8 open / 752 closed loans) the three surfaces read like a ledger:

- **Loans** — every loan is an identical card with a full items table; the title is `Texas A&M University → Texas A&M University`; dates are raw `2025-03-13`; "Approvals" lists every open loan whether or not anything is approvable; "All" renders 760 loans as cards.
- **Plates** — every row says `384-well · Assay · Stored · 0 wells · Texas A&M` (true for ~2 200 of 2 259 rows); no set, no location; a hover-delete on every row.
- **Plate detail** — seven stacked cards; the empty "No wells mapped yet" card is the largest block on every legacy plate; the one question a chemist came with — *where is it, who has it* — is answered nowhere.

The page's job is: what needs my hand, what's out, when is it coming back, where is this plate.

## 2. Decisions

| # | Decision |
|---|---|
| L1+L4 | **No "Needs action" tab.** Tabs are **Open · History**. A role-aware chip strip above the Open list filters by need (§4.2). |
| L2 | Loan identity = requester name · set names · plate count · due (relative). Org names only when borrower ≠ owner. No "Open" badge on the Open tab. Sets are the items' `group_name` only — library ancestry is not in the loan payload and a borrower cannot read the owner's tree. |
| L3 | Compact rows + a **loan page** `/inventory/loans/[id]` (§5). `loan-card.tsx` is deleted. |
| L5 | History = closed loans in `DataGrid` (§4.3). |
| L6 | Items grouped by set, with the status date; checkboxes only when the viewer has a verb. |
| L7 | After "Request loan" the dialog navigates to the new loan page. |
| P1 | Summary chips on Plates: total · On loan · Overdue · Depleted. |
| P2 | Columns Barcode · Name · Set · Format · Where · Owner (Owner only under "All orgs"). **Type and Wells mapped are removed from the list** (community AG Grid has no column chooser to bring a hidden column back; both are on the plate page; Type stays a filter). |
| P3 | Row trash icon removed; **Delete moves to the plate page "More" menu** (it did not exist there before). |
| P4 | Row multi-select → "Request loan (n)" pre-fills the dialog's barcode mode. |
| P5 | Admin's org filter remembered in `localStorage["plates.org"]` (try/catch). |
| D1–D4 | Custody hero, identity row, two columns, well map only when mapped, `Request loan` + Change Status + "More" menu (§9). |
| X1 | Relative due phrases (`formatDue`, §3.1) with the absolute date as `title`. |
| X2 | On lists, colour only exceptions: on loan = warning, overdue = destructive, depleted/disposed = muted, normal = plain text. |
| Authority | Mirrors the server: owner verbs when `me.is_admin \|\| me.org_id === owner_org_id`; borrower verbs when `me.is_admin \|\| me.org_id === borrower_org_id` (`_require_borrower_authority`). |
| "Mine" | `loan.requested_by === me.user_id`, client-side. The dashboard no longer sends `mine=true`. |
| Backend | **None.** Everything is client-side over the unpaginated lists; the loan page uses `GET /plate-loans/{id}`. `ponytail:` server-side counts/pagination is the upgrade path if `/plate-loans` ever gets slow. |

## 3. Shared pieces

### 3.1 `formatDue` — `shared/lib/format-date.ts`

```ts
/** Day-granular due phrase for a YYYY-MM-DD value (local calendar days). */
export function formatDue(input: string | null | undefined, now?: Date): { label: string; overdue: boolean } | null
```

| Δ days (due − today) | label |
|---|---|
| 0 | `due today` |
| 1 | `due tomorrow` |
| 2…13 | `due in N d` |
| 14…59 | `due in N w` |
| ≥ 60 | `due Sep 30` (year appended when not the current year) |
| −1 | `1 d overdue` |
| −2…−13 | `N d overdue` |
| −14…−59 | `N w overdue` |
| −60…−729 | `N mo overdue` (30-day months) |
| ≤ −730 | `N y overdue` |

`overdue` = Δ < 0. Callers put `formatDate(due)` in `title`. Optional `now` for tests.

### 3.2 `useMemberNames` — `shared/hooks/use-workspace-members.ts`

```ts
/** user_id → display name over the full member list; "" for null, "Unknown member" when absent. */
export function useMemberNames(): (userId: string | null | undefined) => string
```
Wraps `useWorkspaceMembers()` (no query) in a memoized `Map`; stable callback.

### 3.3 `features/inventory/lib/loan-verbs.ts` (moved out of `loan-card.tsx`)

`VERB_SOURCES`, `VERB_LABELS`, `OWNER_VERBS`, `BORROWER_VERBS` verbatim, plus:

```ts
export function ownerAuthority(loan, me): boolean
export function borrowerAuthority(loan, me): boolean
export function eligibleItems(loan, verb): PlateLoanItem[]
/** Verbs the viewer may press that have ≥ 1 eligible item, owner verbs first. */
export function availableVerbs(loan, me): LoanVerb[]
```

### 3.4 `features/inventory/lib/loan-summary.ts`

```ts
export interface LoanSet { id: string | null; name: string; count: number }   // id null = "Ungrouped"
export function loanSets(loan): LoanSet[]                 // distinct, first-seen order
export function setSummary(loan): string                  // "Set 5, Set 27 +1"; "" when no grouped items
export const ITEM_STATUS_ORDER: LoanItemStatus[]          // requested, approved, checked_out, return_pending, returned, denied, cancelled
export function itemStatusCounts(loan): { status: LoanItemStatus; count: number }[]  // non-zero, in order
export function isOverdue(loan, todayISO = local today): boolean   // status open && due_date < today
export function loanOutcome(loan): "open" | "returned" | "denied" | "cancelled"
   // closed: any returned → returned; else any denied → denied; else cancelled
export type InboxKey = "approve" | "hand_out" | "check_in" | "awaiting_approval" | "ready_for_pickup" | "overdue" | "mine"
export const INBOX_ORDER: InboxKey[]   // as listed above
export const INBOX_LABELS: Record<InboxKey, string>
   // To approve · To hand out · To check in · Awaiting approval · Ready for pickup · Overdue · Requested by me
export function loanInboxKeys(loan, me): Set<InboxKey>
export function inboxCounts(loans, me): Record<InboxKey, number>   // number of LOANS per key
export function loanTitle(loan, requesterName): string   // `${name} · ${setSummary || `${n} plates`}`
```

`loanInboxKeys`: with owner authority — `requested`∈items → `approve`, `approved` → `hand_out`, `return_pending` → `check_in`; without — `requested` → `awaiting_approval`, `approved` → `ready_for_pickup`. Always: `isOverdue` → `overdue`; `requested_by === me.user_id` → `mine`. (A self-checkout viewer with owner authority sees only the owner-side keys — no duplicates.)

### 3.5 `features/inventory/lib/storage-path.ts`

```ts
/** "Room 1148 › Freezer 3" — last `depth` names of the parent chain; "" when unknown. Cycle-guarded. */
export function storagePath(locations: StorageLocation[] | undefined, id: string | null | undefined, depth = 2): string
export function storageFullPath(locations, id): string   // all levels, for `title`
```

### 3.6 `useGroupIndex` — `features/inventory/hooks/use-plate-groups.ts`

```ts
/** group id → { name, path } over the trees of the given orgs ("SAC1 › Set 014"). */
export function useGroupIndex(orgIds: string[]): Map<string, { name: string; path: string }>
```
`useQueries` over `GET /plate-groups/tree?owner_org_id=`, flattened with ancestry. Plates list passes `[selectedOrg]` or every org id under "All orgs" (admin).

### 3.7 `plateWhereabouts` — `features/inventory/lib/plate-where.ts`

```ts
export type Whereabouts =
  | { kind: "custody"; loan: PlateLoan; item: PlateLoanItem; overdue: boolean }
  | { kind: "terminal"; status: "depleted" | "disposed" }
  | { kind: "location"; path: string; fullPath: string }
  | { kind: "status"; status: PlateStatus }
export function plateWhereabouts(plate, custody: {loan,item} | undefined, locations): Whereabouts
```
Precedence: custody (from `buildCustodyMap`) → terminal status → storage location → status. One source of truth for the list's Where column and the plate page hero.

## 4. Loans dashboard (S13) — `loan-dashboard.tsx` rewrite

### 4.1 Frame
`PageHeader` "Loans" / "Plate checkouts — who has what, and what's due back." Action: **Request loan**. `useHashTab("open")`: **Open** · **History**.

### 4.2 Open tab
- Data: `useLoans({ status: "open" })` (visibility already scopes to owner-side + borrower-side loans), `useCurrentUser`, `useMemberNames`, `useOrgs`.
- **Chip strip** (`InboxChips`): one toggle per non-zero `InboxKey` in `INBOX_ORDER`, label + count, single-active, click again clears; `aria-pressed`; `overdue` chip renders destructive when inactive. Hidden entirely when every count is 0.
- **List**: loans filtered by the active chip, sorted by `due_date` ascending (nulls last), then `created_at` descending. Each is a `LoanRow` (§4.4). Empty copy: "No open loans." / "Nothing matches <chip label>." Loading/error as today.

### 4.3 History tab
`useLoans({ status: "closed" }, { enabled: tab === "history" })` → `DataGrid` (`preferencesKey="loans-history"`, `searchPlaceholder="Search requester, set or barcode…"`, `includeHiddenColumnsInQuickFilter`):

| Column | Value |
|---|---|
| Requester | member name |
| Sets | `setSummary` |
| Plates | `items.length` |
| Requested | `formatDate(created_at)` |
| Closed | `formatDate(closed_at)` |
| Outcome | `StatusBadge(loanOutcome, LOAN_VARIANT)` |
| Barcodes (hidden) | items' barcodes joined — quick-filter only |

Default sort Closed desc. Row click → `/inventory/loans/{id}`.

### 4.4 `LoanRow` — `loan-row.tsx`
A `<Link href="/inventory/loans/{id}">` block, `rounded-md border bg-card px-4 py-3 hover:bg-accent`:

```
Maia Young   SAC3 › Set 5, Set 27 +1 · 7 plates                        4 mo overdue
[5 checked out] [2 return pending]  Lent to Sanofi                     requested Apr 2, 2026
Migrated from legacy plate-tracker · requester: Maia Young             (notes, muted, truncate)
```
- Line 1: requester name (`font-medium`), `setSummary` (muted; omitted when empty), `n plates`; right: `formatDue` label (`text-destructive font-medium` when overdue, muted otherwise, `title` = absolute date), nothing when no due date.
- Line 2: `itemStatusCounts` as `StatusBadge`s (`LOAN_VARIANT`, label `"5 checked out"`); `Lent to <org>` when viewer's org is the owner and borrower differs, `Borrowed from <org>` when viewer's org is the borrower and owner differs, both names (`A → B`) for an admin outside both; right: `requested {formatDate(created_at)}`.
- Line 3: notes, muted, single line, `title` = full notes.
- Never fetches comments.

## 5. Loan page (S13) — `app/(dashboard)/inventory/loans/[id]/page.tsx` → `loan-page.tsx`

- `useLoan(loanId)`; `DetailShell` (`backHref="/inventory/loans"`, title = `loanTitle(loan, requesterName)`, `notFoundMessage="Loan not found."`).
- **Header line** (under the title, `-mt-3`): `StatusBadge(loan.status, LOAN_VARIANT)` · due phrase (as §4.4) · `requested {formatDate}` · org line (as §4.4) · `n plates`. Notes below, muted.
- **Actions** (DetailShell `actions`): one button per `availableVerbs(loan, me)`, label `"{VERB_LABELS} ({count})"` where count = checked ∩ eligible, else all eligible; variants approve=default, deny=destructive, others outline; disabled while the mutation is pending or count is 0. `request-return` opens `RequestReturnDialog` (unchanged); other verbs call `useLoanItemsAction` and clear the selection on success.
- **Body** `grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]`:
  - Left — Card "Plates (n)": `Table`; a muted subheader row per `loanSets` entry (`"{name} · {count} plates"`, `colSpan`) when the loan has ≥ 1 grouped item; columns: [checkbox — only when `availableVerbs` is non-empty] · Barcode (`Link` to the plate, mono) · Plate · Status (`StatusBadge`, `LOAN_VARIANT`) · Since (`formatDate(status_changed_at)`, `title` = `formatDateTime`).
  - Right — Card "Activity": `CommentFeed` scope `{ loanId }`, composer target `plate_loan`, `canWrite = canEdit(me)`. Always loaded (one loan per page).
- Breadcrumb: Loans › {title} (DetailShell default override).

## 6. Request loan dialog (S13)
- New prop `initialBarcodes?: string[]`: when non-empty on open, `mode = "paste"` and the textarea is pre-filled one per line.
- On success: close and `router.push("/inventory/loans/{loan.id}")`.

## 7. Comment feed (S13)
The loan-context link becomes `href="/inventory/loans/{loan_id}"`, text **view loan** (ruling R19 superseded — a per-loan page now exists).

## 8. Plates list (S14) — `plate-list.tsx` rewrite

- **Removed:** delete column, `ConfirmDeleteDialog`, `useDeletePlate`, Type / Status / Wells Mapped columns (Status folds into Where).
- **Filters** unchanged (type, status, format, org for admins, tags). Admin org choice persisted in `localStorage["plates.org"]`.
- **Summary strip** under the filters: `"{n.toLocaleString()} plates"` + toggle chips (single-active, non-zero only, same component as §4.2): **On loan** (custody kind) · **Overdue** (custody overdue) · **Depleted** (status depleted). Chips filter the loaded rows client-side.
- **Columns:** Barcode (link, mono) · Name · Set (`useGroupIndex` path, `—` when none) · Format (`384`) · Where · Owner (`hide` unless "All orgs").
- **Where** renders `plateWhereabouts`: custody → `{requester name} · {phrase}` where phrase = `formatDue` label when `checked_out` with a due date, else the item status label; tone destructive when overdue, warning otherwise. terminal → status label, muted. location → `storagePath` (title = full path). status → status label, muted.
- `selectionToolbar` → `"{n} selected"` + **Request loan (n)** → `RequestLoanDialog initialBarcodes`.
- `preferencesKey="plates"`. Row click → plate page. Empty: existing `EmptyState` when the org has no plates; "No plates match the current filters." otherwise.

## 9. Plate page (S14) — `plate-detail.tsx` rewrite

- **Hero** (under the title, before anything else): icon + one line from `plateWhereabouts`:
  - custody: `{item status label} · {requester name} · since {formatDate(item.status_changed_at)}` + due phrase (destructive when overdue) + `View loan →` (`/inventory/loans/{id}`)
  - terminal: `Depleted` / `Disposed` (muted)
  - location: `In storage · {storagePath(depth 3)}`
  - status: `{status label} · no storage location`
- **Identity row**: set path as a `Link` to `/inventory/plate-groups/{group_id}` (`usePlateGroup(group_id)` → ancestors + name, " › "), `{format}-well`, type badge, owner org name, `plate_label` muted.
- **Actions**: **Request loan** (primary; only when whereabouts kind ≠ custody and status ∉ {depleted, disposed}) → `RequestLoanDialog initialBarcodes=[barcode]`; the existing Change Status select; **More** `DropdownMenu`: Map Wells · Import Data · Export CSV · Export Excel · Derive Plate · — · Delete (destructive) → `ConfirmDeleteDialog` → `useDeletePlate` → `/inventory/plates`.
- **Body** `grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]`:
  - Left: Details (Project · Template · Parent plate · Registered by (member name) · Notes), Tags, Daughter plates (when any), Files.
  - Right: Well map (**only when wells are mapped**), History (one row per loan: `{requester} · StatusBadge(item.status) · {formatDate(created_at)}{closed_at ? " → " + formatDate(closed_at) : ""}`, whole row links to the loan), Comments.
- Well-mapping and derive dialogs unchanged.

## 10. Tests (vitest; delete `loan-card.test.tsx`)

| File | Pins |
|---|---|
| `shared/lib/format-date.test.ts` | every `formatDue` bucket incl. boundaries (13/14 d, 59/60 d, 729/730 d), year suffix |
| `shared/hooks/use-workspace-members.test.tsx` | `useMemberNames` fallbacks |
| `lib/loan-verbs.test.ts` | authority × verbs matrix (owner-org, borrower-org, admin, stranger) |
| `lib/loan-summary.test.ts` | sets/summary "+n", status counts order, overdue, outcome precedence, inbox keys (owner vs borrower side, no duplicates), counts |
| `lib/storage-path.test.ts` | depth, unknown id, cycle |
| `lib/plate-where.test.ts` | precedence custody > terminal > location > status |
| `components/loan-row.test.tsx` | name/sets/due/org line variants; renders N rows with **zero** `/comments` requests |
| `components/loan-page.test.tsx` | the three owner-verb visibility cases ported from loan-card; borrower verbs for borrower-org member; request-return opens the dialog; set subheaders; no checkboxes for a stranger |
| `components/loan-dashboard.test.tsx` | chips show non-zero keys with counts and filter the list; history tab fetches `status=closed` only when opened |
| `components/request-loan-dialog.test.tsx` | + `initialBarcodes` pre-fills paste mode; success navigates to the loan |
| `components/comment-feed.test.tsx` | link href → `/inventory/loans/{id}` |
| `components/plate-list.test.tsx` | chips count + filter; Owner column hidden unless All orgs; selection toolbar opens the dialog with the selected barcodes |
| `components/plate-detail.test.tsx` | hero for each whereabouts kind; Request loan hidden while on loan; Delete flow |

## 11. Out of scope
Plate Groups page (legacy parity just tuned) · backend changes · pagination · per-item activity timeline (state transitions live only in the audit log) · attribution of migrated loans (that's a `--user-map` re-run, not a display hack).

## 12. Sessions
| Session | Scope | Commit |
|---|---|---|
| **S13** | §3.1–3.4, §4–7, their tests | `feat(frontend): loans read as a work queue — inbox chips, compact rows, loan page, history grid` |
| **S14** | §3.5–3.7, §8–9, their tests | `feat(frontend): plates answer "which set, where, who has it" — where column, custody hero, request-loan from plates` |

One whole-branch review after S14; browser verification against the saclab-dev data for both.
