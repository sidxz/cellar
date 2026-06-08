# Run Detail Header Redesign — Design Spec

**Date:** 2026-06-07
**Branch:** `design-5`
**Status:** Approved (design); pending implementation plan
**Surface:** Screening & Assay → Run detail page (`run-detail.tsx`)

---

## Problem

The run detail page spends ~900px of vertical space on four stacked cards
(**Details**, **Targets**, **Collections**, **Tags**) before the data tabs
(Readout Data / Plate Map / Heat Map / Dose-Response / QC Metrics / Files)
even begin. Two structural issues drive the bloat:

1. **Always-on edit controls.** The Targets and Collections multi-select
   dropdowns are rendered unconditionally (for editors on unlocked runs),
   so the page is permanently in "edit mode" even when nobody is editing.
2. **One card per field.** Details, Targets, Collections, and Tags each get a
   full `Card` with its own header and padding; Tags additionally renders the
   full-width collapsible `TagTable`.

The data — which is the reason a chemist opens a run — is pushed below the fold.

## Goal

Collapse the four cards into a single ~140px **summary card** so the tabs start
~750px higher, while keeping every relationship visible at a glance and
editable on demand. The result should read as a dense, scientific run header,
not a form.

## Non-Goals

- No change to the data tabs (`RunDataPanel`) or any action buttons.
- No backend/API changes — everything reuses existing hooks and DTOs.
- No change to the protocol Overview tab's wide `CoverageBar` or to the
  shared `TagTable` (still used on the protocol/campaign surfaces).
- Not extracting a shared inline-edit component from the campaign
  `DescriptionRow` in this change (noted as optional future work).

---

## Design

### Layout

`DetailShell` is unchanged — it still renders the back link, the
`Run {run_date}` title, the status badge, and all action buttons.

Inside the shell, **one new `RunSummaryCard`** replaces the four cards. It has
two bands separated by a hairline divider:

```
┌───────────────────────────────────────────────────────────────────────┐
│ Protocol Mtb_WCA…Resazurin · 2026-05-15 · 384-Well · 1 plate · ⬤Z′0.82 │  ← Facts band
│ Resuspended in fresh 7H9; DMSO 0.5%.  ✎                                │  ← Notes (conditional)
│ ─────────────────────────────────────────────────────────────────────  │
│ Targets [🎯 M. tb whole-cell] +Add    Collection ▨ Library SACCZ ▮▯ 2% ✎│  ← Relations band
│ Tags [project=SACCZ] [stage=primary] +Tag                              │
└───────────────────────────────────────────────────────────────────────┘
[ Readout Data | Plate Map | Heat Map | Dose-Response | QC Metrics | Files ]
```

### Band 1 — Facts (read-only, inline)

A single dense line of intrinsic metadata, muted labels:

- `Protocol` → link to `/assays/protocols/{protocol_id}` (reuse `ProtocolName`)
- `run_date` (mono)
- `plate_format` label (`PLATE_FORMAT_LABELS`)
- `{plate_count} plate(s)`
- **Z′ chip** — worst-plate Z′ via existing `worstZPrime(run.qc_metrics)`,
  color-coded by existing `classifyZPrime()` /  `ZPrimeBadge`
  (≥0.5 green "Excellent", ≥0 amber "Marginal", <0 red "Poor"). Rendered as a
  link to `#qc`, which switches the data panel to the QC Metrics tab
  (`useHashTab` listens to `hashchange`). **Hidden** when `worstZPrime` returns
  `null` (no QC/plate data) — never an empty placeholder.

**Lock-reason banner:** when `run.lock_reason` is set, keep the existing
destructive-tinted banner, rendered at the top of the card.

**Notes line (conditional):** directly under the facts line.
- Rendered only when notes are present **or** the user can edit (editor +
  unlocked). Read-only viewer with no notes → omitted entirely.
- Click-to-edit (Notion-style: the text is the click target, a faint inline
  pencil at the end — no corner pencil). Editing swaps to a `Textarea` with
  explicit **Save** / **Cancel**; ⌘/Ctrl+Enter saves, Esc cancels. Commits via
  the existing `useUpdateRun({ runId, data: { notes } })`. Empty + editable
  shows a faint "Add notes…" affordance.
- Mirrors the campaign `header-strip.tsx` `DescriptionRow` pattern; replicated
  locally as `RunNotesLine` (no campaign code touched).

### Band 2 — Relations (compact display, popover edit)

Default state shows compact chips only — **no always-on dropdowns**. Each
relation has one explicit trigger that opens a shadcn `Popover` containing the
**existing** control. Mutations still commit per-toggle exactly as today; the
popover is only the disclosure surface. Closing returns to chips.

