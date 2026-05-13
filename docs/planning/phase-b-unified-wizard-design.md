# Phase B: Unified Registration & Disclosure Wizard

**Date:** 2026-04-15
**Branch:** `fe2`
**Status:** Design approved, implementation not started
**Prerequisite:** Phase A (merge preview + two-phase disclosure) — complete on `fe2`

---

## Problem

Registration and disclosure are currently separate UI flows:
- **Registration:** A 480-line modal dialog (`molecule-registration-dialog.tsx`) for single registration, a separate bulk upload dialog
- **Disclosure:** An inline form on the compound detail overview tab, redirecting to a merge preview page on match

From the scientist's perspective, these are the same action: "I have compound data, process it." The system should figure out whether it's a new registration, a dedup, or a disclosure based on the data provided.

Additionally, bulk registration has no disclosure detection — if a CSV row's identifiers match an existing undisclosed molecule, it registers a duplicate instead of disclosing.

---

## Scope

1. **Unified full-page wizard** replacing registration dialog + inline disclosure form
2. **Single and bulk modes** in one wizard with mode toggle on step 1
3. **Identifier-match disclosure detection** in `RegisterMolecule` — automatically detects when a row should disclose an undisclosed molecule
4. **Temporal workflow** for bulk processing (shared activity with CDD import)
5. **Batch-confirm merge review** with expandable impact previews
6. **Review Queue** — renamed disclosure conflicts list covering conflicts + pending confirmations
7. **Disclosure history** surfaced on compound detail from existing `DisclosureRequest` data

**Not in scope:** New disclosure provenance aggregate (existing `DisclosureRequest` fields are sufficient). Bulk Temporal for other contexts (S49 scope).

---

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Single vs separate wizards | Single wizard, mode toggle on step 1 | One entry point, one mental model, less code duplication |
| Batch creation | Optional wizard step (single), CSV-sourced (bulk), auto-create if not provided | Scientists usually register because they have a sample; skippable keeps it fast |
| Disclosure provenance model | Reuse `DisclosureRequest` as-is, surface in UI | All fields already exist; no new aggregate needed |
| Bulk processing | Temporal workflow from day 1 | Infrastructure already deployed for CDD import; no throwaway sync path |
| Polling vs streaming | Poll Temporal query every 3s | WebSocket infra (S51) not built yet; polling is sufficient and zero UX change when WS lands |
| Identifier matching | Primary match on name/custom IDs against undisclosed molecules | Most natural for scientists; reg number fallback not needed (identifiers cover it) |
| Conflict handling | Always require human review, even for API callers | Conflicts are genuinely ambiguous; auto-resolution risks data integrity |
| Existing UI | Delete registration dialog + inline disclosure form | One unified flow; two paths creates confusion |
| Backend approach | Enhance `RegisterMolecule`, share activity with CDD import | Single source of truth; no parallel pipeline |

---

## Wizard Flow

### Route

`/compounds/register` — single full-page route.

### Entry Points

| Action | Entry | Wizard State |
|--------|-------|-------------|
| "Register" button on compound list | Fresh wizard | `mode: null` (user picks) |
| "Bulk Register" button on compound list | Fresh wizard | `mode: "bulk"` (pre-selected) |
| "Disclose" button on compound list/detail | Wizard with molecule pre-loaded | `mode: "single"`, `disclosureMode: true`, `moleculeId` set |

### Steps

```
Single mode:                          Bulk mode:
┌──────────────┐                      ┌──────────────┐
│ 1. Input     │ ← form fields        │ 1. Input     │ ← CSV/SDF upload + preview
├──────────────┤                      ├──────────────┤
│ 2. Processing│ ← inline spinner     │ 2. Processing│ ← Temporal + poll progress
├──────────────┤                      ├──────────────┤
│ 3. Results   │ ← outcome + merges   │ 3. Results   │ ← categorized table + merges
├──────────────┤                      ├──────────────┤
│ 4. Batch     │ ← optional fields    │   (skip)     │ ← batch from CSV / auto-created
├──────────────┤                      ├──────────────┤
│ 5. Summary   │ ← links + counts     │ 4. Summary   │ ← links + counts
└──────────────┘                      └──────────────┘
```

**Step 3 (Results):**
- Single mode, no merge candidate: brief confirmation ("Registered as CV-00XXX"), auto-advance
- Single mode, merge candidate: full merge preview inline with confirm/reject
- Bulk mode: categorized results table with batch-confirm checklist

**Step 4 (Batch, single only):**
- Optional batch fields: source, amount, unit, purity, salt form, stoichiometry
- If skipped or left empty: auto-create batch with defaults
- Bulk mode: batch info sourced from CSV columns, auto-create where not provided

### Step Engine — Zustand Store

