"use client";

import { useCallback, useEffect, useMemo, useReducer } from "react";

export type ExclusionSource = "manual" | "auto_3sigma";

export type ExclusionReason =
  | "outlier"
  | "instrument_artifact"
  | "concentration_error"
  | "contamination"
  | "qc_failure"
  | "other"
  | "auto_3sigma";

export interface DraftExclusion {
  idx: number | null; // null for legacy entries (read-only)
  source: ExclusionSource;
  excluded: boolean;
  reason: ExclusionReason;
  note: string | null;
  author_id: string | null;
  ts: string; // ISO timestamp
  concentration?: number | null;
  response?: number | null;
}

interface CurveLike {
  excluded_points: DraftExclusion[] | null | undefined;
}

interface State {
  initial: DraftExclusion[];
  current: DraftExclusion[];
  history: DraftExclusion[][]; // bounded at HISTORY_CAP — snapshots of `current` BEFORE each mutation
  future: DraftExclusion[][];
}

type Action =
  | { type: "toggle"; idx: number; authorId: string; now: string }
  | { type: "undo" }
  | { type: "redo" }
  | { type: "resetToSaved" }
  | { type: "seed"; entries: DraftExclusion[] };

const HISTORY_CAP = 50;

function pushHistory(
  history: DraftExclusion[][],
  snapshot: DraftExclusion[],
): DraftExclusion[][] {
  const next = [...history, snapshot];
  if (next.length > HISTORY_CAP) {
    // Drop the oldest entries to keep the cap.
    return next.slice(next.length - HISTORY_CAP);
  }
  return next;
}

function applyToggle(
  current: DraftExclusion[],
  idx: number,
  authorId: string,
  now: string,
): DraftExclusion[] {
  const existingPos = current.findIndex((e) => e.idx === idx);

  if (existingPos === -1) {
    // No entry for this idx → ADD a new manual exclusion.
    return [
      ...current,
      {
        idx,
        source: "manual",
        excluded: true,
        reason: "other",
        note: null,
        author_id: authorId,
        ts: now,
        concentration: null,
        response: null,
      },
    ];
  }

  const existing = current[existingPos];

  if (existing.source === "manual" && existing.excluded) {
    // Re-include: remove the manual exclusion entry entirely.
    const next = current.slice();
    next.splice(existingPos, 1);
    return next;
  }

  // Otherwise (auto_3sigma suggestion, OR a manual entry with excluded=false
  // — which shouldn't happen in practice but we handle defensively): flip `excluded`.
  // For auto_3sigma we PRESERVE source so the BE knows it originated as a suggestion.
  const next = current.slice();
  next[existingPos] = {
    ...existing,
    excluded: !existing.excluded,
    ts: now,
    author_id: authorId,
  };
  return next;
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "seed": {
      return {
        initial: action.entries,
        current: action.entries,
        history: [],
        future: [],
      };
    }
    case "toggle": {
      // idx=null entries are read-only. The toggle is on a NUMERIC idx,
      // so we can never produce or remove a null-idx row this way. But if
      // somehow the only entry at this idx is legacy (which is impossible
      // since legacy entries have idx=null), guard anyway: applyToggle
      // looks up by exact-equality on idx, so legacy rows are untouched.
      const nextCurrent = applyToggle(
        state.current,
        action.idx,
        action.authorId,
        action.now,
      );
      // No-op guard: if applyToggle didn't change anything, skip history bump.
      if (nextCurrent === state.current) return state;
      return {
        ...state,
        current: nextCurrent,
        history: pushHistory(state.history, state.current),
        future: [], // any new mutation clears the redo stack
      };
    }
    case "undo": {
      if (state.history.length === 0) return state;
      const prev = state.history[state.history.length - 1];
      return {
        ...state,
        current: prev,
        history: state.history.slice(0, -1),
        future: [...state.future, state.current],
      };
    }
    case "redo": {
      if (state.future.length === 0) return state;
      const next = state.future[state.future.length - 1];
      return {
        ...state,
        current: next,
        history: pushHistory(state.history, state.current),
        future: state.future.slice(0, -1),
      };
    }
    case "resetToSaved": {
      return {
        initial: state.initial,
        current: state.initial,
        history: [],
        future: [],
      };
    }
  }
}

