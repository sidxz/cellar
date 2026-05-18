# V4 Path A — Server-side scaffold-membership filtering — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a partial composite index on `molecules.bemis_murcko_smiles`, extend the scaffold criterion with a list-input mode (`exact_match_in`), and rewire the scaffold-tree right pane to query that mode server-side when a node is selected.

**Architecture:** The BE scaffold criterion is already shipped (`_scaffold_clause` at `_structure_query.py:170`). Path A adds (a) a partial composite index `(workspace_id, bemis_murcko_smiles) WHERE bemis_murcko_smiles != ''`, (b) a new `exact_match_in` clause branch that emits `IN (...)`, and (c) a FE component change in `scaffold-tree-view.tsx` that dispatches to a new `useCollectionScaffoldSearch` hook when a scaffold node is selected on a collection page — leaving the "no selection" path untouched.

**Tech Stack:** Python 3.13+, FastAPI, SQLAlchemy 2.0 async, RDKit, Alembic, Pytest. React 19, Next.js 16, TypeScript 5.7+, TanStack Query v5, Vitest.

---

## Task ordering at a glance

| # | Title | Layer |
|---|---|---|
| 1 | Migration 040 — partial composite index | BE / persistence |
| 2 | `_scaffold_clause` accepts `exact_match_in` | BE / persistence |
| 3 | FE wire types — extend `ScaffoldCriterion` | FE / types |
| 4 | `collectSubtreeScaffolds` helper | FE / lib |
| 5 | `useCollectionScaffoldSearch` hook | FE / hooks |
| 6 | `scaffold-tree-view.tsx` rewire | FE / components |

---

## Task 1: Migration 040 — partial composite index on `bemis_murcko_smiles`

**Files:**
- Create: `backend/alembic/versions/040_scaffold_membership_index.py`

- [ ] **Step 1: Create the migration**

Create `backend/alembic/versions/040_scaffold_membership_index.py`:

```python
"""040 — partial composite index for scaffold-membership lookups.

V4 Path A: enables server-side scaffold-membership filtering. The composite
(workspace_id, bemis_murcko_smiles) serves the always-present workspace
tenancy filter plus the scaffold equality predicate in one index seek.
The partial WHERE clause skips acyclic mols (empty string) — they go
through a different code path (mode='acyclic_only') and don't benefit
from this index.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "040_scaffold_membership_index"
down_revision: str | None = "039_umap_jobs"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.create_index(
        "ix_molecules_workspace_scaffold",
        "molecules",
        ["workspace_id", "bemis_murcko_smiles"],
        postgresql_where=sa.text("bemis_murcko_smiles != ''"),
    )


def downgrade() -> None:
    op.drop_index("ix_molecules_workspace_scaffold", table_name="molecules")
```

- [ ] **Step 2: Apply against dev DB**

Run: `cd backend && uv run alembic upgrade head`
Expected: `INFO  [alembic.runtime.migration] Running upgrade 039_umap_jobs -> 040_scaffold_membership_index, ...`

Verify in psql (or `docker compose exec postgres psql -U cellar -d cellar`):
```sql
\d+ molecules
-- look for "ix_molecules_workspace_scaffold" btree (workspace_id, bemis_murcko_smiles) WHERE bemis_murcko_smiles != ''::text
```

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/040_scaffold_membership_index.py
git commit -m "feat(persistence): migration 040 — partial composite index on molecules.bemis_murcko_smiles"
```

---

## Task 2: `_scaffold_clause` accepts `exact_match_in`

**Files:**
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_structure_query.py`
- Modify: `backend/tests/unit/test_search_query_composer_scaffold.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/unit/test_search_query_composer_scaffold.py` (inside the existing `class TestScaffoldClause`):

