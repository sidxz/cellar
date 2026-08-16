# Follow-up batch — V1.5 quick wins + scaffold filter criterion + Sonner toast — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Waves 0 + 1 + 4 from the agreed 7-wave plan: A1 (disable Add/Remove on frozen), A2 (inline-edit collection name), B1+B2+B3 (scaffold filter criterion + ergonomic loop closer from scaffold-tree-node), C1 (Sonner toast for scaffold-tree async compute).

**Spec:** `docs/superpowers/specs/2026-05-17-followup-batch-design.md` (commit `1e778631`).

**Architecture:** Six discrete, independently-shippable tasks. Each touches its own surface (collection-detail, collection-header, BE search composer, FE criterion-rows + builder, scaffold-tree-node + search-page handoff, scaffold-tree-view toast). No shared refactors between tasks. Branch `prot-2`, no separate branch.

**Tech Stack:** Python 3.13+ / FastAPI / SQLAlchemy 2.0 async / RDKit / Pydantic v2 / pytest (BE). Next.js 16 / React 19 / TypeScript / shadcn/ui / TanStack Query v5 / sonner / vitest + jest-dom (FE).

---

## File structure (overview)

**New files:**
- `frontend/src/features/research-organization/lib/scaffold-search-handoff.ts` — small helper (`STORAGE_KEY` constant + `stash(scaffold_smiles)` + `consume()`). Shared between scaffold-tree-node (B3 stasher) and search-page (B3 consumer) so neither side hard-codes the storage key.
- `frontend/src/features/research-organization/hooks/use-inline-edit-collection-name.ts` — A2 hook (optimistic state, mutation wrapper, revert on error).
- `frontend/src/features/research-organization/components/criterion-rows/scaffold-rows.tsx` — B2 row component (kept in its own file rather than dumped into advanced-rows.tsx; the existing rows are organized by topic — structure/scaffold belong together but the existing structure-rows.tsx already has its own complexity, so a dedicated file is the cleanest fit).

**Modified files:**
- `frontend/src/features/research-organization/components/collection-detail.tsx` — A1 disable Add/Remove on frozen.
- `frontend/src/features/research-organization/components/collection/collection-header.tsx` — A2 inline-edit name affordance.
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_structure_query.py` — B1 `_scaffold_clause` (RDKit-touching, parallel to other chemistry-aware clauses).
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/search_query_composer.py` — B1 dispatch case + re-export.
- `frontend/src/features/research-organization/types/index.ts` — B2 `ScaffoldCriterion` interface + `CriterionType` union extension.
- `frontend/src/features/research-organization/lib/search-query-config.ts` — B2 `defaultScaffoldCriterion()`.
- `frontend/src/features/research-organization/components/criterion-rows/index.ts` — B2 re-export the new row.
- `frontend/src/features/research-organization/components/search-query-builder.tsx` — B2 dispatch case + dropdown option.
- `frontend/src/features/sar-analysis/components/scaffold-tree-node.tsx` — B3 hover action icon.
- `frontend/src/features/research-organization/components/search-page.tsx` — B3 sessionStorage hydration effect.
- `frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx` — C1 Sonner toast effect + Cancel wiring.

**New test files:**
- `backend/tests/unit/test_search_query_composer_scaffold.py` — B1 tests (4 cases: exact_match hit + miss, acyclic_only, negation).
- `frontend/src/features/research-organization/components/criterion-rows/scaffold-rows.test.tsx` — B2 row tests.
- `frontend/src/features/research-organization/lib/scaffold-search-handoff.test.ts` — B3 stash/consume tests.
- `frontend/src/features/sar-analysis/components/scaffold-tree-node.test.tsx` — B3 hover-action test (the file already exists — add cases).
- `frontend/src/features/sar-analysis/components/scaffold-tree-view.test.tsx` — C1 toast test cases (the file already exists — add cases).

**Modified test files:**
- `frontend/src/features/research-organization/components/collection/collection-header.test.tsx` — A2 inline-edit cases.
- New file: `frontend/src/features/research-organization/components/collection-detail.test.tsx` (none exists currently — add a focused test for A1's frozen-disable behavior).

---

## Task 1 — A1: Disable Add/Remove on frozen collections

**Files:**
- Modify: `frontend/src/features/research-organization/components/collection-detail.tsx` (lines 99–113 selectionToolbar + lines 140–143 Add Molecules button)
- Create: `frontend/src/features/research-organization/components/collection-detail.test.tsx`

**Surface boundary:** Disable ONLY the membership-affecting buttons (Add Molecules + Remove from selection toolbar). Edit/Delete/Export SDF stay enabled because frozen collections block membership changes, not metadata (per `docs/domain-model/05-research-organization.md`).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/research-organization/components/collection-detail.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CollectionDetail } from "./collection-detail";

// Stub Next.js + Sentinel + every downstream hook so we exercise ONLY the
// frozen-button gating logic in CollectionDetail itself.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@duar-auth/nextjs", () => ({
  useAuthzHasRole: () => false,
}));

