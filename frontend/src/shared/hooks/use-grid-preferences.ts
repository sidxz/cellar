"use client";

import { useCallback, useEffect, useRef } from "react";
import type { ColumnState } from "ag-grid-community";
import type { AgGridReact } from "ag-grid-react";

const STORAGE_KEY_PREFIX = "cv-grid-prefs-";

/**
 * Persist per-grid column visibility, order, and width in localStorage.
 */
export function useGridPreferences(gridId: string) {
  const storageKey = `${STORAGE_KEY_PREFIX}${gridId}`;
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const saveState = useCallback(
    (state: ColumnState[]) => {
      try {
        localStorage.setItem(storageKey, JSON.stringify(state));
      } catch {
        // localStorage full or unavailable — ignore
      }
    },
    [storageKey]
  );

  const loadState = useCallback((): ColumnState[] | null => {
    try {
      const raw = localStorage.getItem(storageKey);
      return raw ? (JSON.parse(raw) as ColumnState[]) : null;
    } catch {
      return null;
    }
  }, [storageKey]);

  const onColumnChanged = useCallback(
    (gridRef: React.RefObject<AgGridReact | null>) => {
      return () => {
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => {
          const api = gridRef.current?.api;
          if (!api) return;
          const state = api.getColumnState();
          if (state) saveState(state);
        }, 500);
      };
    },
    [saveState]
  );

  const applyState = useCallback(
    (gridRef: React.RefObject<AgGridReact | null>) => {
      const saved = loadState();
      if (!saved) return;
      const api = gridRef.current?.api;
      if (!api) return;
      api.applyColumnState({ state: saved, applyOrder: true });
    },
    [loadState]
  );

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  return { onColumnChanged, applyState };
}