export interface UseEditSessionOptions {
  authorId: string;
  /**
   * Stable identifier for the curve being edited. The hook re-seeds the
   * draft whenever this value changes. Pass `undefined` if no curve is
   * loaded yet (the draft will start empty).
   */
  curveId: string | undefined;
  /** Optional override for `Date.now()` (testing). */
  nowProvider?: () => string;
}

export interface UseEditSessionApi {
  draft: { exclusions: DraftExclusion[] };
  dirtyCount: number;
  canUndo: boolean;
  canRedo: boolean;
  toggleExclusion: (idx: number) => void;
  undo: () => void;
  redo: () => void;
  resetToSaved: () => void;
}

function initialEntriesFrom(curve: CurveLike | null | undefined): DraftExclusion[] {
  return curve?.excluded_points ?? [];
}

export function useEditSession(
  curve: CurveLike | null | undefined,
  options: UseEditSessionOptions,
): UseEditSessionApi {
  const { authorId, curveId, nowProvider } = options;

  const [state, dispatch] = useReducer(reducer, undefined, () => {
    const entries = initialEntriesFrom(curve);
    return { initial: entries, current: entries, history: [], future: [] };
  });

  // Re-seed when curveId changes. We intentionally key ONLY on curveId so
  // that an in-place re-fetch (same id, new object reference) doesn't blow
  // away the user's in-progress edits. The consumer should bump curveId
  // when the underlying curve identity truly changes.
  useEffect(() => {
    dispatch({ type: "seed", entries: initialEntriesFrom(curve) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [curveId]);

  const toggleExclusion = useCallback(
    (idx: number) => {
      const now = nowProvider ? nowProvider() : new Date().toISOString();
      dispatch({ type: "toggle", idx, authorId, now });
    },
    [authorId, nowProvider],
  );

  const undo = useCallback(() => dispatch({ type: "undo" }), []);
  const redo = useCallback(() => dispatch({ type: "redo" }), []);
  const resetToSaved = useCallback(
    () => dispatch({ type: "resetToSaved" }),
    [],
  );

  const dirtyCount = useMemo(
    () => computeDirtyCount(state.initial, state.current),
    [state.initial, state.current],
  );

  const draft = useMemo(
    () => ({ exclusions: state.current }),
    [state.current],
  );

  return {
    draft,
    dirtyCount,
    canUndo: state.history.length > 0,
    canRedo: state.future.length > 0,
    toggleExclusion,
    undo,
    redo,
    resetToSaved,
  };
}

/**
 * Compare initial vs current. We key entries by `idx` (legacy entries with
 * idx=null are read-only and never produce dirt). An entry is "dirty" when:
 * - it exists in `current` but not in `initial` (added), OR
 * - it exists in `initial` but not in `current` (removed), OR
 * - both sides have the same `idx` but the `excluded` flag differs.
 */
function computeDirtyCount(
  initial: DraftExclusion[],
  current: DraftExclusion[],
): number {
  // Build maps keyed by numeric idx (skip nulls — legacy rows are immutable).
  const initialMap = new Map<number, DraftExclusion>();
  for (const e of initial) {
    if (e.idx !== null) initialMap.set(e.idx, e);
  }
  const currentMap = new Map<number, DraftExclusion>();
  for (const e of current) {
    if (e.idx !== null) currentMap.set(e.idx, e);
  }

  let dirty = 0;
  const seen = new Set<number>();

  for (const [idx, init] of initialMap) {
    seen.add(idx);
    const curr = currentMap.get(idx);
    if (!curr) {
      // Initial entry was removed (re-include).
      dirty++;
    } else if (curr.excluded !== init.excluded) {
      // `excluded` flag flipped (e.g. suggestion accepted/rejected).
      dirty++;
    }
  }
  for (const [idx] of currentMap) {
    if (!seen.has(idx)) {
      // New entry that wasn't in initial.
      dirty++;
    }
  }
  return dirty;
}
