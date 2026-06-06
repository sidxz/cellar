"use client";

import { useCallback, useMemo, useState } from "react";

/**
 * A `Set`-backed selection model for grids/lists where rows are toggled on and
 * off by id. Encapsulates the immutable add/remove dance
 * (`new Set(prev); next.add/delete(id)`) that otherwise gets copy-pasted into
 * every selection grid.
 *
 * - `set(id, on)` — add when `on` is true, remove when false (the
 *   `onSelectChange(id, selected)` grid contract).
 * - `toggle(id)` — flip membership (click-to-toggle).
 * - `clear()` — empty the selection.
 * - `reset(ids)` — replace the whole membership at once (bulk default
 *   expansion, select-all); `reset()` is equivalent to `clear()`.
 * - `has(id)` — membership test.
 *
 * The returned helpers are stable (memoized), so they're safe to pass as
 * effect/callback dependencies.
 */
export interface SelectionSet<T> {
  selected: Set<T>;
  set: (id: T, on: boolean) => void;
  toggle: (id: T) => void;
  clear: () => void;
  reset: (ids?: Iterable<T>) => void;
  has: (id: T) => boolean;
}

export function useSelectionSet<T = string>(initial?: Iterable<T>): SelectionSet<T> {
  const [selected, setSelected] = useState<Set<T>>(() => new Set(initial));

  const set = useCallback((id: T, on: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  const toggle = useCallback((id: T) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const clear = useCallback(() => setSelected(new Set()), []);

  const reset = useCallback((ids?: Iterable<T>) => setSelected(new Set(ids)), []);

  const has = useCallback((id: T) => selected.has(id), [selected]);

  return useMemo(
    () => ({ selected, set, toggle, clear, reset, has }),
    [selected, set, toggle, clear, reset, has],
  );
}