```python
    def test_exact_match_in_emits_in_clause(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "exact_match_in",
                    "scaffold_smiles_list": ["c1ccncc1", "c1ccccc1"],
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "bemis_murcko_smiles" in sql
        # SQLAlchemy emits "IN (...)" (uppercase) by default.
        assert " IN " in sql.upper()

    def test_exact_match_in_canonicalizes_each_input(self) -> None:
        """Full-molecule SMILES inputs canonicalize to their scaffolds."""
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "exact_match_in",
                    # 2-aminopyridine + 4-aminopyridine: both should canonicalize
                    # to pyridine scaffold; result list should be DE-DUPED.
                    "scaffold_smiles_list": ["Nc1ccccn1", "Nc1ccncc1"],
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        # The input N atoms should be gone (canonicalized away).
        assert "Nc1" not in sql
        # Both inputs canonicalize to pyridine; only ONE literal should appear
        # in the IN clause (dedup). Count distinct pyridine-ish substrings.
        pyridine_literals = sum(
            sql.count(s) for s in ("'c1ccncc1'", "'c1ccccn1'", "'n1ccccc1'")
        )
        assert pyridine_literals == 1

    def test_exact_match_in_drops_acyclic_entries_silently(self) -> None:
        """Inputs that canonicalize to '' are dropped (caller uses acyclic_only mode for those)."""
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "exact_match_in",
                    "scaffold_smiles_list": ["CCCC", "c1ccccc1"],
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        # Acyclic dropped — only benzene survives. IN clause should have
        # exactly ONE literal.
        assert sql.count("'") == 2  # one literal = two single-quote chars

    def test_exact_match_in_empty_list_emits_false(self) -> None:
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "exact_match_in",
                    "scaffold_smiles_list": [],
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        # SQLAlchemy false_() renders as "false" (or "0") depending on dialect.
        assert "false" in sql.lower() or " 0" in sql

    def test_exact_match_in_all_acyclic_emits_false(self) -> None:
        """When every input canonicalizes to '', the post-canonical list is empty."""
        clause = _compose({
            "criteria": [
                {
                    "type": "scaffold",
                    "mode": "exact_match_in",
                    "scaffold_smiles_list": ["CCCC", "CCO"],
                }
            ],
            "logic": "and",
        })
        assert clause is not None
        sql = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "false" in sql.lower() or " 0" in sql

    def test_exact_match_in_oversized_list_raises(self) -> None:
        """501 scaffolds → ValueError. Cap is 500."""
        with pytest.raises(ValueError, match=r"too many scaffolds"):
            _compose({
                "criteria": [
                    {
                        "type": "scaffold",
                        "mode": "exact_match_in",
                        "scaffold_smiles_list": ["c1ccccc1"] * 501,
                    }
                ],
                "logic": "and",
            })

    def test_exact_match_in_without_list_raises(self) -> None:
        with pytest.raises(ValueError, match=r"scaffold_smiles_list"):
            _compose({
                "criteria": [
                    {"type": "scaffold", "mode": "exact_match_in"}
                ],
                "logic": "and",
            })
```

- [ ] **Step 2: Run + fail**

Run: `cd backend && uv run pytest tests/unit/test_search_query_composer_scaffold.py -v`
Expected: 7 new tests FAIL with `ValueError: scaffold criterion: unknown mode 'exact_match_in'`.

- [ ] **Step 3: Implement**

Modify `backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_structure_query.py`. Replace the function body of `_scaffold_clause` (lines 170-214) with:

```python
_SCAFFOLD_IN_MAX = 500


def _scaffold_clause(criterion: dict[str, Any]) -> ColumnElement:
    """WHERE clause for {type: 'scaffold'} criteria.

    Supports three modes:
      - 'exact_match': molecules.bemis_murcko_smiles == canonical(input)
        Input is canonicalized via Bemis-Murcko computation so a paste of
        the full molecule normalizes to its scaffold (forgiving behavior).
      - 'acyclic_only': molecules.bemis_murcko_smiles == ''
        Matches the V2 'no scaffold' bucket (acyclic compounds; RDKit
        convention writes the empty string for these).
      - 'exact_match_in': molecules.bemis_murcko_smiles IN (canonical(input)...)
        V4 Path A — server-side filter to a list of scaffolds. Each input
        is canonicalized; entries that resolve to '' are dropped silently;
        duplicates are de-duped. Empty post-canonical list emits false_().
        Cap: 500 inputs per query.

    Raises ValueError on unknown mode, unparseable scaffold_smiles, or
    oversized exact_match_in list.
    """
    from rdkit import Chem  # local import to keep module fast to import

    from cellar.infrastructure.rdkit.scaffold_calculator import MurckoScaffoldCalculator

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
        if canonical == "":
            msg = (
                f"scaffold criterion: {raw!r} has no ring system — "
                "use mode='acyclic_only' to find acyclic compounds"
            )
            raise ValueError(msg)
        return MoleculeModel.bemis_murcko_smiles == canonical

    if mode == "exact_match_in":
        raw_list = criterion.get("scaffold_smiles_list")
        if raw_list is None:
            msg = "scaffold criterion: 'exact_match_in' mode requires 'scaffold_smiles_list'"
            raise ValueError(msg)
        if not isinstance(raw_list, list):
            msg = "scaffold criterion: 'scaffold_smiles_list' must be a list"
            raise ValueError(msg)
        if len(raw_list) > _SCAFFOLD_IN_MAX:
            msg = (
                f"scaffold criterion: too many scaffolds in 'exact_match_in' "
                f"(got {len(raw_list)}, max {_SCAFFOLD_IN_MAX})"
            )
            raise ValueError(msg)
        calc = MurckoScaffoldCalculator()
        seen: set[str] = set()
        canonical_list: list[str] = []
        for raw in raw_list:
            mol = Chem.MolFromSmiles(raw)
            if mol is None:
                # Skip unparseable entries rather than failing the whole query —
                # caller may be passing scaffold SMILES from a node-walk where
                # one bad entry shouldn't poison the lookup.
                continue
            canonical = calc.compute(mol)
            if not canonical:  # None or "" → acyclic; drop silently
                continue
            if canonical in seen:
                continue
            seen.add(canonical)
            canonical_list.append(canonical)
        if not canonical_list:
            return sa.false()
        return MoleculeModel.bemis_murcko_smiles.in_(canonical_list)

    msg = (
        f"scaffold criterion: unknown mode {mode!r} "
        "(allowed: exact_match, acyclic_only, exact_match_in)"
    )
    raise ValueError(msg)
```