```typescript
interface RegistrationWizardState {
  // Mode
  mode: "single" | "bulk" | null;
  currentStep: number;

  // Input (single)
  singleInput: {
    name: string;
    smiles: string | null;
    moleculeType: MoleculeType;
    originatingOrgId: string | null;
    externalIds: ExternalIdentifier[];
    customFields: Record<string, unknown>;
    disclosureMode: boolean;
    moleculeId: string | null;
  };

  // Input (bulk)
  bulkInput: {
    file: File | null;
    fileFormat: "csv" | "sdf";
    parsedRows: BulkRow[];
    columnMapping: Record<string, string>;
  };

  // Processing
  jobId: string | null;
  jobStatus: "pending" | "processing" | "completed" | "failed" | null;
  progress: { current: number; total: number };

  // Results
  results: ProcessingResults;
  mergeCandidates: MergeCandidate[];
  mergeDecisions: Record<string, "confirm" | "reject">;

  // Batch (single only)
  batchInput: BatchInput | null;

  // Actions
  setMode: (mode: "single" | "bulk") => void;
  nextStep: () => void;
  prevStep: () => void;
  setMergeDecision: (candidateId: string, decision: "confirm" | "reject") => void;
  confirmAllMerges: () => void;
  reset: () => void;
}
```

**Navigation guards:** Back allowed from any step except during processing. Next validates current step before advancing. Browser navigation/refresh shows "discard changes?" prompt.

---

## Backend Changes

### Core Principle

`RegisterMolecule` is the single processing unit. Enhanced with identifier-match disclosure detection. Both the wizard and CDD import call the same code through a shared Temporal activity.

### RegisterMolecule Enhancement

Add identifier matching against undisclosed molecules after InChIKey dedup check:

```python
# After InChIKey dedup check, if no match found:
if not inchi_match and input.external_ids:
    undisclosed_match = await self._molecule_repo.find_undisclosed_by_identifiers(
        workspace_id, input.external_ids
    )
    if undisclosed_match:
        # Delegate to DisclosureService
        outcome = await self._disclosure_service.submit(
            SubmitDisclosureCommand(
                workspace_id=workspace_id,
                molecule_id=undisclosed_match.id,
                disclosed_smiles=input.smiles,
                auto_approve=input.auto_approve,
                scientist_name=input.scientist_name,
                ...
            )
        )
        return RegistrationOutcome(
            molecule=undisclosed_match,
            action="disclosure" or "merge_candidate",
            needs_merge_confirmation=outcome.needs_confirmation,
            matched_molecule_id=outcome.matched_molecule_id,
            disclosure_id=outcome.disclosure_request.id,
        )
```

### RegistrationOutcome Action Enum

```python
class RegistrationAction(str, Enum):
    REGISTERED = "registered"           # new molecule created
    DEDUPLICATED = "deduplicated"       # InChIKey match, added identifiers + batch
    DISCLOSED = "disclosed"             # matched undisclosed, structure applied, no merge
    MERGE_CANDIDATE = "merge_candidate" # disclosed + InChIKey matches another → needs confirmation
    CONFLICT = "conflict"               # ambiguous match, CAS mismatch, structure conflict
```

### Decision Tree Per Row

```
Row arrives with (name, smiles?, identifiers[], molecule_type, org)
│
├─ Has SMILES?
│   ├─ YES
│   │   ├─ Standardize → compute InChIKey
│   │   ├─ InChIKey matches existing DISCLOSED molecule?
│   │   │   ├─ YES → DEDUPLICATED (add identifiers + batch to existing)
│   │   │   └─ NO
│   │   │       ├─ Identifiers match existing UNDISCLOSED molecule?
│   │   │       │   ├─ YES (single match) → Disclosure path:
│   │   │       │   │   ├─ Apply SMILES to undisclosed molecule
│   │   │       │   │   ├─ Compute InChIKey of disclosed SMILES
│   │   │       │   │   ├─ InChIKey matches ANOTHER disclosed molecule?
│   │   │       │   │   │   ├─ YES → MERGE_CANDIDATE (needs confirmation)
│   │   │       │   │   │   └─ NO → DISCLOSED (structure applied, done)
│   │   │       │   ├─ YES (multiple matches) → CONFLICT (ambiguous)
│   │   │       │   └─ NO → REGISTERED (new molecule)
│   │
│   └─ NO (no SMILES)
│       ├─ Identifiers match existing molecule (any status)?
│       │   ├─ YES → DEDUPLICATED (add missing identifiers + batch)
│       │   └─ NO → REGISTERED as undisclosed
```

### Identifier Matching Rules

New repository method: `find_undisclosed_by_identifiers(workspace_id, identifiers) -> Molecule | None`