const mockUseCollection = vi.fn();
const mockUseCollectionSearch = vi.fn();
vi.mock("../hooks/use-collections", () => ({
  useCollection: (...args: unknown[]) => mockUseCollection(...args),
  useDeleteCollection: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("../hooks/use-collection-search", () => ({
  useCollectionSearch: (...args: unknown[]) => mockUseCollectionSearch(...args),
}));
vi.mock("../hooks/use-collection-molecules", () => ({
  useRemoveMolecules: () => ({ mutateAsync: vi.fn() }),
}));
vi.mock("../hooks/use-projects", () => ({
  useProject: () => ({ data: null }),
}));
vi.mock("../hooks/use-protocol-test-counts", () => ({
  useProtocolTestCounts: () => ({ data: {} }),
}));
vi.mock("@/features/chemical-registration/hooks/use-sdf-export", () => ({
  useSdfExport: () => ({ exportSdf: vi.fn() }),
}));

// Stub the heavy children so we don't pull AG Grid / RDKit.js etc. into jsdom.
vi.mock("./create-collection-dialog", () => ({ CreateCollectionDialog: () => null }));
vi.mock("./add-molecules-dialog", () => ({ AddMoleculesDialog: () => null }));
vi.mock("./collection/collection-header", () => ({
  CollectionHeader: ({ rightSlot }: { rightSlot?: React.ReactNode }) => (
    <div>{rightSlot}</div>
  ),
}));
vi.mock("./results/results-surface", () => ({ ResultsSurface: () => <div /> }));
vi.mock("./results/view-mode-toggle", () => ({ ViewModeToggle: () => <div /> }));
vi.mock("@/shared/components/detail-shell", () => ({
  DetailShell: ({
    query,
    actions,
    children,
  }: {
    query: { data: unknown };
    actions: () => React.ReactNode;
    children: (c: unknown) => React.ReactNode;
  }) => (
    <div>
      <div>{actions()}</div>
      <div>{children(query.data)}</div>
    </div>
  ),
}));
vi.mock("@/shared/components/admin-delete-button", () => ({
  AdminDeleteButton: () => null,
}));
vi.mock("@/shared/components/confirm-delete-dialog", () => ({
  ConfirmDeleteDialog: () => null,
}));

const baseCollection = {
  id: "c1",
  name: "Frozen Set",
  description: null,
  project_id: null,
  owned_by_org_id: null,
  created_by: "u1",
  visibility: "private" as const,
  molecule_count: 5,
  is_frozen: false,
  derived_from_campaign_id: null,
};

function renderWith(collection: typeof baseCollection) {
  mockUseCollection.mockReturnValue({ data: collection, isLoading: false });
  mockUseCollectionSearch.mockReturnValue({
    data: { items: [{ id: "m1" }, { id: "m2" }] },
    isLoading: false,
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CollectionDetail collectionId="c1" />
    </QueryClientProvider>,
  );
}

describe("CollectionDetail frozen-collection gating", () => {
  it("enables Add Molecules when not frozen", () => {
    renderWith({ ...baseCollection, is_frozen: false });
    const btn = screen.getByRole("button", { name: /add molecules/i });
    expect(btn).not.toBeDisabled();
  });

  it("disables Add Molecules when frozen, with a tooltip-style title", () => {
    renderWith({ ...baseCollection, is_frozen: true });
    const btn = screen.getByRole("button", { name: /add molecules/i });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute(
      "title",
      "Frozen collection — unfreeze to modify.",
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/collection-detail.test.tsx`
Expected: FAIL — second assertion fails because the Add button has no `disabled` attribute today.

- [ ] **Step 3: Modify collection-detail.tsx to gate the buttons**

In `frontend/src/features/research-organization/components/collection-detail.tsx`:

a) Replace the selectionToolbar useMemo (lines 99–113) with:

```tsx
const isFrozen = query.data?.is_frozen ?? false;

const selectionToolbar = useMemo(() => {
  if (selectedIds.size === 0) return null;
  return (
    <>
      <span className="text-xs text-muted-foreground">{selectedIds.size} selected</span>
      <Button
        size="sm"
        variant="destructive"
        onClick={() => setRemoveOpen(true)}
        disabled={isFrozen}
        title={
          isFrozen
            ? "Frozen collection — unfreeze to modify."
            : undefined
        }
      >
        Remove
      </Button>
    </>
  );
}, [selectedIds.size, isFrozen]);
```

b) Replace the Add Molecules button (around line 140) with:

```tsx
<Button
  size="sm"
  onClick={() => setAddMolOpen(true)}
  disabled={isFrozen}
  title={
    isFrozen ? "Frozen collection — unfreeze to modify." : undefined
  }
>
  <Plus className="mr-2 h-4 w-4" />
  Add Molecules
</Button>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/collection-detail.test.tsx`
Expected: PASS — both cases.

- [ ] **Step 5: Run the full FE test suite to confirm no regressions**

Run: `cd frontend && pnpm vitest run src/features/research-organization/`
Expected: PASS — all research-organization tests.

- [ ] **Step 6: Confirm typecheck clean**

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/research-organization/components/collection-detail.tsx \
        frontend/src/features/research-organization/components/collection-detail.test.tsx
git commit -m "$(cat <<'EOF'
feat(collections): disable Add/Remove on frozen collections (Wave 0 / A1)

is_frozen blocks membership changes, not metadata — Edit / Delete /
Export SDF stay enabled; only Add Molecules + Remove (selection toolbar)
gate on the frozen state. Tooltip on disabled buttons explains why.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 — A2: Inline-edit collection name

**Files:**
- Modify: `frontend/src/features/research-organization/components/collection/collection-header.tsx`
- Create: `frontend/src/features/research-organization/hooks/use-inline-edit-collection-name.ts`
- Modify: `frontend/src/features/research-organization/components/collection/collection-header.test.tsx`

**Behavior:** The collection name in `<DetailShell title>` is owned by DetailShell and not editable inline — A2 instead adds inline edit on the name as it appears in the CollectionHeader strip. But looking at the current strip (collection-header.tsx), the name is **NOT rendered there** at all; only badges + meta + created-by + rightSlot. So we need to ADD a name display in CollectionHeader AND make it click-to-edit. DetailShell's `<h1>` becomes the read-only canonical display; the in-strip inline-edit is the editing affordance.

**Decision:** Put the inline-editable name as the FIRST element of the meta strip (before badges), styled as a heading-weight span. On click → input field. On Enter/blur → save via existing PATCH; Escape → revert. The DetailShell `<h1>` above stays as-is (and updates after a save because React-Query invalidates the collection cache).

- [ ] **Step 1: Write the hook test first**

Create `frontend/src/features/research-organization/hooks/use-inline-edit-collection-name.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useInlineEditCollectionName } from "./use-inline-edit-collection-name";

const mockMutate = vi.fn();
vi.mock("./use-collections", () => ({
  useUpdateCollection: () => ({
    mutate: mockMutate,
    isPending: false,
  }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useInlineEditCollectionName", () => {
  it("commit() fires the mutation with the new name", () => {
    mockMutate.mockClear();
    const { result } = renderHook(
      () => useInlineEditCollectionName("c1", "Original"),
      { wrapper },
    );
    act(() => result.current.startEdit());
    act(() => result.current.setDraft("Updated"));
    act(() => result.current.commit());
    expect(mockMutate).toHaveBeenCalledTimes(1);
    expect(mockMutate.mock.calls[0][0]).toEqual({
      id: "c1",
      data: { name: "Updated" },
    });
  });

  it("commit() with unchanged draft is a no-op (skip the round-trip)", () => {
    mockMutate.mockClear();
    const { result } = renderHook(
      () => useInlineEditCollectionName("c1", "Original"),
      { wrapper },
    );
    act(() => result.current.startEdit());
    act(() => result.current.commit());
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it("commit() with whitespace-only draft is rejected (no-op)", () => {
    mockMutate.mockClear();
    const { result } = renderHook(
      () => useInlineEditCollectionName("c1", "Original"),
      { wrapper },
    );
    act(() => result.current.startEdit());
    act(() => result.current.setDraft("   "));
    act(() => result.current.commit());
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it("cancel() resets the draft and exits edit mode", () => {
    const { result } = renderHook(
      () => useInlineEditCollectionName("c1", "Original"),
      { wrapper },
    );
    act(() => result.current.startEdit());
    act(() => result.current.setDraft("Changed"));
    act(() => result.current.cancel());
    expect(result.current.isEditing).toBe(false);
    expect(result.current.draft).toBe("Original");
  });
});
```

- [ ] **Step 2: Run the hook test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/research-organization/hooks/use-inline-edit-collection-name.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the hook**

Create `frontend/src/features/research-organization/hooks/use-inline-edit-collection-name.ts`:

```ts
"use client";

import { useCallback, useEffect, useState } from "react";
import { useUpdateCollection } from "./use-collections";

export interface UseInlineEditCollectionName {
  isEditing: boolean;
  draft: string;
  isPending: boolean;
  startEdit: () => void;
  cancel: () => void;
  commit: () => void;
  setDraft: (next: string) => void;
}

export function useInlineEditCollectionName(
  collectionId: string,
  currentName: string,
): UseInlineEditCollectionName {
  const update = useUpdateCollection();
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(currentName);

  useEffect(() => {
    if (!isEditing) setDraft(currentName);
  }, [currentName, isEditing]);

  const startEdit = useCallback(() => {
    setDraft(currentName);
    setIsEditing(true);
  }, [currentName]);

  const cancel = useCallback(() => {
    setDraft(currentName);
    setIsEditing(false);
  }, [currentName]);

  const commit = useCallback(() => {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === currentName) {
      setIsEditing(false);
      setDraft(currentName);
      return;
    }
    update.mutate({ id: collectionId, data: { name: trimmed } });
    setIsEditing(false);
  }, [draft, currentName, collectionId, update]);

  return {
    isEditing,
    draft,
    isPending: update.isPending,
    startEdit,
    cancel,
    commit,
    setDraft,
  };
}
```

- [ ] **Step 4: Run hook test to verify pass**

Run: `cd frontend && pnpm vitest run src/features/research-organization/hooks/use-inline-edit-collection-name.test.tsx`
Expected: PASS — all 4 cases.

- [ ] **Step 5: Add the inline-edit affordance test to CollectionHeader test file**

Append to `frontend/src/features/research-organization/components/collection/collection-header.test.tsx` (inside the existing `describe`):

```tsx
import { fireEvent } from "@testing-library/react";

// Add to the existing vi.mock block at top of file: mock the inline-edit hook
vi.mock("@/features/research-organization/hooks/use-inline-edit-collection-name", () => ({
  useInlineEditCollectionName: () => ({
    isEditing: false,
    draft: "Mtb Q1 Hits",
    isPending: false,
    startEdit: vi.fn(),
    cancel: vi.fn(),
    commit: vi.fn(),
    setDraft: vi.fn(),
  }),
}));

// Inside the existing describe block, add:
it("renders the name as a clickable inline-edit affordance", () => {
  render(<CollectionHeader collection={baseCollection} projectName="Mtb-TB" />);
  const trigger = screen.getByRole("button", { name: /Mtb Q1 Hits/ });
  expect(trigger).toBeInTheDocument();
});
```

NOTE: the existing test file does not import `fireEvent` yet — add it to the existing testing-library import line.

- [ ] **Step 6: Run header test — verify it fails (no button yet)**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/collection/collection-header.test.tsx`
Expected: FAIL on the new case ("renders the name as a clickable inline-edit affordance") — `getByRole("button", { name: /Mtb Q1 Hits/ })` not found.

- [ ] **Step 7: Modify CollectionHeader to render the inline-editable name**

In `frontend/src/features/research-organization/components/collection/collection-header.tsx`:

a) Add imports at top:

```tsx
import { useInlineEditCollectionName } from "@/features/research-organization/hooks/use-inline-edit-collection-name";
import { useRef, useEffect } from "react";
```

b) Inside the `CollectionHeader` function body, before the return, add:

```tsx
const edit = useInlineEditCollectionName(collection.id, collection.name);
const inputRef = useRef<HTMLInputElement | null>(null);

useEffect(() => {
  if (edit.isEditing) inputRef.current?.focus();
}, [edit.isEditing]);
```

c) Inside the JSX, replace the first child of the meta-strip div (the `<div className="flex items-center gap-x-3 gap-y-1 flex-wrap text-xs text-muted-foreground">` block) with a sibling sequence that puts the name first. Specifically change the structure to:

```tsx
{/* Single-row meta strip */}
<div className="flex items-center gap-x-3 gap-y-1 flex-wrap">
  {/* Inline-editable name — leads the strip; reads as a heading at base size */}
  {edit.isEditing ? (
    <input
      ref={inputRef}
      className="text-sm font-medium bg-background border rounded px-2 py-0.5 outline-none focus-visible:ring-2 focus-visible:ring-ring"
      value={edit.draft}
      onChange={(e) => edit.setDraft(e.target.value)}
      onBlur={edit.commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          edit.commit();
        } else if (e.key === "Escape") {
          e.preventDefault();
          edit.cancel();
        }
      }}
    />
  ) : (
    <button
      type="button"
      className="text-sm font-medium text-foreground hover:bg-muted rounded px-1 -mx-1"
      onClick={edit.startEdit}
      title="Click to rename"
    >
      {collection.name}
    </button>
  )}

  {/* Left: badges + meta links + created-by */}
  <div className="flex items-center gap-x-3 gap-y-1 flex-wrap text-xs text-muted-foreground">
    {/* ...existing badges + links + created-by content unchanged... */}
  </div>
  {/* Right slot unchanged */}
  {rightSlot && (
    <div className="ml-auto flex items-center gap-2">{rightSlot}</div>
  )}
</div>
```

The existing badges/links/created-by content (lines 41–83 of the current file) stays inside the inner `<div>` exactly as-is — only the outer ordering changes to put the new inline-name editor first.

- [ ] **Step 8: Run header tests — verify all pass**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/collection/collection-header.test.tsx`
Expected: PASS — all 8 cases (7 existing + 1 new).

- [ ] **Step 9: Confirm typecheck clean + research-org test suite**

Run: `cd frontend && pnpm exec tsc --noEmit`
Run: `cd frontend && pnpm vitest run src/features/research-organization/`
Expected: both pass.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/features/research-organization/hooks/use-inline-edit-collection-name.ts \
        frontend/src/features/research-organization/hooks/use-inline-edit-collection-name.test.tsx \
        frontend/src/features/research-organization/components/collection/collection-header.tsx \
        frontend/src/features/research-organization/components/collection/collection-header.test.tsx
git commit -m "$(cat <<'EOF'
feat(collections): inline-edit collection name in CollectionHeader (Wave 0 / A2)

Click name → input. Enter or blur saves via PATCH; Escape reverts.
Whitespace-only and unchanged drafts are no-ops (skip the round-trip).
Existing Edit dialog stays as the fallback for description/visibility.

Frozen-state intentionally does NOT gate the name edit — is_frozen only
blocks membership changes per the domain rules. Confirmed during smoke.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 — B1: Backend `_scaffold_clause` + tests

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_structure_query.py` (add `_scaffold_clause`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/search_query_composer.py` (import + dispatch + `__all__`)
- Create: `backend/tests/unit/test_search_query_composer_scaffold.py`

**Wire shape:**

```jsonc
// exact_match mode (default)
{
  "type": "scaffold",
  "mode": "exact_match",
  "scaffold_smiles": "c1ccc2ncccc2c1",
  "negate": false
}
// acyclic_only mode (no SMILES required)
{
  "type": "scaffold",
  "mode": "acyclic_only",
  "negate": false
}
```

**SQL produced:**
- `exact_match`: `molecules.bemis_murcko_smiles = :canonical_input`
- `acyclic_only`: `molecules.bemis_murcko_smiles = ''`

**Canonicalization:** parse input SMILES via `Chem.MolFromSmiles()`, then `MurckoScaffoldCalculator().compute(mol)` to get canonical scaffold SMILES (idempotent for valid scaffolds, normalizes full-molecule paste). On parse failure or `None` return, raise `ValueError` (mirrors the validation pattern in `_text_clause` / `_property_clause`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/test_search_query_composer_scaffold.py`:

```python
"""Unit tests for the scaffold criterion clause."""

from __future__ import annotations

import uuid

import pytest

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (
    compose_criteria,
)

_WS = uuid.UUID("00000000-0000-0000-0000-ffffffffffff")


def _compose(query: dict) -> object:
    return compose_criteria(query, workspace_id=_WS)


class TestScaffoldClause:
    def test_exact_match_emits_equality_on_bemis_murcko_smiles(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "exact_match",
                    "scaffold_smiles": "c1ccncc1",  # pyridine
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "bemis_murcko_smiles" in sql
        assert "=" in sql
        # Canonicalized form of pyridine should appear (RDKit canonical SMILES)
        assert "c1ccncc1" in sql or "c1cnccc1" in sql or "n1ccccc1" in sql

    def test_exact_match_canonicalizes_full_molecule_paste(self) -> None:
        """Pasting a full molecule should match against ITS scaffold."""
        # 2-aminopyridine → scaffold is pyridine (c1ccncc1).
        # Compose with the full mol; the WHERE clause should compare
        # against the canonical pyridine SMILES.
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "exact_match",
                    "scaffold_smiles": "Nc1ccccn1",  # 2-aminopyridine (full mol)
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        # The amine nitrogen ("N") of the input should be GONE — only the
        # ring scaffold remains. Verify "N" is not present as an aliphatic
        # atom (the aromatic "n" of pyridine itself is fine).
        # The canonical scaffold SMILES has only lowercase aromatic atoms.
        assert "Nc1" not in sql  # No leftover amine.
        # The bound parameter should be a 5-or-6 character pyridine-ish form
        # — assert presence of the column lookup at minimum.
        assert "bemis_murcko_smiles" in sql

    def test_acyclic_only_emits_equality_against_empty_string(self) -> None:
        clause = _compose({
            "criteria": [
                {"type": "scaffold", "mode": "acyclic_only"}
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "bemis_murcko_smiles" in sql
        assert "''" in sql or "=" in sql

    def test_negation_inverts_the_clause(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "acyclic_only",
                    "negate": True,
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        # SQLAlchemy "~ (col = '')" compiles to "col != ''" — accept either form
        assert "bemis_murcko_smiles" in sql
        assert "!=" in sql or "NOT" in sql.upper() or "<>" in sql

    def test_exact_match_without_scaffold_smiles_raises(self) -> None:
        with pytest.raises((ValueError, KeyError)):
            _compose({
                "criteria": [
                    {"type": "scaffold", "mode": "exact_match"}
                ],
                "logic": "and",
            })

    def test_exact_match_with_unparseable_smiles_raises(self) -> None:
        with pytest.raises(ValueError):
            _compose({
                "criteria": [
                    {
                        "type": "scaffold",
                        "mode": "exact_match",
                        "scaffold_smiles": "not-a-smiles!!@@",
                    }
                ],
                "logic": "and",
            })

    def test_unknown_mode_raises(self) -> None:
        with pytest.raises(ValueError):
            _compose({
                "criteria": [
                    {
                        "type": "scaffold",
                        "mode": "substructure",  # not supported in V1
                        "scaffold_smiles": "c1ccccc1",
                    }
                ],
                "logic": "and",
            })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/test_search_query_composer_scaffold.py -v`
Expected: FAIL on all 7 cases — `compose_criteria` raises `ValueError("Unknown criterion type: scaffold")`.

- [ ] **Step 3: Implement `_scaffold_clause`**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_structure_query.py`, add at the bottom of the file (use the existing import of `Chem` from rdkit at top of file; if not present, add `from rdkit import Chem`):

```python
def _scaffold_clause(criterion: dict[str, Any]) -> ColumnElement:
    """WHERE clause for {type: 'scaffold'} criteria.

    Supports two modes:
      - 'exact_match': molecules.bemis_murcko_smiles == canonical(input)
        Input is canonicalized via Bemis-Murcko computation so a paste of
        the full molecule normalizes to its scaffold (forgiving behavior).
      - 'acyclic_only': molecules.bemis_murcko_smiles == ''
        Matches the V2 'no scaffold' bucket (acyclic compounds; RDKit
        convention writes the empty string for these).

    Raises ValueError on unknown mode or unparseable scaffold_smiles.
    """
    from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
        MoleculeModel,
    )
    from cellar.infrastructure.rdkit.scaffold_calculator import (
        MurckoScaffoldCalculator,
    )

    mode = criterion.get("mode", "exact_match")

    if mode == "acyclic_only":
        return MoleculeModel.bemis_murcko_smiles == ""

    if mode == "exact_match":
        raw = criterion.get("scaffold_smiles")
        if not raw:
            msg = "scaffold criterion: 'exact_match' mode requires 'scaffold_smiles'"
            raise ValueError(msg)
        mol = Chem.MolFromSmiles(raw)
        if mol is None:
            msg = f"scaffold criterion: invalid SMILES {raw!r}"
            raise ValueError(msg)
        canonical = MurckoScaffoldCalculator().compute(mol)
        if canonical is None:
            msg = f"scaffold criterion: failed to compute scaffold for {raw!r}"
            raise ValueError(msg)
        return MoleculeModel.bemis_murcko_smiles == canonical

    msg = f"scaffold criterion: unknown mode {mode!r} (allowed: exact_match, acyclic_only)"
    raise ValueError(msg)
```

NOTE: Confirm `MoleculeModel` is the correct model class name + path by reading the existing model file at `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/models.py`. If the actual class name differs (e.g. just `Molecule`), use that.

- [ ] **Step 4: Wire dispatch + re-export in the composer**

In `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/search_query_composer.py`:

a) Update the `_structure_query` import block (around line 51) to include `_scaffold_clause`:

```python
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration._structure_query import (
    _compute_query_bytes,
    _default_registry,
    _parse_metric,
    _resolve_algorithm_and_metric,
    _scaffold_clause,
    _similarity_clause,
    _structure_clause,
    _substructure_clause,
)
```

b) Add `"_scaffold_clause"` to the `__all__` list.

c) In `compose_criteria` (around line 110), add a dispatch case before the final `else`:

```python
        elif ctype == "scaffold":
            clause = _scaffold_clause(criterion)
```

d) In `_group_clause` (the nested group recursion further down in the same file, around lines 185–210), also add the same `elif ctype == "scaffold": clause = _scaffold_clause(sub)` branch so nested groups support scaffold criteria too.

- [ ] **Step 5: Run test to verify all pass**

Run: `cd backend && uv run pytest tests/unit/test_search_query_composer_scaffold.py -v`
Expected: PASS — all 7 cases.

- [ ] **Step 6: Run the broader composer test suite for regression**

Run: `cd backend && uv run pytest tests/unit/test_search_query_composer.py tests/unit/test_search_query_composer_scaffold.py -v`
Expected: PASS — both files green.

- [ ] **Step 7: Run mypy / ruff per project linting convention**

Run: `cd backend && uv run ruff check src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_structure_query.py src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/search_query_composer.py`
Expected: clean (no new warnings).

- [ ] **Step 8: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_structure_query.py \
        backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/search_query_composer.py \
        backend/tests/unit/test_search_query_composer_scaffold.py
git commit -m "$(cat <<'EOF'
feat(search): scaffold criterion — exact_match + acyclic_only modes (Wave 1 / B1)

New {type: "scaffold"} criterion on POST /api/v1/search/execute. Two modes:
- exact_match: molecules.bemis_murcko_smiles == canonical(input)
  Forgiving paste — full-molecule SMILES normalizes to its Bemis-Murcko
  scaffold before the compare (so chemists can paste from a SAR table
  without having to strip side chains by hand).
- acyclic_only: molecules.bemis_murcko_smiles == "" (the "no scaffold"
  bucket from V2 scaffold tree; matches acyclic compounds).

No index on bemis_murcko_smiles for V1 — exact equality is fine at
current workspace scale (well under the threshold where a B-tree would
matter). Document the perf gate; add if a chemist reports lag.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 — B2: Frontend ScaffoldCriterion type + row component + builder dispatch

**Files:**
- Modify: `frontend/src/features/research-organization/types/index.ts`
- Modify: `frontend/src/features/research-organization/lib/search-query-config.ts`
- Create: `frontend/src/features/research-organization/components/criterion-rows/scaffold-rows.tsx`
- Modify: `frontend/src/features/research-organization/components/criterion-rows/index.ts`
- Modify: `frontend/src/features/research-organization/components/search-query-builder.tsx`
- Create: `frontend/src/features/research-organization/components/criterion-rows/scaffold-rows.test.tsx`

- [ ] **Step 1: Write the failing test for the row component**

Create `frontend/src/features/research-organization/components/criterion-rows/scaffold-rows.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ScaffoldCriterionRow } from "./scaffold-rows";
import type { ScaffoldCriterion } from "../../types";

const baseExact: ScaffoldCriterion = {
  type: "scaffold",
  mode: "exact_match",
  scaffold_smiles: "",
};

describe("ScaffoldCriterionRow", () => {
  it("renders mode picker + SMILES input in exact_match mode", () => {
    render(
      <ScaffoldCriterionRow
        criterion={baseExact}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.getByPlaceholderText(/scaffold smiles/i)).toBeInTheDocument();
  });

  it("hides the SMILES input in acyclic_only mode", () => {
    render(
      <ScaffoldCriterionRow
        criterion={{ type: "scaffold", mode: "acyclic_only" }}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.queryByPlaceholderText(/scaffold smiles/i)).not.toBeInTheDocument();
  });

  it("emits onChange with the typed SMILES", () => {
    const onChange = vi.fn();
    render(
      <ScaffoldCriterionRow
        criterion={baseExact}
        onChange={onChange}
        onRemove={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText(/scaffold smiles/i), {
      target: { value: "c1ccncc1" },
    });
    expect(onChange).toHaveBeenLastCalledWith({
      type: "scaffold",
      mode: "exact_match",
      scaffold_smiles: "c1ccncc1",
    });
  });

  it("emits onChange when mode switches to acyclic_only (drops smiles)", () => {
    const onChange = vi.fn();
    render(
      <ScaffoldCriterionRow
        criterion={{ ...baseExact, scaffold_smiles: "c1ccncc1" }}
        onChange={onChange}
        onRemove={vi.fn()}
      />,
    );
    // Trigger native onValueChange on the Select — simulate via the toggle.
    // Find the acyclic-only segment trigger by accessible label/text.
    fireEvent.click(screen.getByRole("button", { name: /acyclic/i }));
    expect(onChange).toHaveBeenLastCalledWith({
      type: "scaffold",
      mode: "acyclic_only",
    });
  });

  it("calls onRemove when the trash icon is clicked", () => {
    const onRemove = vi.fn();
    render(
      <ScaffoldCriterionRow
        criterion={baseExact}
        onChange={vi.fn()}
        onRemove={onRemove}
      />,
    );
    // The remove button has only an icon (no accessible text) — same pattern
    // as the other rows. Match it by being the ONLY button without a name
    // in a row that uses mode segments.
    const buttons = screen.getAllByRole("button");
    const trash = buttons.find((b) => b.querySelector("svg") && !b.textContent?.trim());
    expect(trash).toBeDefined();
    if (trash) fireEvent.click(trash);
    expect(onRemove).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/criterion-rows/scaffold-rows.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Add the ScaffoldCriterion type**

In `frontend/src/features/research-organization/types/index.ts`:

a) Update `CriterionType` (around line 172) to include `"scaffold"` (alphabetical placement between `"property"` and `"selectivity"` — or wherever fits the current ordering):

```ts
export type CriterionType =
  | "text"
  | "property"
  | "structure"
  | "scaffold"
  | "activity"
  | "collection"
  | "keyword_list"
  | "run_date"
  | "batch"
  | "project"
  | "selectivity"
  | "group"
  | "custom_field";
```

b) Add the `ScaffoldCriterion` interface (place near the other structure-y interfaces, after `StructureCriterion` around line 230):

```ts
export type ScaffoldMode = "exact_match" | "acyclic_only";

export interface ScaffoldCriterion {
  type: "scaffold";
  mode: ScaffoldMode;
  /** Required when mode is "exact_match"; ignored in acyclic_only. */
  scaffold_smiles?: string;
}
```

c) Update the `SearchCriterionBase` union (around line 372) to include `ScaffoldCriterion`:

```ts
export type SearchCriterionBase =
  | TextCriterion
  | PropertyCriterion
  | StructureCriterion
  | ScaffoldCriterion
  | ActivityCriterion
  | CollectionCriterion
  | KeywordListCriterion
  | RunDateCriterion
  | BatchCriterion
  | ProjectCriterion
  | SelectivityCriterion
  | GroupCriterion
  | CustomFieldCriterion;
```

- [ ] **Step 4: Add the factory**

In `frontend/src/features/research-organization/lib/search-query-config.ts`:

a) Add `ScaffoldCriterion` to the imports at the top.

b) Add the factory after `defaultStructureCriterion` (around line 123):

```ts
export function defaultScaffoldCriterion(): ScaffoldCriterion {
  return { type: "scaffold", mode: "exact_match", scaffold_smiles: "" };
}
```

- [ ] **Step 5: Implement the row component**

Create `frontend/src/features/research-organization/components/criterion-rows/scaffold-rows.tsx`:

```tsx
"use client";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Trash2 } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import type { ScaffoldCriterion, ScaffoldMode } from "../../types";

const MODE_OPTIONS: { value: ScaffoldMode; label: string }[] = [
  { value: "exact_match", label: "Exact match" },
  { value: "acyclic_only", label: "Acyclic only" },
];

export function ScaffoldCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: ScaffoldCriterion;
  onChange: (c: ScaffoldCriterion) => void;
  onRemove: () => void;
}) {
  function handleModeChange(next: ScaffoldMode) {
    if (next === "acyclic_only") {
      onChange({ type: "scaffold", mode: "acyclic_only" });
    } else {
      onChange({
        type: "scaffold",
        mode: "exact_match",
        scaffold_smiles: criterion.scaffold_smiles ?? "",
      });
    }
  }

  return (
    <div className="flex items-end gap-2 flex-wrap">
      {/* Mode picker — segmented control matches the Structure row's pattern */}
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Mode</Label>
        <div className="inline-flex rounded-md border bg-background p-0.5">
          {MODE_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              type="button"
              variant={criterion.mode === opt.value ? "default" : "ghost"}
              size="sm"
              className={cn(
                "h-7 px-3 text-xs",
                criterion.mode === opt.value && "shadow-sm",
              )}
              onClick={() => handleModeChange(opt.value)}
            >
              {opt.label}
            </Button>
          ))}
        </div>
      </div>

      {/* SMILES input — only in exact_match mode */}
      {criterion.mode === "exact_match" && (
        <div className="flex-1 min-w-64">
          <Label className="text-xs text-muted-foreground">Scaffold SMILES</Label>
          <Input
            className="h-9 font-mono text-xs"
            placeholder="Scaffold SMILES (e.g. c1ccc2ncccc2c1)"
            value={criterion.scaffold_smiles ?? ""}
            onChange={(e) =>
              onChange({
                type: "scaffold",
                mode: "exact_match",
                scaffold_smiles: e.target.value,
              })
            }
          />
        </div>
      )}

      <div className="flex-1" />
      <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}
```

- [ ] **Step 6: Re-export from the index**

In `frontend/src/features/research-organization/components/criterion-rows/index.ts`, add:

```ts
export { ScaffoldCriterionRow } from "./scaffold-rows";
```

- [ ] **Step 7: Wire dispatch in SearchQueryBuilder**

In `frontend/src/features/research-organization/components/search-query-builder.tsx`:

a) Import the factory + the row component at the top:

```tsx
import { defaultScaffoldCriterion } from "../lib/search-query-config";
// Update the criterion-rows import block to include ScaffoldCriterionRow:
import {
  ActivityCriterionRow,
  BatchCriterionRow,
  CollectionCriterionRow,
  CustomFieldCriterionRow,
  GroupCriterionRow,
  KeywordListCriterionRow,
  ProjectCriterionRow,
  PropertyCriterionRow,
  RunDateCriterionRow,
  ScaffoldCriterionRow,
  SelectivityCriterionRow,
  StructureCriterionRow,
  TextCriterionRow,
} from "./criterion-rows";
```

b) Add `scaffold: defaultScaffoldCriterion` to the `factories` object inside the dropdown's `onValueChange` (around line 111):

```tsx
const factories: Record<string, () => SearchCriterion> = {
  text: defaultTextCriterion,
  property: defaultPropertyCriterion,
  structure: defaultStructureCriterion,
  scaffold: defaultScaffoldCriterion,
  activity: defaultActivityCriterion,
  collection: defaultCollectionCriterion,
  keyword_list: defaultKeywordListCriterion,
  run_date: defaultRunDateCriterion,
  batch: defaultBatchCriterion,
  project: defaultProjectCriterion,
  selectivity: defaultSelectivityCriterion,
  custom_field: defaultCustomFieldCriterion,
  group: defaultGroupCriterion,
};
```

c) Add a `<SelectItem value="scaffold">Scaffold</SelectItem>` entry to the dropdown's `<SelectContent>` (around line 134), placed alphabetically — between "Project" and "Selectivity":

```tsx
<SelectItem value="project">Project</SelectItem>
<SelectItem value="scaffold">Scaffold</SelectItem>
<SelectItem value="selectivity">Selectivity</SelectItem>
```

d) Add a dispatch case in the criteria switch (around line 247, between "project" and "selectivity"):

```tsx
case "scaffold":
  return wrapWithNegate(
    <ScaffoldCriterionRow
      criterion={criterion}
      onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
      onRemove={() => removeCriterion(index)}
    />,
  );
```

- [ ] **Step 8: Run row test to verify pass**

Run: `cd frontend && pnpm vitest run src/features/research-organization/components/criterion-rows/scaffold-rows.test.tsx`
Expected: PASS — all 5 cases.

- [ ] **Step 9: Run typecheck + full research-org suite**

Run: `cd frontend && pnpm exec tsc --noEmit`
Run: `cd frontend && pnpm vitest run src/features/research-organization/`
Expected: both pass — no regressions on the existing builder tests.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/features/research-organization/types/index.ts \
        frontend/src/features/research-organization/lib/search-query-config.ts \
        frontend/src/features/research-organization/components/criterion-rows/scaffold-rows.tsx \
        frontend/src/features/research-organization/components/criterion-rows/scaffold-rows.test.tsx \
        frontend/src/features/research-organization/components/criterion-rows/index.ts \
        frontend/src/features/research-organization/components/search-query-builder.tsx
git commit -m "$(cat <<'EOF'
feat(search): scaffold filter criterion in SearchQueryBuilder (Wave 1 / B2)

New "Scaffold" entry in the criterion dropdown — sits between Project and
Selectivity (alphabetical). Two modes:
- Exact match: chemist enters a Bemis-Murcko scaffold SMILES; BE canonicalizes
  and matches against molecules.bemis_murcko_smiles. Forgiving paste — a full
  molecule normalizes to its scaffold.
- Acyclic only: matches the V2 "no scaffold" bucket (compounds with no rings).

FE adds the type, factory, row component, and dispatch wire. BE clause from
the prior commit handles the actual matching.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 — B3: Scaffold-tree-node → /search loop closer (sessionStorage handoff)

**Files:**
- Create: `frontend/src/features/research-organization/lib/scaffold-search-handoff.ts`
- Create: `frontend/src/features/research-organization/lib/scaffold-search-handoff.test.ts`
- Modify: `frontend/src/features/sar-analysis/components/scaffold-tree-node.tsx`
- Modify: `frontend/src/features/sar-analysis/components/scaffold-tree-node.test.tsx`
- Modify: `frontend/src/features/research-organization/components/search-page.tsx`

**Why a shared helper:** the storage key + JSON shape need to match exactly on both sides (stash in scaffold-tree-node, consume in search-page). A 30-line helper module with two functions + a `STORAGE_KEY` constant prevents magic-string drift.

- [ ] **Step 1: Write the handoff helper test first**

Create `frontend/src/features/research-organization/lib/scaffold-search-handoff.test.ts`:

```ts
import { afterEach, describe, expect, it } from "vitest";
import {
  STORAGE_KEY,
  stashScaffoldSearch,
  consumeScaffoldSearch,
} from "./scaffold-search-handoff";

afterEach(() => {
  if (typeof window !== "undefined") {
    window.sessionStorage.removeItem(STORAGE_KEY);
  }
});

describe("scaffold-search-handoff", () => {
  it("stashes a scaffold criterion and consume() returns it", () => {
    stashScaffoldSearch("c1ccncc1");
    const result = consumeScaffoldSearch();
    expect(result).toEqual({
      type: "scaffold",
      mode: "exact_match",
      scaffold_smiles: "c1ccncc1",
    });
  });

  it("consume() clears the storage on read (one-shot)", () => {
    stashScaffoldSearch("c1ccncc1");
    consumeScaffoldSearch();
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("consume() returns null when nothing is stashed", () => {
    expect(consumeScaffoldSearch()).toBeNull();
  });

  it("consume() returns null and clears storage on malformed JSON", () => {
    window.sessionStorage.setItem(STORAGE_KEY, "not-json{");
    expect(consumeScaffoldSearch()).toBeNull();
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("stashes the NO_SCAFFOLD sentinel as acyclic_only mode", () => {
    stashScaffoldSearch("");
    expect(consumeScaffoldSearch()).toEqual({
      type: "scaffold",
      mode: "acyclic_only",
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/features/research-organization/lib/scaffold-search-handoff.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the helper**

Create `frontend/src/features/research-organization/lib/scaffold-search-handoff.ts`:

```ts
import type { ScaffoldCriterion } from "../types";

export const STORAGE_KEY = "cellar:pending-search-query";

/**
 * Stash a single scaffold criterion in sessionStorage for the next /search
 * page mount to consume. Used by the scaffold-tree-node action that opens
 * /search pre-filtered for compounds matching a tree node's scaffold.
 *
 * Empty-string input → acyclic_only mode (the V2 "no scaffold" bucket).
 */
export function stashScaffoldSearch(scaffoldSmiles: string): void {
  if (typeof window === "undefined") return;
  const criterion: ScaffoldCriterion =
    scaffoldSmiles === ""
      ? { type: "scaffold", mode: "acyclic_only" }
      : { type: "scaffold", mode: "exact_match", scaffold_smiles: scaffoldSmiles };
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(criterion));
}

/**
 * Read and clear the stashed scaffold criterion. Returns null if nothing
 * was stashed or the payload is malformed. Always clears on read so the
 * pending query doesn't leak into subsequent /search visits.
 */
export function consumeScaffoldSearch(): ScaffoldCriterion | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  if (raw === null) return null;
  window.sessionStorage.removeItem(STORAGE_KEY);
  try {
    const parsed = JSON.parse(raw) as ScaffoldCriterion;
    if (
      parsed &&
      typeof parsed === "object" &&
      parsed.type === "scaffold" &&
      (parsed.mode === "exact_match" || parsed.mode === "acyclic_only")
    ) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}
```

- [ ] **Step 4: Run helper test — verify pass**

Run: `cd frontend && pnpm vitest run src/features/research-organization/lib/scaffold-search-handoff.test.ts`
Expected: PASS — all 5 cases.

- [ ] **Step 5: Write the scaffold-tree-node action test**

Append to `frontend/src/features/sar-analysis/components/scaffold-tree-node.test.tsx` (inside the existing describe):

```tsx
import { fireEvent } from "@testing-library/react";
import {
  consumeScaffoldSearch,
  STORAGE_KEY,
} from "@/features/research-organization/lib/scaffold-search-handoff";

// Add at top of file alongside existing vi.mock calls:
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// Inside the existing describe block:
describe("scaffold → search loop closer", () => {
  beforeEach(() => {
    mockPush.mockClear();
    window.sessionStorage.removeItem(STORAGE_KEY);
  });

  it("clicking the 'open in search' action stashes the scaffold and navigates", () => {
    // Use a minimal tree fixture (the existing tests already construct one
    // — reuse the same shape). The component renders an action button
    // visible on hover/focus; query by accessible name.
    render(
      <ScaffoldTreeNode
        scaffoldSmiles="c1ccncc1"
        tree={fixtureTreeWithPyridine}  // existing fixture or new minimal one
        childIndex={new Map()}
        colorBins={new Map()}
        depth={0}
        expanded={new Set()}
        selected={null}
        onToggle={vi.fn()}
        onSelect={vi.fn()}
      />,
    );
    const action = screen.getByRole("button", { name: /find compounds with this scaffold/i });
    fireEvent.click(action);
    expect(mockPush).toHaveBeenCalledWith("/search?from=scaffold-tree");
    expect(consumeScaffoldSearch()).toEqual({
      type: "scaffold",
      mode: "exact_match",
      scaffold_smiles: "c1ccncc1",
    });
  });
});
```

NOTE: read the existing test file for the actual fixture shape (`fixtureTreeWithPyridine` is illustrative — use whatever fixture the existing tests construct, or build a one-off fixture with `{ nodes: [{ scaffold_smiles: "c1ccncc1", molecule_count: 1, subtree_molecule_count: 1 }], ... }`).

- [ ] **Step 6: Run node test — verify it fails**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/scaffold-tree-node.test.tsx`
Expected: FAIL on the new case (no such button yet).

- [ ] **Step 7: Add the action icon to scaffold-tree-node.tsx**

In `frontend/src/features/sar-analysis/components/scaffold-tree-node.tsx`:

a) Add imports:

```tsx
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { stashScaffoldSearch } from "@/features/research-organization/lib/scaffold-search-handoff";
```

b) Inside `ScaffoldTreeNodeInner`, after the existing variable destructure (around line 52), add:

```tsx
const router = useRouter();

const handleOpenInSearch = (e: React.MouseEvent) => {
  e.stopPropagation();
  // Sentinel bucket has no concrete scaffold SMILES — stash empty string,
  // which the handoff helper translates to acyclic_only mode.
  const stashed = scaffoldSmiles === NO_SCAFFOLD_SENTINEL ? "" : scaffoldSmiles;
  stashScaffoldSearch(stashed);
  router.push("/search?from=scaffold-tree");
};
```

c) Replace the activity color band block (current lines 134–140) with a sibling group that includes the action button on the right. The color band moves to be the rightmost; the action sits just before it, visible only on hover/focus of the row. Apply the `group` Tailwind utility on the row container (current line 80 `<div data-testid=...>`):

Update the row container line:

```tsx
<div
  data-testid={`scaffold-node-${scaffoldSmiles}`}
  onClick={() => onSelect(scaffoldSmiles)}
  className={cn(
    "group flex items-center gap-2 rounded px-2 py-1 cursor-pointer hover:bg-muted",
    isSelected && "bg-muted",
  )}
  style={{ paddingLeft: `${8 + depth * 16}px` }}
>
```

And inside, REPLACE the current activity-color-band block with:

```tsx
{/* Action button — visible only on hover/focus; opens /search filtered
    to compounds matching this node's scaffold. */}
<button
  type="button"
  onClick={handleOpenInSearch}
  className="ml-auto opacity-0 group-hover:opacity-100 focus-visible:opacity-100 text-muted-foreground hover:text-foreground transition-opacity"
  aria-label="Find compounds with this scaffold"
  title="Find compounds with this scaffold"
>
  <Search size={14} />
</button>

{/* Activity color band — pinned to the right edge as a status glyph */}
{colorBin && (
  <span
    aria-label={`activity ${colorBin}`}
    className={cn("h-1.5 w-6 rounded shrink-0", BIN_COLORS[colorBin])}
  />
)}
```

NOTE: since both the action button and the color band now want the right edge, drop `ml-auto` from the band span — the button claims it instead, and the band sits to the right of the button (which lives inside the same flex row).

- [ ] **Step 8: Run node test — verify pass**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/scaffold-tree-node.test.tsx`
Expected: PASS — new case + all existing cases.

- [ ] **Step 9: Add the sessionStorage hydration effect in search-page.tsx**

In `frontend/src/features/research-organization/components/search-page.tsx`:

a) Add the import at the top:

```tsx
import { consumeScaffoldSearch } from "@/features/research-organization/lib/scaffold-search-handoff";
```

b) After the existing saved-search load effect (after the closing of the `useEffect` around line 430), add a sibling effect that runs ONCE on mount:

```tsx
// ── Scaffold-tree → /search handoff ────────────────────────────────────
// scaffold-tree-node.tsx stashes a pending scaffold criterion before
// navigating here. Consume + auto-execute. One-shot — the helper clears
// storage on read so we don't re-trigger on subsequent renders.
const scaffoldHandoffConsumedRef = useRef(false);
useEffect(() => {
  if (scaffoldHandoffConsumedRef.current) return;
  scaffoldHandoffConsumedRef.current = true;
  const criterion = consumeScaffoldSearch();
  if (!criterion) return;

  const query: SearchQuery = { logic: "and", criteria: [criterion] };
  dispatch({ type: "searchStart", query, protocolColumns: [] });

  const input = {
    query,
    aggregation: aggregationModeToWire(aggregationMode),
  };
  runSearch(
    { input, limit: SEARCH_PAGE_SIZE },
    {
      onSuccess: (data) => {
        dispatch({
          type: "searchComplete",
          results: enrichItems(data),
          nextCursor: data.next_cursor,
          totalCount: data.total_count,
        });
      },
      onError: (err) => {
        console.error("[Search] scaffold-handoff mutation failed:", err);
        dispatch({
          type: "searchComplete",
          results: [],
          nextCursor: null,
          totalCount: null,
        });
      },
    },
  );
  // Deliberately runs only once on mount — the handoff key is one-shot.
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

- [ ] **Step 10: Confirm typecheck + run search-page + node tests**

Run: `cd frontend && pnpm exec tsc --noEmit`
Run: `cd frontend && pnpm vitest run src/features/research-organization/ src/features/sar-analysis/components/scaffold-tree-node.test.tsx`
Expected: all green — no regressions.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/features/research-organization/lib/scaffold-search-handoff.ts \
        frontend/src/features/research-organization/lib/scaffold-search-handoff.test.ts \
        frontend/src/features/sar-analysis/components/scaffold-tree-node.tsx \
        frontend/src/features/sar-analysis/components/scaffold-tree-node.test.tsx \
        frontend/src/features/research-organization/components/search-page.tsx
git commit -m "$(cat <<'EOF'
feat(scaffold-tree): "open in search" action closes the loop to a filterable query (Wave 1 / B3)

Hover any tree node → small Search icon appears on the right → click →
lands on /search pre-filtered to that scaffold's exact_match (or
acyclic_only for the "no scaffold" bucket) and auto-executes.

Handoff via sessionStorage (key: cellar:pending-search-query) — one-shot,
cleared on read. Avoids inventing a /search ?q=<encoded-criterion> URL
scheme just for this affordance (defer until we have a broader use case
for bookmarkable ad-hoc queries).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6 — C1: Sonner toast for scaffold-tree async compute (3-second threshold + Cancel)

**Files:**
- Modify: `frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx`
- Modify: `frontend/src/features/sar-analysis/components/scaffold-tree-view.test.tsx`

**Behavior:**
- Track `isStarting || isPolling`. On enter → start a 3-second `setTimeout`.
- After 3s, fire `toast.loading("Computing scaffold tree…", { id: "scaffold-tree-job", duration: Infinity, action: { label: "Cancel", onClick } })`.
- When `tree` arrives OR `error` set → `toast.dismiss(id)` + clear any pending timeout.
- On Cancel click → call `cancelScaffoldTreeJobApiV1ScaffoldTreeJobsJobIdCancelPost(jobId)` (orval-generated); the polling hook picks up the `"cancelled"` status → sets `error`; the watching effect dismisses the toast and briefly shows `toast.success("Scaffold tree cancelled")`.
- Inline caption ("Computing scaffold tree…") stays as backstop.

- [ ] **Step 1: Add the failing toast tests**

Append to `frontend/src/features/sar-analysis/components/scaffold-tree-view.test.tsx` (inside the existing describe, with the existing setup utilities):

```tsx
import { vi, beforeEach, afterEach } from "vitest";
import { toast } from "sonner";

vi.mock("sonner", () => ({
  toast: {
    loading: vi.fn(),
    success: vi.fn(),
    dismiss: vi.fn(),
  },
}));

// Mock the orval-generated cancel call so we can assert it fires.
const mockCancel = vi.fn();
vi.mock("@/shared/lib/api/scaffold-tree/scaffold-tree", async () => {
  const actual = await vi.importActual<
    typeof import("@/shared/lib/api/scaffold-tree/scaffold-tree")
  >("@/shared/lib/api/scaffold-tree/scaffold-tree");
  return {
    ...actual,
    cancelScaffoldTreeJobApiV1ScaffoldTreeJobsJobIdCancelPost: (jobId: string) =>
      mockCancel(jobId),
  };
});

describe("ScaffoldTreeView async-toast wiring", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    (toast.loading as ReturnType<typeof vi.fn>).mockClear();
    (toast.success as ReturnType<typeof vi.fn>).mockClear();
    (toast.dismiss as ReturnType<typeof vi.fn>).mockClear();
    mockCancel.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows a loading toast after 3s of polling", () => {
    // Build the test render so useScaffoldTree returns
    // { isStarting: true, isPolling: false, tree: null, jobId: null, error: null }
    // — use the existing test override pattern (startFn / pollFn props on
    //   ScaffoldTreeView, OR vi.mock useScaffoldTree depending on what the
    //   existing test file uses). Mirror the existing pattern.
    renderScaffoldTreeViewWithMockedHook({
      isStarting: true,
      isPolling: false,
      tree: null,
      jobId: null,
      error: null,
    });
    expect(toast.loading).not.toHaveBeenCalled();
    vi.advanceTimersByTime(3000);
    expect(toast.loading).toHaveBeenCalledWith(
      "Computing scaffold tree…",
      expect.objectContaining({
        id: "scaffold-tree-job",
        duration: Infinity,
        action: expect.objectContaining({ label: "Cancel" }),
      }),
    );
  });

  it("does NOT show a toast if compute completes within 3s", () => {
    const { rerender } = renderScaffoldTreeViewWithMockedHook({
      isStarting: true,
      isPolling: false,
      tree: null,
      jobId: null,
      error: null,
    });
    vi.advanceTimersByTime(2000);
    rerender({
      isStarting: false,
      isPolling: false,
      tree: fixtureTree,  // non-null
      jobId: null,
      error: null,
    });
    vi.advanceTimersByTime(2000);
    expect(toast.loading).not.toHaveBeenCalled();
  });

  it("dismisses the toast when tree arrives", () => {
    const { rerender } = renderScaffoldTreeViewWithMockedHook({
      isStarting: true,
      isPolling: false,
      tree: null,
      jobId: null,
      error: null,
    });
    vi.advanceTimersByTime(3000);
    expect(toast.loading).toHaveBeenCalledTimes(1);
    rerender({
      isStarting: false,
      isPolling: false,
      tree: fixtureTree,
      jobId: null,
      error: null,
    });
    expect(toast.dismiss).toHaveBeenCalledWith("scaffold-tree-job");
  });

  it("Cancel action fires the cancel mutation and dismisses the toast", () => {
    renderScaffoldTreeViewWithMockedHook({
      isStarting: false,
      isPolling: true,
      tree: null,
      jobId: "job-123",
      error: null,
    });
    vi.advanceTimersByTime(3000);
    expect(toast.loading).toHaveBeenCalledTimes(1);

    // Pull the onClick out of the toast.loading call and fire it.
    const opts = (toast.loading as ReturnType<typeof vi.fn>).mock.calls[0][1];
    opts.action.onClick();

    expect(mockCancel).toHaveBeenCalledWith("job-123");
    expect(toast.dismiss).toHaveBeenCalledWith("scaffold-tree-job");
    expect(toast.success).toHaveBeenCalledWith("Scaffold tree cancelled");
  });
});
```

NOTE: `renderScaffoldTreeViewWithMockedHook` is the helper pattern — check the existing scaffold-tree-view.test.tsx file. If the existing tests mock `useScaffoldTree` via `vi.mock("../hooks/use-scaffold-tree", ...)`, use that pattern; if they pass `startFn`/`pollFn` overrides as props, use that. Both patterns exist in this codebase. Match what's already there. Same for `fixtureTree`.

- [ ] **Step 2: Run tests to verify failure**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/scaffold-tree-view.test.tsx`
Expected: FAIL on all 4 new cases — no toast fires.

- [ ] **Step 3: Implement the toast effect in scaffold-tree-view.tsx**

In `frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx`:

a) Add imports:

```tsx
import { useEffect } from "react";  // confirm already imported — extend if not
import { toast } from "sonner";
import { cancelScaffoldTreeJobApiV1ScaffoldTreeJobsJobIdCancelPost } from "@/shared/lib/api/scaffold-tree/scaffold-tree";
```

b) Inside the `ScaffoldTreeView` component body (around the existing destructure of `tree`, `isStarting`, `isPolling`, `error` from `useScaffoldTree`), add this effect:

```tsx
// Sonner toast for long-running async compute. After 3 seconds in a
// pending state, show a loading toast with a Cancel action. Dismiss on
// terminal status (tree arrives or error fires). The inline caption
// below stays as a backstop for screens where toasts may be off.
useEffect(() => {
  const TOAST_ID = "scaffold-tree-job";
  const isWorking = isStarting || (isPolling && !tree);
  if (!isWorking) {
    toast.dismiss(TOAST_ID);
    return;
  }
  const timer = window.setTimeout(() => {
    toast.loading("Computing scaffold tree…", {
      id: TOAST_ID,
      duration: Infinity,
      action: {
        label: "Cancel",
        onClick: () => {
          if (jobId) {
            void cancelScaffoldTreeJobApiV1ScaffoldTreeJobsJobIdCancelPost(jobId);
          }
          toast.dismiss(TOAST_ID);
          toast.success("Scaffold tree cancelled");
        },
      },
    });
  }, 3000);
  return () => {
    window.clearTimeout(timer);
  };
}, [isStarting, isPolling, tree, jobId]);
```

NOTE: `jobId` must be in the destructure off `useScaffoldTree` — confirm it's already pulled by the existing code; if only `tree`, `isStarting`, `isPolling`, `error` are destructured today, add `jobId` to that destructure.

- [ ] **Step 4: Run scaffold-tree-view tests — verify pass**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/components/scaffold-tree-view.test.tsx`
Expected: PASS — all 4 new cases + the existing cases.

- [ ] **Step 5: Run the sar-analysis test suite for regression**

Run: `cd frontend && pnpm vitest run src/features/sar-analysis/`
Expected: all green.

- [ ] **Step 6: Run typecheck**

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx \
        frontend/src/features/sar-analysis/components/scaffold-tree-view.test.tsx
git commit -m "$(cat <<'EOF'
feat(scaffold-tree): Sonner toast for async compute > 3 s, with Cancel (Wave 4 / C1)

Async path on > 500-mol collections now surfaces progress via a Sonner
loading toast 3 s after compute starts. Cancel action wires the existing
cancelScaffoldTreeJob mutation; on terminal status (tree arrives or
error) the toast dismisses cleanly.

Inline "Computing scaffold tree…" caption stays as a backstop for
screens where toasts may be off. Pattern mirrors the export-job-toast
shipped 2026-05-16.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification (after all 6 tasks)

- [ ] **Run the full FE test suite:**

```bash
cd frontend && pnpm vitest run
```
Expected: all green (research-organization + sar-analysis + the rest unchanged).

- [ ] **Run typecheck:**

```bash
cd frontend && pnpm exec tsc --noEmit
```
Expected: clean.

- [ ] **Run the affected BE tests:**

```bash
cd backend && uv run pytest tests/unit/test_search_query_composer.py tests/unit/test_search_query_composer_scaffold.py -v
```
Expected: all green.

- [ ] **Browser smoke (per the spec acceptance criteria):**

| # | Scenario | Expected |
|---|---|---|
| 1 | Set `is_frozen=true` on a test collection → open /collections/{id} | Add Molecules disabled with tooltip; selection toolbar's Remove disabled |
| 2 | Click collection name in CollectionHeader | Inline input appears; Enter saves; Escape reverts; whitespace-only is a no-op |
| 3 | /search → add Scaffold criterion → exact_match + paste a Bemis-Murcko SMILES → Search | Returns expected molecules |
| 4 | Same with `acyclic_only` mode | Returns the acyclic-compound bucket |
| 5 | Paste a full-molecule SMILES into exact_match | BE canonicalizes — matches against the scaffold (forgiving paste) |
| 6 | Open a collection with ringed compounds → scaffold-tree view → hover a node | Search-icon action appears on the right |
| 7 | Click the action | Lands on /search with the scaffold pre-filled + auto-executed; N rows ≈ node.molecule_count |
| 8 | Open scaffold-tree view on a > 500-mol collection → wait > 3s | Toast with spinner + Cancel appears |
| 9 | Click Cancel on the toast | Toast dismisses + brief "Scaffold tree cancelled" toast + caption clears |
| 10 | Small collection (< 500 mols) | No toast — sync return as before |

- [ ] **Push:**

```bash
git push origin prot-2
```

---

## Self-review

**Spec coverage check:**
- ✅ A1 — Task 1 (disable Add/Remove on frozen + tooltip; vitest test)
- ✅ A2 — Task 2 (inline-edit name; whitespace + unchanged + cancel cases tested; frozen stays editable since A1 only gates membership buttons)
- ✅ B1 — Task 3 (BE _scaffold_clause, two modes, canonicalization, 7 unit tests)
- ✅ B2 — Task 4 (FE type + factory + row + dispatch + dropdown entry; 5 row tests)
- ✅ B3 — Task 5 (handoff helper with stash/consume tests; scaffold-tree-node action test; search-page hydration effect)
- ✅ C1 — Task 6 (3s toast + Cancel + dismiss on terminal; 4 toast tests with fake timers)
- ✅ Acceptance criteria — all 10 spec smoke rows are mapped to the Final Verification section
- ✅ Deferred waves (2, 3, 5, 6) — explicitly out of scope; not mentioned in any task

**Placeholder scan:** none. Every step has either code, a command, or a discrete action.

**Type / signature consistency:**
- `ScaffoldCriterion` shape consistent across Task 3 (BE wire) + Task 4 (FE type) + Task 5 (helper module).
- `STORAGE_KEY` constant defined once in scaffold-search-handoff.ts, consumed by both producers.
- `useScaffoldTree` destructure consistent across the existing component + the new Task 6 effect (needs `jobId` — flagged as a confirm in the implementation step).

**Open dependency notes for implementers:**
- Task 3 (BE) is fully independent — can be tackled first or last.
- Task 4 (FE criterion) does NOT depend on Task 3 — the wire shape is documented in the spec, and the FE will fail-fast in browser if BE isn't shipped (clean error from compose_criteria).
- Task 5 (B3 loop closer) depends on Task 4 for the criterion type definition.
- Task 6 (C1 toast) is fully independent — touches only scaffold-tree-view + its test.
- Recommended order: 1 → 2 → 3 → 4 → 5 → 6 (spec order; minimizes intermediate broken-state windows).