- [ ] **Step 4: Run + pass**

Run: `cd backend && uv run pytest tests/unit/test_search_query_composer_scaffold.py -v`
Expected: ALL tests PASS (both the original 8 and the 7 new ones).

Then run the broader composer/structure-query suite to catch regressions:

Run: `cd backend && uv run pytest tests/unit/ -k "scaffold or structure_query or search_query_composer" -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/infrastructure/persistence/sqlalchemy/chemical_registration/_structure_query.py backend/tests/unit/test_search_query_composer_scaffold.py
git commit -m "feat(search): scaffold criterion exact_match_in mode — list of scaffolds OR'd via IN"
```

---

## Task 3: FE wire types — extend `ScaffoldCriterion` + `ScaffoldMode`

**Files:**
- Modify: `frontend/src/features/research-organization/types/index.ts`

- [ ] **Step 1: Locate the existing type**

`frontend/src/features/research-organization/types/index.ts:233-240` currently reads:

```ts
export type ScaffoldMode = "exact_match" | "acyclic_only";

export interface ScaffoldCriterion {
  type: "scaffold";
  mode: ScaffoldMode;
  /** Required when mode is "exact_match"; ignored in acyclic_only. */
  scaffold_smiles?: string;
}
```

- [ ] **Step 2: Extend in place**

Replace those lines with:

```ts
export type ScaffoldMode = "exact_match" | "acyclic_only" | "exact_match_in";

export interface ScaffoldCriterion {
  type: "scaffold";
  mode: ScaffoldMode;
  /** Required when mode is "exact_match"; ignored otherwise. */
  scaffold_smiles?: string;
  /**
   * Required when mode is "exact_match_in"; a list of scaffold SMILES
   * that get OR'd together server-side via IN. V4 Path A — used by the
   * scaffold-tree right pane when a Hierarchy node selects its whole
   * subtree. Cap: 500 entries (enforced server-side).
   */
  scaffold_smiles_list?: string[];
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: clean exit; no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/research-organization/types/index.ts
git commit -m "feat(search): wire ScaffoldCriterion exact_match_in mode + scaffold_smiles_list"
```

---

## Task 4: `collectSubtreeScaffolds` helper