- Compare row identifiers against `molecule_identifiers` table for undisclosed molecules in same workspace
- Name-to-name match (case-insensitive, stripped)
- Custom ID value match (e.g., vendor ID "SACC-0419109")
- **Single match** → proceed with disclosure
- **Multiple matches** → CONFLICT (ambiguous, user must resolve)
- **No match** → not a disclosure, continue to normal registration

### Conflict Scenarios (Always Require Human Review)

| Scenario | Result | Applies To |
|----------|--------|-----------|
| Identifier matches 2+ undisclosed molecules | CONFLICT — ambiguous | All callers |
| CAS number on row conflicts with CAS on matched molecule | CONFLICT — CAS mismatch | All callers |
| Row SMILES identifier matches a disclosed molecule with different InChIKey | CONFLICT — structure mismatch | All callers |

Conflicts **never auto-resolve**, even with `auto_approve=True`. API responses include `conflicts_count: int` flag so callers know human intervention is needed.

### Shared Temporal Activity

```python
@activity.defn
async def process_registration_chunk(
    items: list[BulkRowInput],
    workspace_id: uuid.UUID,
    originating_org_id: uuid.UUID | None,
    auto_approve: bool,
) -> list[RegistrationOutcome]:
    """Shared activity — called by both bulk wizard and CDD import workflows."""
    register_uc = get_use_case(RegisterMolecule)
    results = []
    for item in items:
        outcome = await register_uc(RegisterMoleculeCommand(
            workspace_id=workspace_id,
            name=item.name,
            smiles=item.smiles,
            auto_approve=auto_approve,
            ...
        ))
        results.append(outcome)
    return results
```

CDD import workflow refactored to use this same activity with `auto_approve=True`.

### Temporal Workflow

```python
@workflow.defn
class BulkRegistrationWorkflow:
    def __init__(self):
        self.progress = Progress(current=0, total=0)
        self.results = ProcessingResults.empty()

    @workflow.run
    async def run(self, input: BulkRegistrationInput) -> ProcessingResults:
        self.progress.total = len(input.items)

        for chunk in chunked(input.items, 50):
            chunk_results = await workflow.execute_activity(
                process_registration_chunk,
                args=[chunk, input.workspace_id, input.originating_org_id, input.auto_approve],
                start_to_close_timeout=timedelta(minutes=5),
            )
            self.results.merge(chunk_results)
            self.progress.current += len(chunk)

            if self.progress.current % 250 == 0:
                workflow.continue_as_new(...)

        return self.results

    @workflow.query
    def get_progress(self) -> ProgressReport:
        return ProgressReport(
            progress=self.progress,
            counts=self.results.summary_counts(),
        )
```

### Endpoints

| Endpoint | Type | Purpose |
|----------|------|---------|
| `POST /api/v1/molecules` | Modified | Returns richer `RegistrationOutcome` with action enum. Single mode wizard hits this. |
| `POST /api/v1/molecules/bulk` | Modified | Starts Temporal workflow, returns `job_id`. Bulk mode wizard hits this. |
| `GET /api/v1/molecules/bulk/{job_id}/status` | New | Queries Temporal workflow progress via workflow query. |
| `POST /api/v1/molecules/bulk/{job_id}/confirm-merges` | New | Batch confirm/reject merge candidates. Calls existing `ConfirmDisclosure`/`RejectDisclosure` per decision. |

---

## Frontend Changes

### Merge Candidate Review UX (Bulk Results Step)

