import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { type DraftExclusion, useEditSession } from "./use-edit-session";

const AUTHOR = "user-uuid-1";
const TS = "2026-05-19T10:00:00Z";

function makeEntry(over: Partial<DraftExclusion> & { idx: number | null }): DraftExclusion {
  return {
    source: "manual",
    excluded: true,
    reason: "outlier",
    note: null,
    author_id: AUTHOR,
    ts: TS,
    concentration: null,
    response: null,
    ...over,
  };
}

const persistedCurve = {
  excluded_points: [
    makeEntry({ idx: 9 }),
    makeEntry({
      idx: 7,
      source: "auto_3sigma",
      excluded: false,
      reason: "auto_3sigma",
    }),
  ],
};

describe("useEditSession", () => {
  it("seeds draft from persisted curve on mount", () => {
    const { result } = renderHook(() =>
      useEditSession(persistedCurve, { authorId: AUTHOR, curveId: "curve-1" }),
    );
    expect(result.current.draft.exclusions).toHaveLength(2);
    expect(result.current.dirtyCount).toBe(0);
  });

  it("seeds with empty exclusions when curve is undefined", () => {
    const { result } = renderHook(() =>
      useEditSession(undefined, { authorId: AUTHOR, curveId: undefined }),
    );
    expect(result.current.draft.exclusions).toHaveLength(0);
    expect(result.current.dirtyCount).toBe(0);
  });

  it("toggleExclusion on a previously-included point adds a manual exclusion", () => {
    const { result } = renderHook(() =>
      useEditSession(persistedCurve, { authorId: AUTHOR, curveId: "curve-1" }),
    );
    act(() => result.current.toggleExclusion(3));
    const draft = result.current.draft.exclusions;
    expect(draft.find((e) => e.idx === 3)?.excluded).toBe(true);
    expect(draft.find((e) => e.idx === 3)?.source).toBe("manual");
    expect(draft.find((e) => e.idx === 3)?.author_id).toBe(AUTHOR);
    expect(result.current.dirtyCount).toBe(1);
  });

  it("toggleExclusion on a suggestion flips it to excluded (accept)", () => {
    const { result } = renderHook(() =>
      useEditSession(persistedCurve, { authorId: AUTHOR, curveId: "curve-1" }),
    );
    act(() => result.current.toggleExclusion(7));
    const entry = result.current.draft.exclusions.find((e) => e.idx === 7)!;
    expect(entry.excluded).toBe(true);
    expect(entry.source).toBe("auto_3sigma"); // source preserved
    expect(result.current.dirtyCount).toBe(1);
  });

  it("toggleExclusion twice on a suggestion: accept then reject", () => {
    const { result } = renderHook(() =>
      useEditSession(persistedCurve, { authorId: AUTHOR, curveId: "curve-1" }),
    );
    act(() => result.current.toggleExclusion(7)); // accept
    act(() => result.current.toggleExclusion(7)); // reject
    const entry = result.current.draft.exclusions.find((e) => e.idx === 7)!;
    expect(entry.excluded).toBe(false);
    expect(entry.source).toBe("auto_3sigma");
    // Back to initial state
    expect(result.current.dirtyCount).toBe(0);
  });

  it("toggleExclusion on a manual exclusion removes it (re-include)", () => {
    const { result } = renderHook(() =>
      useEditSession(persistedCurve, { authorId: AUTHOR, curveId: "curve-1" }),
    );
    act(() => result.current.toggleExclusion(9));
    const draft = result.current.draft.exclusions;
    expect(draft.find((e) => e.idx === 9)).toBeUndefined();
    expect(result.current.dirtyCount).toBe(1);
  });

  it("toggleExclusion on an idx=null entry is a noop", () => {
    const legacyCurve = {
      excluded_points: [makeEntry({ idx: null, source: "auto_3sigma" })],
    };
    const { result } = renderHook(() =>
      useEditSession(legacyCurve, { authorId: AUTHOR, curveId: "legacy-1" }),
    );
    // We can't reconstruct a legacy entry's idx, and the user's toggle is on an idx
    // not present in the draft, so this should ADD a new entry (not affect the legacy one).
    // The "idx=null noop" rule applies to existing legacy entries; they remain untouched.
    const before = result.current.draft.exclusions.find((e) => e.idx === null);
    act(() => result.current.toggleExclusion(0));
    const after = result.current.draft.exclusions.find((e) => e.idx === null);
    expect(after).toEqual(before); // legacy entry unchanged
  });

  it("undo reverts the last toggle", () => {
    const { result } = renderHook(() =>
      useEditSession(persistedCurve, { authorId: AUTHOR, curveId: "curve-1" }),
    );
    act(() => result.current.toggleExclusion(3));
    expect(result.current.dirtyCount).toBe(1);
    act(() => result.current.undo());
    expect(result.current.dirtyCount).toBe(0);
  });

  it("redo replays an undone toggle", () => {
    const { result } = renderHook(() =>
      useEditSession(persistedCurve, { authorId: AUTHOR, curveId: "curve-1" }),
    );
    act(() => result.current.toggleExclusion(3));
    act(() => result.current.undo());
    expect(result.current.canRedo).toBe(true);
    act(() => result.current.redo());
    expect(result.current.dirtyCount).toBe(1);
  });

  it("a new toggle clears the redo stack", () => {
    const { result } = renderHook(() =>
      useEditSession(persistedCurve, { authorId: AUTHOR, curveId: "curve-1" }),
    );
    act(() => result.current.toggleExclusion(3));
    act(() => result.current.undo());
    expect(result.current.canRedo).toBe(true);
    act(() => result.current.toggleExclusion(4));
    expect(result.current.canRedo).toBe(false);
  });

  it("resetToSaved clears all draft changes and history", () => {
    const { result } = renderHook(() =>
      useEditSession(persistedCurve, { authorId: AUTHOR, curveId: "curve-1" }),
    );
    act(() => result.current.toggleExclusion(3));
    act(() => result.current.toggleExclusion(4));
    expect(result.current.dirtyCount).toBe(2);
    act(() => result.current.resetToSaved());
    expect(result.current.dirtyCount).toBe(0);
    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(false);
    expect(result.current.draft.exclusions).toHaveLength(2);
  });

  it("re-seeds on curveId change", () => {
    const { result, rerender } = renderHook(
      ({ curve, curveId }: { curve: typeof persistedCurve; curveId: string }) =>
        useEditSession(curve, { authorId: AUTHOR, curveId }),
      { initialProps: { curve: persistedCurve, curveId: "curve-1" } },
    );
    act(() => result.current.toggleExclusion(3));
    expect(result.current.dirtyCount).toBe(1);

    const newCurve = { excluded_points: [makeEntry({ idx: 1 })] };
    rerender({ curve: newCurve, curveId: "curve-2" });
    expect(result.current.dirtyCount).toBe(0);
    expect(result.current.draft.exclusions).toHaveLength(1);
    expect(result.current.draft.exclusions[0].idx).toBe(1);
  });

  it("does NOT re-seed when curveId is unchanged (preserves edits)", () => {
    const { result, rerender } = renderHook(
      ({ curve, curveId }: { curve: typeof persistedCurve; curveId: string }) =>
        useEditSession(curve, { authorId: AUTHOR, curveId }),
      { initialProps: { curve: persistedCurve, curveId: "curve-1" } },
    );
    act(() => result.current.toggleExclusion(3));
    expect(result.current.dirtyCount).toBe(1);

    // Same curveId, but a new curve object reference (e.g. TanStack refetch)
    const sameContentNewRef = {
      excluded_points: [...persistedCurve.excluded_points],
    };
    rerender({ curve: sameContentNewRef, curveId: "curve-1" });
    // User's edit preserved
    expect(result.current.dirtyCount).toBe(1);
  });

  it("history is bounded at 50 entries", () => {
    const { result } = renderHook(() =>
      useEditSession(persistedCurve, { authorId: AUTHOR, curveId: "curve-1" }),
    );
    for (let i = 0; i < 60; i++) {
      act(() => result.current.toggleExclusion(100 + i));
    }
    let undoCount = 0;
    while (result.current.canUndo) {
      act(() => result.current.undo());
      undoCount++;
      if (undoCount > 100) throw new Error("undo loop unbounded");
    }
    expect(undoCount).toBeLessThanOrEqual(50);
  });

  it("dirtyCount counts both additions and removals", () => {
    const { result } = renderHook(() =>
      useEditSession(persistedCurve, { authorId: AUTHOR, curveId: "curve-1" }),
    );
    // Add a new manual exclusion at idx=3
    act(() => result.current.toggleExclusion(3));
    // Remove the persisted manual exclusion at idx=9
    act(() => result.current.toggleExclusion(9));
    expect(result.current.dirtyCount).toBe(2);
  });
});