| Relation | Display | Edit trigger → popover |
|----------|---------|------------------------|
| **Targets** | `TargetChips` (existing) | `+ Add` (dashed pill when empty; small `+` when populated) → `TargetMultiSelect` with the current diff-batch `onChange` logic |
| **Collection(s)** | one compact `CoverageChip` (new) **per attached collection**, wrapping: `CollectionTypeIcon` + name + mini bar + `covered/total · %` + `N remaining` link → existing `CoverageGapDialog`. Empty collection → `—`. | a single `✎` (next to the chip group) → `CollectionMultiSelect` (existing) editing the whole set, `projectIds` from `protocol.project_ids` |
| **Tags** | `TagChip`s (existing; `×` removes via `useUnassignTag`) | `+ Tag` → `TagAutocomplete` key/value add-row → `useAssignTag` |

**Permission / lock gating** (unchanged semantics): edit triggers render only
when `canEditTags && !run.is_locked`. Read-only or locked → chips only.

**Empty states:** `Targets` with none → just the `+ Add` pill. No collections →
muted "No collections" with the `✎` trigger. No tags → faint "No tags" + `+ Tag`.

### Tags: replacing the TagTable on this page

The full-width collapsible `TagTable` (key/value rows with who/when columns) is
replaced **on the run page only** by inline `TagChip`s + the `+ Tag` popover.
Who/when is dropped from the at-a-glance view (still available in the audit
trail); each chip's native `title` shows `key=value · added {relative}`. The
`TagTable` component itself is untouched and still used elsewhere.

---

## Components

**New (all under `features/screening-assay/components/`):**

1. `run-summary-card.tsx` — `RunSummaryCard({ run, protocol, canEdit })`.
   Orchestrates the facts band, notes line, and relations band. Owns the
   target/collection/tag mutation wiring currently in `run-detail.tsx`
   (`useAddRunTarget`/`useRemoveRunTarget`, `useAddRunCollection`/
   `useRemoveRunCollection`, target/collection query invalidation, gap state).
2. `coverage-chip.tsx` — `CoverageChip({ coverage, onViewGap })`. Compact
   single-line coverage; reuses `fmt`, `CollectionTypeIcon`, and the same
   `CollectionCoverage` type as `CoverageBar`.
3. `relation-popover.tsx` — thin shadcn `Popover` wrapper used by all three
   relations (trigger + content), so the disclosure behavior is consistent.
4. `run-notes-line.tsx` — `RunNotesLine({ run, canEdit })`. Inline click-to-edit
   notes via `useUpdateRun`.

**Modified:**

- `run-detail.tsx` — delete the four cards (Details, Targets, Collections,
  Tags) and their inline wiring; render `<RunSummaryCard … />` in their place.
  Keep the `DetailShell` actions, all dialogs (reject/lock/unlock/reset/delete/
  cascade), and `<RunDataPanel run={run} />` exactly as-is.

**Reused as-is:** `TargetChips`, `TargetMultiSelect`, `CollectionMultiSelect`,
`TagChip`, `TagAutocomplete`, `CoverageGapDialog`, `ZPrimeBadge`,
`CollectionTypeIcon`, `worstZPrime`/`classifyZPrime`, `useUpdateRun`,
`useAssignTag`/`useUnassignTag`/`useEntityTags`, `useHashTab`.

---

## Data Flow

- Targets/collections: chip display from `run.targets` / `run.collections`;
  edits dispatch the existing add/remove mutations (diff-batched, single
  invalidation pass) from inside the popover — unchanged from today.
- Tags: `useEntityTags("runs", runId)` for chips; `useAssignTag`/`useUnassignTag`.
- Notes: optimistic-free `useUpdateRun`; on success the run query invalidates.
- Z′: derived synchronously from `run.qc_metrics` — no new fetch.

## Error Handling

Inherited from the existing mutations (toast on error). Popovers stay open on a
failed mutation so the user can retry; closing never blocks on in-flight writes.
Edit triggers disable while their mutation is pending (mirrors current
`disabled={addRunTarget.isPending || …}`).

## Testing

- Unit (vitest): `RunSummaryCard` renders facts; Z′ chip hidden when
  `worstZPrime` is null and shown/colored when present; notes line hidden for
  read-only+empty; relation triggers hidden when locked or non-editor;
  `CoverageChip` renders `covered/total · %` and the gap link.
- Reuse existing `target-multi-select` / `collection-multi-select` /
  `collection-coverage-chips` tests (controls unchanged).
- E2E (Playwright): note as a TODO scenario — open run, edit a target via
  popover, add a tag via popover, click Z′ chip → lands on QC tab.

## Vertical-space outcome

~900px (4 cards) → ~140px (1 card, 3 short bands). Tabs begin ~750px higher.
