# Tagging — Phase 5: Frontend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Apply the **frontend-design** principles (meticulous, polished, no generic AI-slop) WITHIN Cellar's existing design system — reuse shadcn/Badge, IBM Plex, OkLCh tokens, the compact scientific feel. Do NOT introduce a clashing aesthetic.

**Goal:** Surface tags in the UI: view/edit tags on entity detail pages, filter dashboards + the advanced search by tag, and manage tags (rename/merge/delete) on an admin page — all consuming the Phase 1–4 backend.

**Architecture:** A pure, shared `TagChip` (boxed `key=value`, **colored by a hash of the key** via the existing 8-color palette hoisted to `shared/lib`). A `features/tagging/` feature owns the hooks (hand-rolled `customInstance` + TanStack Query, mirroring `use-collections`/`createCrudHooks`) and the composed components: an AWS-style **separate Key+Value** `TagEditor`, a `TagFilter` for list dashboards, a `TagSection` for advanced search, and a `TagList` admin page mirroring the controlled-vocabulary admin. Tags are NOT in the orval-generated client yet (regen needs a live backend) — hooks are hand-written now; an `orval` regen is deferred to deploy.

**Tech Stack:** Next.js 16 / React 19 / TypeScript / shadcn/ui / Tailwind v4 / TanStack Query v5 / cmdk (Command) / Radix Popover / vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-06-02-tagging-design.md` §9 (frontend). Honors the standing UX feedback: explicit per-tag commit (no autosave), key/value + autocomplete (never UUID inputs), proper form controls (no JSON UI), density-aware "+N more" overflow.

**Branch:** `kvt`.

**Design decisions (confirmed with the user):** boxed `key=value` chips tinted by key-hash; **separate Key + Value** editor fields with autocomplete; molecules filter via the advanced-search Tag section only (no compounds-grid quick filter, no backend change).

---

## File Structure

### New — shared
| Path | Responsibility |
|------|----------------|
| `src/shared/lib/category-colors.ts` | Hoisted 8-color palette + `resolveCategoryColor(label, hex?)` (moved from screening-assay). |
| `src/shared/components/tag-chip.tsx` | Pure display chip: `key=value`, key-hued, optional remove button. |

### New — `src/features/tagging/`
| Path | Responsibility |
|------|----------------|
| `types.ts` | `Tag`, `TagInput`, `TaggableEntity` types. |
| `hooks/use-entity-tags.ts` | `useEntityTags` / `useAssignTag` / `useUnassignTag` / `useSetEntityTags` (nested `/{entity}/{id}/tags`). |
| `hooks/use-tags.ts` | `useTags` (search/list), `useRenameTag`, `useDeleteTag`, `useMergeTags` (via `createCrudHooks` + `useAction`). |
| `components/tag-editor.tsx` | Separate Key+Value autocomplete + Add; current tags as removable chips. |
| `components/tag-autocomplete.tsx` | Reusable Command/Popover combobox over `useTags(q)` (free-entry allowed). |
| `components/tag-filter.tsx` | Popover multi-select + any/all toggle; selected tags as chips. |
| `components/tag-section.tsx` | Advanced-search section (mirrors `collection-section`) → `tag` criterion. |
| `components/tag-list.tsx` | Admin management table (rename/merge/delete). |
| `components/tag-rename-dialog.tsx`, `components/tag-merge-dialog.tsx` | Admin dialogs. |

### Modified
| Path | Change |
|------|--------|
| `src/features/screening-assay/lib/pick-list-colors.ts` | Re-export palette/resolver from `shared/lib/category-colors` (back-compat; no call-site churn). |
| `src/features/research-organization/types/index.ts` | Add `TagCriterion` + `"tag"` to `CriterionType`/union. |
| `src/features/research-organization/components/search/search-form.tsx` | Decompose/compose a `TagSection`. |
| Collection + molecule detail headers | Render `TagEditor`. |
| Project/collection/protocol list toolbars | Add `TagFilter`. |
| `src/shared/lib/navigation.ts` | Add `/admin/tags` nav item. |
| `src/app/(dashboard)/admin/tags/page.tsx` | New route → `<TagList />`. |

---

## Task F5-1: Foundation (colors, types, hooks)

**Files:**
- Create: `src/shared/lib/category-colors.ts`
- Modify: `src/features/screening-assay/lib/pick-list-colors.ts`
- Create: `src/features/tagging/types.ts`
- Create: `src/features/tagging/hooks/use-entity-tags.ts`
- Create: `src/features/tagging/hooks/use-tags.ts`
- Test: `src/shared/lib/category-colors.test.ts`

- [ ] **Step 1: Hoist the palette to shared**

Create `src/shared/lib/category-colors.ts` by MOVING the entire current contents of `src/features/screening-assay/lib/pick-list-colors.ts` into it, renaming the public resolver to a generic name (keep the palette + hash identical):
- Rename `PickListColor` → `CategoryColor`, `PICK_LIST_COLORS` → `CATEGORY_COLORS`, `resolvePickListColor` → `resolveCategoryColor` (same signature `(label: string, color?: string | null) => CategoryColor`). Keep the djb2 `hashLabel` + `HEX_TO_COLOR` logic byte-for-byte.

Then REPLACE `src/features/screening-assay/lib/pick-list-colors.ts` with a back-compat re-export so existing screening-assay imports keep working unchanged:

```typescript
/** @deprecated palette hoisted to shared/lib/category-colors. Re-exported for back-compat. */
export {
  CATEGORY_COLORS as PICK_LIST_COLORS,
  resolveCategoryColor as resolvePickListColor,
  type CategoryColor as PickListColor,
} from "@/shared/lib/category-colors";
```

- [ ] **Step 2: Write the failing color test**

Create `src/shared/lib/category-colors.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { resolveCategoryColor, CATEGORY_COLORS } from "./category-colors";