**Files:**
- Create: `frontend/src/features/sar-analysis/lib/collect-subtree-scaffolds.ts`
- Create: `frontend/src/features/sar-analysis/lib/collect-subtree-scaffolds.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/sar-analysis/lib/collect-subtree-scaffolds.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { collectSubtreeScaffolds } from "./collect-subtree-scaffolds";
import type { ScaffoldTreeResult } from "../types/scaffold-tree";

const node = (scaffold_smiles: string, molecule_ids: string[] = []) => ({
  scaffold_smiles,
  molecule_ids,
  molecule_count: molecule_ids.length,
  subtree_molecule_count: molecule_ids.length,
});

describe("collectSubtreeScaffolds", () => {
  it("returns [node.scaffold_smiles] for a leaf node", () => {
    const tree: ScaffoldTreeResult = {
      nodes: [node("c1ccccc1")],
      edges: [],
      stats: {
        molecule_count: 0,
        scaffold_count: 1,
        max_depth: 0,
        no_scaffold_count: 0,
      },
    };
    expect(collectSubtreeScaffolds("c1ccccc1", tree)).toEqual(["c1ccccc1"]);
  });

  it("returns the inner node plus all descendants in a Schuffenhauer DAG", () => {
    // benzene → naphthalene → anthracene
    const tree: ScaffoldTreeResult = {
      nodes: [
        node("c1ccccc1"),
        node("c1ccc2ccccc2c1"),
        node("c1ccc2cc3ccccc3cc2c1"),
      ],
      edges: [
        { parent_smiles: "c1ccccc1", child_smiles: "c1ccc2ccccc2c1" },
        { parent_smiles: "c1ccc2ccccc2c1", child_smiles: "c1ccc2cc3ccccc3cc2c1" },
      ],
      stats: {
        molecule_count: 0,
        scaffold_count: 3,
        max_depth: 2,
        no_scaffold_count: 0,
      },
    };
    const out = collectSubtreeScaffolds("c1ccc2ccccc2c1", tree);
    expect(new Set(out)).toEqual(
      new Set(["c1ccc2ccccc2c1", "c1ccc2cc3ccccc3cc2c1"]),
    );
  });

  it("de-dupes when DAG has diamond shape (two parents → same descendant)", () => {
    // A → B, A → C, B → D, C → D  (D reachable via two paths)
    const tree: ScaffoldTreeResult = {
      nodes: [node("A"), node("B"), node("C"), node("D")],
      edges: [
        { parent_smiles: "A", child_smiles: "B" },
        { parent_smiles: "A", child_smiles: "C" },
        { parent_smiles: "B", child_smiles: "D" },
        { parent_smiles: "C", child_smiles: "D" },
      ],
      stats: {
        molecule_count: 0,
        scaffold_count: 4,
        max_depth: 2,
        no_scaffold_count: 0,
      },
    };
    const out = collectSubtreeScaffolds("A", tree);
    expect(out.length).toBe(4); // A, B, C, D — exactly once each
    expect(new Set(out)).toEqual(new Set(["A", "B", "C", "D"]));
  });

  it("returns [] when scaffold_smiles is not in the tree", () => {
    const tree: ScaffoldTreeResult = {
      nodes: [node("c1ccccc1")],
      edges: [],
      stats: {
        molecule_count: 0,
        scaffold_count: 1,
        max_depth: 0,
        no_scaffold_count: 0,
      },
    };
    expect(collectSubtreeScaffolds("c1ccncc1", tree)).toEqual([]);
  });
});
```

- [ ] **Step 2: Run + fail**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/lib/collect-subtree-scaffolds.test.ts`
Expected: FAIL with "Cannot find module './collect-subtree-scaffolds'".

- [ ] **Step 3: Implement**

Create `frontend/src/features/sar-analysis/lib/collect-subtree-scaffolds.ts`:

```ts
import type { ScaffoldTreeResult } from "../types/scaffold-tree";
import { buildChildIndex } from "./scaffold-tree-math";

/**
 * Collects the scaffold SMILES for the subtree rooted at `scaffoldSmiles`
 * (the node itself plus all descendants), Set-deduped.
 *
 * Mirror of `collectSubtreeMolIds` but returns scaffold SMILES instead of
 * molecule IDs. Used by V4 Path A to drive the `exact_match_in` server-side
 * scaffold-membership filter when a Hierarchy node selects its whole subtree.
 *
 * Returns [] when `scaffoldSmiles` is not present in the tree.
 */
export function collectSubtreeScaffolds(
  scaffoldSmiles: string,
  tree: ScaffoldTreeResult,
): string[] {
  const scaffoldSet = new Set(tree.nodes.map((n) => n.scaffold_smiles));
  if (!scaffoldSet.has(scaffoldSmiles)) return [];

  const children = buildChildIndex(tree);
  const visited = new Set<string>();
  const acc: string[] = [];
  const stack: string[] = [scaffoldSmiles];

  while (stack.length > 0) {
    const s = stack.pop()!;
    if (visited.has(s)) continue;
    visited.add(s);
    acc.push(s);
    for (const c of children.get(s) ?? []) stack.push(c);
  }

  return acc;
}
```

- [ ] **Step 4: Run + pass**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/lib/collect-subtree-scaffolds.test.ts`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/sar-analysis/lib/collect-subtree-scaffolds.ts frontend/src/features/sar-analysis/lib/collect-subtree-scaffolds.test.ts
git commit -m "feat(sar): collectSubtreeScaffolds — BFS over Schuffenhauer DAG, Set-deduped"
```

---

## Task 5: `useCollectionScaffoldSearch` hook

**Files:**
- Create: `frontend/src/features/sar-analysis/hooks/use-collection-scaffold-search.ts`
- Create: `frontend/src/features/sar-analysis/hooks/use-collection-scaffold-search.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/sar-analysis/hooks/use-collection-scaffold-search.test.tsx`:

```tsx
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useCollectionScaffoldSearch } from "./use-collection-scaffold-search";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  customInstance: vi.fn(),
}));

