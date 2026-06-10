"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

export type ViewMode = "table" | "cards" | "scaffold-tree" | "clusters" | "sar";

const _ALL_MODES: ViewMode[] = ["table", "cards", "scaffold-tree", "clusters", "sar"];

/** Maps URL param values to ViewMode values (and vice versa for short forms). */
const URL_TO_MODE: Record<string, ViewMode> = {
  table: "table",
  cards: "cards",
  tree: "scaffold-tree",
  clusters: "clusters",
  sar: "sar",
};

const MODE_TO_URL: Record<ViewMode, string> = {
  table: "table",
  cards: "cards",
  "scaffold-tree": "tree",
  clusters: "clusters",
  sar: "sar",
};

// Test-only re-exports (used by use-view-mode.test.ts)
export const URL_TO_MODE_TEST = URL_TO_MODE;
export const MODE_TO_URL_TEST = MODE_TO_URL;

function parseViewMode(raw: string | null, fallback: ViewMode): ViewMode {
  if (raw && raw in URL_TO_MODE) return URL_TO_MODE[raw];
  return fallback;
}

export interface UseViewModeResult {
  mode: ViewMode;
  setMode: (mode: ViewMode) => void;
}

/**
 * URL-state hook for the view-mode toggle. The current mode is read from
 * the `?view=` search param; setMode rewrites the URL (replace, no scroll).
 * When the new mode equals `defaultMode`, the param is stripped so the
 * URL stays clean.
 */
export function useViewMode(defaultMode: ViewMode): UseViewModeResult {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const mode = parseViewMode(params.get("view"), defaultMode);

  const setMode = useCallback(
    (next: ViewMode) => {
      const sp = new URLSearchParams(params);
      if (next === defaultMode) sp.delete("view");
      else sp.set("view", MODE_TO_URL[next]);
      const qs = sp.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [defaultMode, params, pathname, router],
  );

  return { mode, setMode };
}