describe("resolveCategoryColor", () => {
  it("is stable for the same label", () => {
    expect(resolveCategoryColor("project").hex).toBe(resolveCategoryColor("project").hex);
  });
  it("returns a palette member", () => {
    const c = resolveCategoryColor("assay");
    expect(CATEGORY_COLORS.some((p) => p.hex === c.hex)).toBe(true);
  });
  it("different keys can map to different colors", () => {
    const keys = ["project", "assay", "series", "target", "favorite", "status"];
    const hexes = new Set(keys.map((k) => resolveCategoryColor(k).hex));
    expect(hexes.size).toBeGreaterThan(1);
  });
  it("honors an explicit hex when valid", () => {
    expect(resolveCategoryColor("x", "#3b82f6").hex).toBe("#3b82f6");
  });
});
```

Run: `pnpm vitest run src/shared/lib/category-colors.test.ts` → fails (module not found), then passes after Step 1.

- [ ] **Step 3: Tag types**

Create `src/features/tagging/types.ts`:

```typescript
export type TaggableEntity = "molecules" | "protocols" | "projects" | "collections";

export interface Tag {
  id: string;
  workspace_id: string;
  key: string;
  value: string | null;
  created_by: string;
  created_at: string;
}

export interface TagInput {
  key: string;
  value?: string | null;
}
```

- [ ] **Step 4: Entity-tag hooks**

Create `src/features/tagging/hooks/use-entity-tags.ts`:

```typescript
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showError, showSuccess } from "@/shared/lib/toast";
import type { Tag, TaggableEntity, TagInput } from "../types";

const entityTagsKey = (entity: TaggableEntity, id: string) => ["entity-tags", entity, id];

export function useEntityTags(entity: TaggableEntity, id: string | undefined) {
  return useQuery({
    queryKey: id ? entityTagsKey(entity, id) : ["entity-tags", entity, "none"],
    enabled: !!id,
    queryFn: () =>
      customInstance<Tag[]>({ url: `/api/v1/${entity}/${id}/tags`, method: "GET" }),
  });
}

export function useAssignTag(entity: TaggableEntity, id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: TagInput) =>
      customInstance<Tag>({
        url: `/api/v1/${entity}/${id}/tags`,
        method: "POST",
        data: { key: input.key, value: input.value ?? null },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: entityTagsKey(entity, id) });
      qc.invalidateQueries({ queryKey: ["tags"] }); // refresh autocomplete pool
    },
    onError: (e: Error) => showError(e.message || "Failed to add tag"),
  });
}