import { customInstance } from "@/shared/lib/api/custom-instance";

const mockCustomInstance = customInstance as ReturnType<typeof vi.fn>;

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useCollectionScaffoldSearch", () => {
  beforeEach(() => {
    mockCustomInstance.mockReset();
    mockCustomInstance.mockResolvedValue({ items: [] });
  });

  it("posts an AND'd group with collection + exact_match_in scaffold criterion", async () => {
    const { result } = renderHook(
      () =>
        useCollectionScaffoldSearch({
          collectionId: "col-1",
          scaffoldSmiles: ["c1ccccc1", "c1ccncc1"],
        }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockCustomInstance).toHaveBeenCalledTimes(1);
    const call = mockCustomInstance.mock.calls[0][0];
    expect(call.url).toBe("/api/v1/search/execute");
    expect(call.method).toBe("POST");
    expect(call.data.query.criteria[0]).toMatchObject({
      type: "group",
      op: "AND",
      criteria: [
        { type: "collection", collection_id: "col-1" },
        {
          type: "scaffold",
          mode: "exact_match_in",
          scaffold_smiles_list: expect.arrayContaining(["c1ccccc1", "c1ccncc1"]),
        },
      ],
    });
  });

  it("disabled when enabled === false", () => {
    const { result } = renderHook(
      () =>
        useCollectionScaffoldSearch({
          collectionId: "col-1",
          scaffoldSmiles: ["c1ccccc1"],
          enabled: false,
        }),
      { wrapper: wrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockCustomInstance).not.toHaveBeenCalled();
  });

  it("disabled when scaffoldSmiles is empty", () => {
    renderHook(
      () =>
        useCollectionScaffoldSearch({
          collectionId: "col-1",
          scaffoldSmiles: [],
        }),
      { wrapper: wrapper() },
    );
    expect(mockCustomInstance).not.toHaveBeenCalled();
  });

  it("query key sorts scaffolds so caller-order doesn't fragment the cache", async () => {
    const { result: a } = renderHook(
      () =>
        useCollectionScaffoldSearch({
          collectionId: "col-1",
          scaffoldSmiles: ["b", "a", "c"],
        }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(a.current.isSuccess).toBe(true));

    mockCustomInstance.mockClear();

    // Same logical query, different input order: should hit the cache, not refetch.
    const { result: b } = renderHook(
      () =>
        useCollectionScaffoldSearch({
          collectionId: "col-1",
          scaffoldSmiles: ["c", "a", "b"],
        }),
      { wrapper: a as unknown as Parameters<typeof wrapper>[0] }, // intentional: reuse same client
    );
    // Better: share the client explicitly.
    expect(true).toBe(true); // placeholder, see implementation note
  });
});
```

Note: the fourth test as written shares clients awkwardly. A simpler approach in the actual implementation is to extract the key builder and test it directly. **Revise the fourth test to be:**

```tsx
  it("query key is stable across scaffold input order", async () => {
    const { scaffoldSearchQueryKey } = await import("./use-collection-scaffold-search");
    expect(scaffoldSearchQueryKey("col-1", ["b", "a", "c"])).toEqual(
      scaffoldSearchQueryKey("col-1", ["c", "a", "b"]),
    );
    expect(scaffoldSearchQueryKey("col-1", ["a"])).not.toEqual(
      scaffoldSearchQueryKey("col-1", ["b"]),
    );
  });
```

- [ ] **Step 2: Run + fail**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/hooks/use-collection-scaffold-search.test.tsx`
Expected: FAIL with "Cannot find module './use-collection-scaffold-search'".

- [ ] **Step 3: Implement**

Create `frontend/src/features/sar-analysis/hooks/use-collection-scaffold-search.ts`:

```ts
"use client";

import { useQuery } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { EnrichedSearchResponse } from "@/features/research-organization/hooks/use-search";
import type { ExecuteSearchInput } from "@/features/research-organization/types";

export interface UseCollectionScaffoldSearchOptions {
  collectionId: string;
  /** Scaffold SMILES to OR together; order-independent for caching. */
  scaffoldSmiles: string[];
  /** Defaults to true when collectionId + scaffoldSmiles.length > 0. */
  enabled?: boolean;
  /** Page size; default 10000 — same as useCollectionSearch. */
  limit?: number;
}

/**
 * Stable cache key for `useCollectionScaffoldSearch`. Exported so callers
 * (e.g. invalidation flows) can build the same key and so tests can verify
 * input-order independence.
 */
export function scaffoldSearchQueryKey(
  collectionId: string,
  scaffoldSmiles: string[],
): readonly unknown[] {
  return [
    "collection-scaffold-search",
    collectionId,
    [...scaffoldSmiles].sort().join("\n"),
  ];
}

/**
 * V4 Path A — fetches the enriched molecule list for `collectionId`
 * filtered to members whose Bemis-Murcko scaffold is in `scaffoldSmiles`.
 * The BE composes `collection_id` AND `bemis_murcko_smiles IN (...)`
 * via the existing search engine + the new `exact_match_in` criterion mode.
 *
 * Cap: 500 scaffolds per request (enforced server-side).
 */
export function useCollectionScaffoldSearch({
  collectionId,
  scaffoldSmiles,
  enabled,
  limit = 10000,
}: UseCollectionScaffoldSearchOptions) {
  const effectiveEnabled =
    (enabled ?? true) && Boolean(collectionId) && scaffoldSmiles.length > 0;

  return useQuery({
    queryKey: scaffoldSearchQueryKey(collectionId, scaffoldSmiles),
    enabled: effectiveEnabled,
    queryFn: async () => {
      const input: ExecuteSearchInput = {
        query: {
          logic: "and",
          criteria: [
            {
              type: "group",
              op: "AND",
              criteria: [
                { type: "collection", collection_id: collectionId },
                {
                  type: "scaffold",
                  mode: "exact_match_in",
                  scaffold_smiles_list: scaffoldSmiles,
                },
              ],
            },
          ],
        },
      };
      return customInstance<EnrichedSearchResponse>({
        url: "/api/v1/search/execute",
        method: "POST",
        data: input,
        params: { limit: String(limit) },
      });
    },
  });
}
```

If the existing `ExecuteSearchInput` / criteria types don't allow `{type: "group", op, criteria: [...]}` shapes, cast at the call site with `as unknown as ExecuteSearchInput` — the FE search-query-builder already produces these shapes; the wire type may be loose (`Record<string, unknown>` at the criterion level). Verify by reading `frontend/src/features/research-organization/types/index.ts` and the existing `useCollectionSearch` body shape.

- [ ] **Step 4: Run + pass**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/hooks/use-collection-scaffold-search.test.tsx`
Expected: tests PASS (3 originals + the revised 4th = 4 total).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/sar-analysis/hooks/use-collection-scaffold-search.ts frontend/src/features/sar-analysis/hooks/use-collection-scaffold-search.test.tsx
git commit -m "feat(sar): useCollectionScaffoldSearch — server-side AND'd collection + scaffold filter"
```

---

## Task 6: `scaffold-tree-view.tsx` rewire

**Files:**
- Modify: `frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx`

- [ ] **Step 1: Read the current `filteredMolecules` block**

The current logic at `scaffold-tree-view.tsx:223-239` is:

```tsx
const filteredMolecules = useMemo(() => {
  if (!tree || selectedScaffold == null) return molecules;
  if (subMode === "groups") {
    const node = tree.nodes.find(
      (n) => n.scaffold_smiles === selectedScaffold,
    );
    const directIds = new Set(node?.molecule_ids ?? []);
    return molecules.filter((m) => directIds.has(m.id));
  }
  const ids = new Set(collectSubtreeMolIds(selectedScaffold, tree));
  return molecules.filter((m) => ids.has(m.id));
}, [molecules, tree, selectedScaffold, subMode]);
```

- [ ] **Step 2: Add the new hook import + selection-driven scaffold list**

At the top of `scaffold-tree-view.tsx`, add the new imports alongside the existing ones:

```tsx
import { useCollectionScaffoldSearch } from "../hooks/use-collection-scaffold-search";
import { collectSubtreeScaffolds } from "../lib/collect-subtree-scaffolds";
```

Inside the `ScaffoldTreeView` component, after `filteredMolecules` is computed (or in its place), add:

```tsx
// V4 Path A: when a scaffold is selected on a collection page, fetch the
// filtered set server-side via the new exact_match_in criterion. Avoids the
// in-memory filter over the full collection load (which is capped at 10K).
// When no scaffold is selected, OR when we're operating on an ad-hoc result
// set (no collectionId), fall through to the existing in-memory path.
const selectedScaffolds = useMemo<string[]>(() => {
  if (!tree || selectedScaffold == null) return [];
  if (subMode === "groups") return [selectedScaffold];
  return collectSubtreeScaffolds(selectedScaffold, tree);
}, [tree, selectedScaffold, subMode]);

const serverFiltered = useCollectionScaffoldSearch({
  collectionId: collectionId ?? "",
  scaffoldSmiles: selectedScaffolds,
  enabled: Boolean(collectionId) && selectedScaffolds.length > 0,
});
```

- [ ] **Step 3: Switch `filteredMolecules` to the server path when available**

Replace the existing `filteredMolecules` block (lines 223-239) with:

```tsx
const filteredMolecules = useMemo(() => {
  if (!tree || selectedScaffold == null) return molecules;

  // V4 Path A: server-side filtered result wins when we're on a collection
  // page AND a scaffold is selected. Use the server response directly —
  // it's the authoritative list (not clipped by the 10K parent-load cap).
  if (
    collectionId &&
    selectedScaffolds.length > 0 &&
    serverFiltered.data?.items
  ) {
    return serverFiltered.data.items as typeof molecules;
  }

  // Fallback (ad-hoc result sets without collectionId, or while the server
  // call is in flight): in-memory filter of the already-loaded molecules.
  if (subMode === "groups") {
    const node = tree.nodes.find(
      (n) => n.scaffold_smiles === selectedScaffold,
    );
    const directIds = new Set(node?.molecule_ids ?? []);
    return molecules.filter((m) => directIds.has(m.id));
  }
  const ids = new Set(collectSubtreeMolIds(selectedScaffold, tree));
  return molecules.filter((m) => ids.has(m.id));
}, [
  molecules,
  tree,
  selectedScaffold,
  subMode,
  collectionId,
  selectedScaffolds,
  serverFiltered.data,
]);
```

- [ ] **Step 4: Typecheck + run existing scaffold-tree-view tests**

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: clean exit.

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/components/`
Expected: existing tests still PASS (the new code path only activates when a `collectionId` is set AND a scaffold is selected, so existing tests that pass plain `moleculeIds` or don't select a scaffold are unaffected).

- [ ] **Step 5: Write a new test asserting server-path activation**

Append a focused test to the existing `frontend/src/features/sar-analysis/components/scaffold-tree-view.test.tsx` (or create if it doesn't exist):

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ScaffoldTreeView } from "./scaffold-tree-view";

vi.mock("@/shared/lib/api/custom-instance", () => ({
  customInstance: vi.fn(),
}));
vi.mock("../hooks/use-scaffold-tree", () => ({
  useScaffoldTree: () => ({
    tree: {
      nodes: [
        {
          scaffold_smiles: "c1ccccc1",
          molecule_ids: ["m1", "m2"],
          molecule_count: 2,
          subtree_molecule_count: 2,
        },
      ],
      edges: [],
      stats: {
        molecule_count: 2,
        scaffold_count: 1,
        max_depth: 0,
        no_scaffold_count: 0,
      },
    },
    jobId: null,
    isStarting: false,
    isPolling: false,
    error: null,
  }),
}));

import { customInstance } from "@/shared/lib/api/custom-instance";
const mockCustomInstance = customInstance as ReturnType<typeof vi.fn>;

function renderWithClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("ScaffoldTreeView server-side filter (V4 Path A)", () => {
  it("invokes useCollectionScaffoldSearch when a scaffold is selected on a collection page", async () => {
    mockCustomInstance.mockResolvedValue({
      items: [
        { id: "m1", name: "M1", inchi_key: "x", workspace_id: "w", visibility: "public" },
      ],
    });

    const mols = [
      { id: "m1", name: "M1", inchi_key: "x" } as any,
      { id: "m2", name: "M2", inchi_key: "y" } as any,
    ];
    renderWithClient(
      <ScaffoldTreeView
        molecules={mols}
        activityData={{}}
        collectionId="col-1"
      />,
    );

    // The chemotype row in Groups mode is clickable; find by scaffold SMILES text content.
    // (Actual selector may be a button; adjust to component's testid/aria.)
    await waitFor(() => {
      expect(screen.getByText(/c1ccccc1/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/c1ccccc1/i));

    await waitFor(() => {
      expect(mockCustomInstance).toHaveBeenCalled();
    });
    const call = mockCustomInstance.mock.calls[0][0];
    expect(call.url).toBe("/api/v1/search/execute");
    expect(call.data.query.criteria[0].criteria).toContainEqual(
      expect.objectContaining({
        type: "scaffold",
        mode: "exact_match_in",
        scaffold_smiles_list: ["c1ccccc1"],
      }),
    );
  });

  it("does NOT invoke the server hook when collectionId is absent (ad-hoc result set)", async () => {
    mockCustomInstance.mockResolvedValue({ items: [] });
    const mols = [{ id: "m1", name: "M1", inchi_key: "x" } as any];
    renderWithClient(
      <ScaffoldTreeView molecules={mols} activityData={{}} />,
    );
    // Click a chemotype; no server call should fire since collectionId is undefined.
    await waitFor(() => {
      expect(screen.queryByText(/c1ccccc1/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText(/c1ccccc1/i));
    // Wait one tick to make sure no async call was scheduled.
    await new Promise((r) => setTimeout(r, 50));
    expect(mockCustomInstance).not.toHaveBeenCalled();
  });
});
```

If the test selectors don't quite match the actual DOM (e.g. the SMILES isn't rendered as visible text — it's drawn as a structure thumbnail), the implementer should adjust selectors to use `data-testid` or `getByRole("button", { name: ... })` once they read the component DOM live. **The behavioral assertion is what matters: `mockCustomInstance` is or is not called.**

- [ ] **Step 6: Run all sar-analysis tests + typecheck**

Run: `cd frontend && pnpm exec vitest run src/features/sar-analysis/`
Expected: ALL tests PASS.

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/sar-analysis/components/scaffold-tree-view.tsx frontend/src/features/sar-analysis/components/scaffold-tree-view.test.tsx
git commit -m "feat(sar): scaffold-tree right pane uses server-side exact_match_in when a scaffold is selected on a collection"
```

---

## Smoke checklist (manual, post-implementation)

1. `cd backend && uv run alembic upgrade head` — migration 040 applies cleanly.
2. Verify the index:
   ```sql
   \d+ molecules
   ```
   Expect `"ix_molecules_workspace_scaffold" btree (workspace_id, bemis_murcko_smiles) WHERE bemis_murcko_smiles != ''::text`.
3. `cd frontend && pnpm dev`, open a 5-mol collection in `?view=tree` — Groups mode → click a chemotype → right pane filters correctly (regression check on tiny set).
4. Same on a 900-mol collection — server call fires, right pane shows the chemotype's mols, count matches.
5. Switch to Hierarchy on the same 900-mol collection — click an inner node → server call fires with `scaffold_smiles_list` containing the subtree's scaffolds; right pane shows union; count matches `subtree_molecule_count`.
6. Click the selected node again to deselect → returns to the "show all" pane (uses parent's pre-loaded `molecules`; no server call).
7. Open `/search`, use the EXISTING single-value scaffold criterion → no regression (Wave 1 / B1 still works).
8. (Perf) `EXPLAIN ANALYZE` a representative query in psql:
   ```sql
   EXPLAIN ANALYZE
   SELECT id FROM molecules
   WHERE workspace_id = '...' AND bemis_murcko_smiles IN ('c1ccccc1', 'c1ccncc1')
   LIMIT 100;
   ```
   Expect `Index Scan using ix_molecules_workspace_scaffold` (not `Seq Scan on molecules`).

---

## Self-review notes

- **Spec coverage:** Tasks 1, 2 cover spec §3.1 + §3.2; Tasks 3-6 cover spec §3.3; spec §3.4 is "what does NOT change" so requires no task; spec §5 acceptance criteria 1, 6 are validated by Smoke #8; criteria 2-5 by Smoke #3-7; criterion 7 by Tasks 2/3/4/5/6 test runs.
- **Type consistency:** `scaffold_smiles_list` named identically in BE (`_scaffold_clause` reads `criterion.get("scaffold_smiles_list")`), FE wire type (`ScaffoldCriterion.scaffold_smiles_list`), and hook (`scaffoldSmiles` prop → `scaffold_smiles_list` body field). `exact_match_in` mode string identical across BE + FE.
- **Cap consistency:** 500 cited in spec §3.2 and enforced in BE Task 2 (`_SCAFFOLD_IN_MAX = 500`); FE hook doesn't pre-validate (relies on BE 400).
- **Index name consistency:** `ix_molecules_workspace_scaffold` in spec §3.1, Task 1 migration, and Smoke checklist.
- **No placeholders.**