```
Step 3: Results                                          247 compounds processed
┌─────────────────────────────────────────────────────────────────────────────┐
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌────────────────┐ ┌──────────┐  │
│  │ ✓ 189    │ │ ✓ 31     │ │ ✓ 18      │ │ ⚠ 4 Need Review│ │ ✕ 5      │  │
│  │Registered│ │Deduped   │ │Disclosed  │ │Merge Candidates│ │Conflicts │  │
│  └──────────┘ └──────────┘ └───────────┘ └────────────────┘ └──────────┘  │
│                                                                           │
│  [Tab: All] [Tab: Merge Candidates (4)] [Tab: Conflicts (5)]             │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  Merge Candidates                        [ ✓ Confirm All ] [ ✕ Reject All]│
│                                                                           │
│  ┌─ ☑ ────────────────────────────────────────────────────────────────┐   │
│  │ SACC-0419109 → Aspirin (CV-00012)                                 │   │
│  │ Source: undisclosed, 3 batches, 47 readouts  │ Target: disclosed  │   │
│  │ ▸ Show impact details                                             │   │
│  │ No blockers                                               [undo]  │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│  ┌─ ☐ ────────────────────────────────────────────────────────────────┐   │
│  │ XYZ-3390 → CV-00102                                               │   │
│  │ Source: undisclosed, 8 batches, 203 readouts │ Target: disclosed  │   │
│  │ ▸ Show impact details                                             │   │
│  │ 🔴 2 active sample requests block this merge             [undo]  │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                           │
│  Conflicts (5) — resolve manually on compound detail pages                │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │ ROW 34: "ABC-100" — matches 2 undisclosed compounds (ambiguous)   │   │
│  │ ROW 89: "DEF-200" — CAS mismatch with matched compound           │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                           │
│                                  [ Back ] [ Confirm Selected & Continue ] │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Behavior:**
- All merge candidates start checked (pre-selected for confirm)
- Blocked candidates unchecked with checkbox disabled — blocker reason shown in red
- "Confirm All" / "Reject All" toggles all non-blocked candidates
- Expand "Show impact details" — reuses `MergeImpactSection` from Phase A
- "Confirm Selected & Continue" — calls confirm-merges endpoint, advances to summary
- Unresolved candidates stay as `pending_confirmation` — visible in Review Queue

### Component Architecture

**New files:**
```
frontend/src/features/chemical-registration/
  components/registration-wizard/
    registration-wizard.tsx          # Wizard shell — step engine, navigation, guards
    step-input.tsx                   # Step 1: mode toggle + single form / bulk upload
    step-processing.tsx              # Step 2: spinner (single) / progress bar (bulk)
    step-results.tsx                 # Step 3: categorized outcomes + merge review
    step-batch.tsx                   # Step 4: optional batch fields (single only)
    step-summary.tsx                 # Step 5: final counts + links
    merge-candidate-card.tsx         # Expandable merge candidate row with checkbox
    bulk-preview-table.tsx           # CSV/SDF parsed rows preview before submit
    processing-progress.tsx          # Temporal polling progress display
  hooks/
    use-registration-wizard.ts       # Zustand store
    use-submit-registration.ts       # Single mode submission
    use-bulk-registration.ts         # Bulk submit + polling
    use-confirm-merges.ts            # Batch confirm/reject
  types/
    registration-wizard.ts           # Wizard-specific types

frontend/src/app/(dashboard)/compounds/register/
  page.tsx                           # Route → renders RegistrationWizard
```

**Backend new files:**
```
backend/src/cellar/
  infrastructure/temporal/
    workflows/bulk_registration_workflow.py
    activities/registration_activity.py
  interface/routes/registration.py       # Bulk status + confirm-merges endpoints
```

### What Gets Deleted

| File | Reason |
|------|--------|
| `molecule-registration-dialog.tsx` | Replaced by wizard |
| `DisclosureSection` in `overview-tab.tsx` | Replaced by wizard link |
| Hash-fragment `#disclose` handling | No longer needed |
| `BulkRegistrationService` (backend) | Deleted — logic moves to Temporal workflow + shared activity |

### What Stays

| Component | Why |
|-----------|-----|
| Merge preview page (`/compounds/[id]/merge-preview/[disclosureId]`) | Phase A disclosures still in `pending_confirmation` need resolution |
| Admin Operations tab (manual merge) | Independent admin feature |
| Existing `/api/v1/disclosures/*` endpoints | Still called internally by confirm-merges |

---

## Entry Point Changes

| Current | After Phase B |
|---------|--------------|
| "Register" button → modal dialog | "Register" → `/compounds/register` |
| "Bulk Register" button → bulk dialog | "Bulk Register" → `/compounds/register?mode=bulk` |
| "Disclose" on compound list → `/compounds/{id}#disclose` | "Disclose" → `/compounds/register?disclose={moleculeId}` |
| Inline disclosure form on overview tab | Removed — banner with link: "This compound is undisclosed. [Disclose it →]" |

---

## Review Queue

Rename existing disclosure conflicts list to **Review Queue**. Covers:

| Status | Source | Action |
|--------|--------|--------|
| `conflict` | Any caller (wizard, API, CDD) | Manual resolution on compound detail |
| `pending_confirmation` | Wizard with `auto_approve=False` | Confirm/reject merge |

Accessible from sidebar nav. Query: `DisclosureRequest WHERE status IN (conflict, pending_confirmation)`.

---

## Component Reuse Map

| Existing Component | Reused By |
|--------------------|-----------|
| `MergeImpactSection` | Embedded in `merge-candidate-card.tsx` on expand |
| `useMergeImpact` hook | Called per candidate in results step |
| `RegisterMolecule` use case | Core of `process_registration_chunk` shared activity |
| `DisclosureService` | Called by `RegisterMolecule` on identifier match |
| `ConfirmDisclosure` / `RejectDisclosure` | Called by confirm-merges endpoint |
| CDD Temporal patterns (chunking, continue-as-new, query) | `BulkRegistrationWorkflow` follows same structure |