export function useUnassignTag(entity: TaggableEntity, id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tagId: string) =>
      customInstance<void>({
        url: `/api/v1/${entity}/${id}/tags/${tagId}`,
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: entityTagsKey(entity, id) }),
    onError: (e: Error) => showError(e.message || "Failed to remove tag"),
  });
}
```

- [ ] **Step 5: Admin/search tag hooks**

Create `src/features/tagging/hooks/use-tags.ts`:

```typescript
"use client";

import { useQuery } from "@tanstack/react-query";
import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type { Tag } from "../types";

const tagHooks = createCrudHooks<Tag, { key: string; value?: string | null }, { key: string; value?: string | null }>({
  entityName: "Tag",
  baseUrl: "/api/v1/tags",
  queryKey: ["tags"],
});

/** Rename = PATCH /api/v1/tags/{id}; Delete = DELETE; Merge = POST /{id}/merge. */
export const useRenameTag = tagHooks.useUpdate;
export const useDeleteTag = tagHooks.useDelete;
export const useMergeTags = () => tagHooks.useAction("merge", "Tags merged");

/** Autocomplete / management list. `q` substring; `mine` = created-by-me. */
export function useTags(params?: { q?: string; mine?: boolean; limit?: number }) {
  const search: Record<string, string> = {};
  if (params?.q) search.q = params.q;
  if (params?.mine) search.mine = "true";
  if (params?.limit) search.limit = String(params.limit);
  return useQuery({
    queryKey: ["tags", search],
    queryFn: () => customInstance<Tag[]>({ url: "/api/v1/tags", method: "GET", params: search }),
  });
}
```

- [ ] **Step 6: Verify + commit**

Run `pnpm vitest run src/shared/lib/category-colors.test.ts` (pass) and `pnpm typecheck` (or `pnpm tsc --noEmit` — check `package.json` scripts) for the new files.

```bash
git add src/shared/lib/category-colors.ts src/shared/lib/category-colors.test.ts \
        src/features/screening-assay/lib/pick-list-colors.ts \
        src/features/tagging/
git commit -m "feat(tagging-ui): color palette hoist + tag types + hooks"
```

---

## Task F5-2: `TagChip` component

**Files:**
- Create: `src/shared/components/tag-chip.tsx`
- Test: `src/shared/components/tag-chip.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/shared/components/tag-chip.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TagChip } from "./tag-chip";

describe("TagChip", () => {
  it("renders key=value", () => {
    render(<TagChip tagKey="project" value="alpha" />);
    expect(screen.getByText("project")).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
  });
  it("renders just the key when value-less", () => {
    render(<TagChip tagKey="favorite" value={null} />);
    expect(screen.getByText("favorite")).toBeInTheDocument();
    expect(screen.queryByText("=")).not.toBeInTheDocument();
  });
  it("calls onRemove when the remove button is clicked", async () => {
    const onRemove = vi.fn();
    render(<TagChip tagKey="x" value={null} onRemove={onRemove} />);
    await userEvent.click(screen.getByRole("button", { name: /remove/i }));
    expect(onRemove).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: Implement `TagChip`**

Create `src/shared/components/tag-chip.tsx`:

```tsx
import { X } from "lucide-react";
import { resolveCategoryColor } from "@/shared/lib/category-colors";
import { cn } from "@/shared/lib/utils";

interface TagChipProps {
  tagKey: string;
  value: string | null;
  /** When provided, renders a remove (×) button. */
  onRemove?: () => void;
  /** When provided, the chip is a button (e.g. click-to-filter). */
  onClick?: () => void;
  className?: string;
  title?: string;
}

export function TagChip({ tagKey, value, onRemove, onClick, className, title }: TagChipProps) {
  const color = resolveCategoryColor(tagKey);
  const label = value ? `${tagKey}=${value}` : tagKey;
  const Wrapper = onClick ? "button" : "span";
  return (
    <Wrapper
      type={onClick ? "button" : undefined}
      onClick={onClick}
      title={title ?? label}
      className={cn(
        "inline-flex w-fit shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        color.bg, // e.g. "bg-blue-500/15 border-blue-500/40"
        onClick && "cursor-pointer transition-colors hover:brightness-110",
        className,
      )}
    >
      <span className={cn("font-semibold", color.text)}>{tagKey}</span>
      {value && (
        <>
          <span className="text-muted-foreground/70">=</span>
          <span className="text-foreground/90">{value}</span>
        </>
      )}
      {onRemove && (
        <button
          type="button"
          aria-label={`Remove ${label}`}
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="-mr-0.5 ml-0.5 rounded-full text-muted-foreground/60 hover:text-destructive"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </Wrapper>
  );
}
```

- [ ] **Step 3: Verify + commit**

Run `pnpm vitest run src/shared/components/tag-chip.test.tsx` → pass.

```bash
git add src/shared/components/tag-chip.tsx src/shared/components/tag-chip.test.tsx
git commit -m "feat(tagging-ui): TagChip (key-hued, removable)"
```

---

## Task F5-3: `TagEditor` (separate Key + Value + autocomplete)

**Files:**
- Create: `src/features/tagging/components/tag-autocomplete.tsx`
- Create: `src/features/tagging/components/tag-editor.tsx`
- Test: `src/features/tagging/components/tag-editor.test.tsx`

Design: a row of current tags (removable `TagChip`s) above a small form — a **Key** combobox + a **Value** combobox (both `tag-autocomplete`, free entry allowed) + an **Add** button. Add → `useAssignTag` (immediate POST); × on a chip → `useUnassignTag` (immediate DELETE). Autocomplete suggestions come from `useTags({ q })` (debounced).

- [ ] **Step 1: `TagAutocomplete`** — a Command/Popover combobox over `useTags(q)` that allows picking an existing key/value OR typing a new one. Mirror the Popover+Command pattern from `collection-section.tsx`:

Create `src/features/tagging/components/tag-autocomplete.tsx`:

```tsx
"use client";

import { useState } from "react";
import { ChevronsUpDown } from "lucide-react";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/shared/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { cn } from "@/shared/lib/utils";
import { useTags } from "../hooks/use-tags";

interface TagAutocompleteProps {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  /** "key" suggests distinct keys; "value" suggests distinct values. */
  field: "key" | "value";
}

export function TagAutocomplete({ value, onChange, placeholder, field }: TagAutocompleteProps) {
  const [open, setOpen] = useState(false);
  const { data: tags } = useTags({ q: value || undefined, limit: 25 });

  // Distinct suggestions for the active field.
  const suggestions = Array.from(
    new Set((tags ?? []).map((t) => (field === "key" ? t.key : t.value ?? "")).filter(Boolean)),
  ).slice(0, 8);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex h-8 w-full items-center justify-between rounded-md border border-input bg-transparent px-2 text-sm shadow-xs",
            !value && "text-muted-foreground",
          )}
        >
          <span className="truncate">{value || placeholder}</span>
          <ChevronsUpDown className="ml-1 h-3 w-3 shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-56 p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            value={value}
            onValueChange={onChange}
            placeholder={placeholder}
            className="h-8 text-sm"
          />
          <CommandList>
            <CommandEmpty className="px-3 py-2 text-xs text-muted-foreground">
              {value ? `Use "${value}"` : "Type to search…"}
            </CommandEmpty>
            <CommandGroup>
              {suggestions.map((s) => (
                <CommandItem
                  key={s}
                  value={s}
                  onSelect={() => {
                    onChange(s);
                    setOpen(false);
                  }}
                  className="text-sm"
                >
                  {s}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
```

- [ ] **Step 2: `TagEditor`**

Create `src/features/tagging/components/tag-editor.tsx`:

```tsx
"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { TagChip } from "@/shared/components/tag-chip";
import type { TaggableEntity } from "../types";
import { useAssignTag, useEntityTags, useUnassignTag } from "../hooks/use-entity-tags";
import { TagAutocomplete } from "./tag-autocomplete";

interface TagEditorProps {
  entity: TaggableEntity;
  entityId: string;
  /** Read-only mode (e.g. for viewers) hides the add form + remove buttons. */
  canEdit?: boolean;
}

export function TagEditor({ entity, entityId, canEdit = true }: TagEditorProps) {
  const { data: tags, isLoading } = useEntityTags(entity, entityId);
  const assign = useAssignTag(entity, entityId);
  const unassign = useUnassignTag(entity, entityId);
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");

  const add = async () => {
    if (!key.trim()) return;
    await assign.mutateAsync({ key: key.trim(), value: value.trim() || null });
    setKey("");
    setValue("");
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1">
        {isLoading && <span className="text-xs text-muted-foreground">Loading tags…</span>}
        {tags?.map((t) => (
          <TagChip
            key={t.id}
            tagKey={t.key}
            value={t.value}
            onRemove={canEdit ? () => unassign.mutate(t.id) : undefined}
          />
        ))}
        {!isLoading && tags?.length === 0 && !canEdit && (
          <span className="text-xs italic text-muted-foreground/60">No tags</span>
        )}
      </div>

      {canEdit && (
        <div className="flex items-end gap-2">
          <div className="w-40">
            <TagAutocomplete value={key} onChange={setKey} placeholder="key" field="key" />
          </div>
          <span className="pb-1.5 text-muted-foreground">=</span>
          <div className="w-40">
            <TagAutocomplete value={value} onChange={setValue} placeholder="value (optional)" field="value" />
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={add}
            disabled={!key.trim() || assign.isPending}
          >
            <Plus className="mr-1 h-3.5 w-3.5" /> Add
          </Button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Test (mock the hooks)**

Create `src/features/tagging/components/tag-editor.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const assignMutate = vi.fn().mockResolvedValue({});
const unassignMutate = vi.fn();

vi.mock("../hooks/use-entity-tags", () => ({
  useEntityTags: () => ({
    data: [{ id: "t1", key: "project", value: "alpha", workspace_id: "w", created_by: "u", created_at: "" }],
    isLoading: false,
  }),
  useAssignTag: () => ({ mutateAsync: assignMutate, isPending: false }),
  useUnassignTag: () => ({ mutate: unassignMutate, isPending: false }),
}));
vi.mock("../hooks/use-tags", () => ({ useTags: () => ({ data: [] }) }));

import { TagEditor } from "./tag-editor";

describe("TagEditor", () => {
  beforeEach(() => {
    assignMutate.mockClear();
    unassignMutate.mockClear();
  });

  it("shows existing tags and removes on ×", async () => {
    render(<TagEditor entity="collections" entityId="c1" />);
    expect(screen.getByText("project")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /remove project=alpha/i }));
    expect(unassignMutate).toHaveBeenCalledWith("t1");
  });

  it("assigns a new tag via the key field + Add", async () => {
    render(<TagEditor entity="collections" entityId="c1" />);
    // type into the Key combobox input
    const keyInput = screen.getByPlaceholderText("key");
    await userEvent.type(keyInput, "assay");
    await userEvent.click(screen.getByRole("button", { name: /add/i }));
    expect(assignMutate).toHaveBeenCalledWith({ key: "assay", value: null });
  });
});
```

> If the Key combobox input isn't reachable as a plain `placeholder` (it's inside a Popover that opens on trigger click), adjust the test to open the popover first (click the "key" trigger) — keep the assertion that `assignMutate` is called with `{key:"assay", value:null}`.

- [ ] **Step 4: Verify + commit**

Run `pnpm vitest run src/features/tagging/components/tag-editor.test.tsx` → pass.

```bash
git add src/features/tagging/components/tag-autocomplete.tsx \
        src/features/tagging/components/tag-editor.tsx \
        src/features/tagging/components/tag-editor.test.tsx
git commit -m "feat(tagging-ui): TagEditor with key/value autocomplete"
```

---

## Task F5-4: Wire `TagEditor` into detail pages

**Files (read each to find the exact insertion point):**
- Modify: `src/features/research-organization/components/collection/collection-header.tsx` (+ its detail page)
- Modify: the molecule detail header/page (find it — `features/chemical-registration/components/molecule-detail*` or similar)

- [ ] **Step 1:** In the collection detail header's meta area, add a tags row below the badges:
```tsx
import { TagEditor } from "@/features/tagging/components/tag-editor";
import { useAuthzHasRole } from "@sentinel-auth/nextjs";
// ...
<div className="mt-2">
  <TagEditor entity="collections" entityId={collection.id} canEdit={useAuthzHasRole("editor")} />
</div>
```
(Use the app's existing role hook — confirm whether it's `useAuthzHasRole("editor")` or similar from `@sentinel-auth/nextjs`, as used in `vocabulary-list.tsx`.)

- [ ] **Step 2:** Do the same on the molecule detail page (entity `"molecules"`, `entityId={molecule.id}`), placed in the header/metadata area.

- [ ] **Step 3:** Manually sanity-check via `pnpm dev` if available, else rely on typecheck/build. Run `pnpm typecheck` + `pnpm lint`.

- [ ] **Step 4: Commit**
```bash
git add -A
git commit -m "feat(tagging-ui): tag editor on collection + molecule detail"
```

---

## Task F5-5: `TagFilter` on project/collection/protocol lists

**Files:**
- Create: `src/features/tagging/components/tag-filter.tsx`
- Modify: `collection-list.tsx`, the projects list, the protocols list, + their list hooks to pass `tags`/`tag_logic`.

- [ ] **Step 1: `TagFilter`** — a Popover trigger button showing the active tag count; inside, a `Command` multi-select over `useTags({q})` (checkable), plus an "All / Any" (`tag_logic`) toggle. Selected tags render as removable `TagChip`s next to the trigger. Emits `({ tagIds, tagLogic })`.

Create `src/features/tagging/components/tag-filter.tsx` (compose Popover + Command like `collection-section`; render selected as `TagChip`; expose `value: {tagIds: string[]; tagLogic: "any"|"all"}` + `onChange`). Keep it presentational — the parent list owns the state and passes `tagIds`/`tagLogic` to its list hook.

- [ ] **Step 2: Thread `tags`/`tag_logic` through the list hooks.** Update `useCollections` (and the projects/protocols list hooks) to accept `{ tags?: string[]; tagLogic?: string }` and pass them as `params` to `customInstance` (the backend F2 added these query params). Example for collections:
```typescript
queryFn: async () => {
  const params: Record<string, unknown> = {};
  if (scope) params.project_ids = scope;
  if (opts?.tags?.length) { params.tags = opts.tags; params.tag_logic = opts.tagLogic ?? "any"; }
  const resp = await customInstance<Collection[] | { items: Collection[] }>({
    url: "/api/v1/collections", method: "GET", ...(Object.keys(params).length ? { params } : {}),
  });
  return Array.isArray(resp) ? resp : resp.items;
},
```
(Add `tags`/`tagLogic` to the query key so the cache keys per filter.)

- [ ] **Step 3: Wire `TagFilter` into each list toolbar** (mirror the `myOnly` toggle placement in `collection-list.tsx`). Hold `{tagIds, tagLogic}` in component state; pass to the list hook.

- [ ] **Step 4:** Typecheck/lint; add a small vitest test for `TagFilter` selection state if practical. Commit:
```bash
git add -A
git commit -m "feat(tagging-ui): TagFilter on project/collection/protocol lists"
```

---

## Task F5-6: `TagSection` in advanced search

**Files:**
- Modify: `src/features/research-organization/types/index.ts`
- Create: `src/features/tagging/components/tag-section.tsx`
- Modify: `src/features/research-organization/components/search/search-form.tsx`

- [ ] **Step 1: Add the criterion type.** In `types/index.ts`: add `"tag"` to `CriterionType`; add `export interface TagCriterion { type: "tag"; tag_ids: string[]; tag_logic?: "any" | "all"; }`; add `TagCriterion` to the `SearchCriterionBase` union.

- [ ] **Step 2: `TagSection`** — mirror `collection-section.tsx`: a tag multi-select (Command/Popover over `useTags`) + an Any/All toggle, with `termsToTagCriteria(...) → SearchCriterion[]` and `tagCriteriaToTerms(...)`. The criterion shape: `{ type: "tag", tag_ids, tag_logic, negate? }`. Selected tags render as `TagChip`s.

Create `src/features/tagging/components/tag-section.tsx` following the `CollectionSection` structure (section header + Add + per-term row + the two converter helpers exported for the search form).

- [ ] **Step 3: Wire into `search-form.tsx`.** In `decomposeQuery`, add `case "tag": tagCriteria.push(c); break;`. Add `const [tagTerms, setTagTerms] = useState(tagCriteriaToTerms(initial.tagCriteria))`. Render `<TagSection terms={tagTerms} onChange={setTagTerms} />` (e.g. alongside the Collections/Keywords columns). In `composeCriteria`, append `...termsToTagCriteria(tagTerms)`. This makes tag filters round-trip through SavedSearch with no backend change.

- [ ] **Step 4:** Typecheck/lint. Commit:
```bash
git add -A
git commit -m "feat(tagging-ui): tag criterion in advanced search"
```

---

## Task F5-7: Admin tag management page

**Files:**
- Create: `src/app/(dashboard)/admin/tags/page.tsx`
- Create: `src/features/tagging/components/tag-list.tsx`
- Create: `src/features/tagging/components/tag-rename-dialog.tsx`
- Create: `src/features/tagging/components/tag-merge-dialog.tsx`
- Modify: `src/shared/lib/navigation.ts`

- [ ] **Step 1: `TagList`** — mirror `vocabulary-list.tsx`: `PageHeader` ("Tags" / "Rename, merge, or remove workspace tags.") + a search input (`useTags({q})`) + a `Table` (columns: Tag [a `TagChip` preview], Created by, Actions). Row actions (admin-gated via `useAuthzHasRole("admin")`): **Rename** (opens `TagRenameDialog`), **Merge** (opens `TagMergeDialog`), **Delete** (`AlertDialog` confirm → `useDeleteTag`). Reuse the `vocabulary-list` skeleton/empty-state patterns.

- [ ] **Step 2: `TagRenameDialog`** — mirror `vocabulary-dialog.tsx`: `Key` + `Value` inputs (prefilled), Save → `useRenameTag(tag.id).mutateAsync({ key, value: value || null })`. A 409 surfaces via the hook's `showError` toast ("already exists — merge instead").

- [ ] **Step 3: `TagMergeDialog`** — pick a TARGET tag (a `TagAutocomplete`/Command picker over `useTags`, excluding the source), confirm copy ("Move all of `source`'s assignments onto `target` and delete `source`."), → `useMergeTags().mutate({ id: sourceId, data: { target_tag_id: targetId } })`. (`useAction("merge")` posts to `/api/v1/tags/{id}/merge` with the body.)

- [ ] **Step 4: Route + nav.** Create `src/app/(dashboard)/admin/tags/page.tsx`:
```tsx
import { TagList } from "@/features/tagging/components/tag-list";
export default function TagsPage() {
  return <TagList />;
}
```
In `src/shared/lib/navigation.ts`, add a `{ title: "Tags", href: "/admin/tags", icon: Tag }` item under the **Administration** group (import `Tag` from `lucide-react`; place under "Vocabularies" or as its own entry).

- [ ] **Step 5:** Typecheck/lint/build. Commit:
```bash
git add -A
git commit -m "feat(tagging-ui): admin tag management page (rename/merge/delete)"
```

---

## Phase 5 Done — Definition of Done

- [ ] `pnpm vitest run src/shared src/features/tagging` → pass (color util, TagChip, TagEditor).
- [ ] `pnpm typecheck` (or `tsc --noEmit`) → clean across the new/modified files.
- [ ] `pnpm lint` → clean.
- [ ] `pnpm build` → succeeds (no type/route errors).
- [ ] Manual check (if `pnpm dev` is available): on a collection detail, add `project=alpha` + `favorite` (chips appear, hued by key); remove one; filter a collections list by a tag; add a Tag section to advanced search + run; rename/merge/delete on `/admin/tags`.

**Deferred (note, don't block):** `orval` regen (needs a live backend) to generate the tag client + drop the stale `tags`/`add_tags`/`remove_tags` types from the molecule models; Playwright E2E (needs the full stack running).

**Delivered:** end-to-end tag UX — key-hued chips, an explicit Key+Value editor, tag filtering on dashboards + advanced search (round-tripping via SavedSearch), and an admin management page — all consistent with Cellar's design system and the standing UX conventions.
