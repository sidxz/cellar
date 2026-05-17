"use client";

import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

export type ViewMode = "table" | "cards";

const ALL_MODES: ViewMode[] = ["table", "cards"];

function parseViewMode(raw: string | null, fallback: ViewMode): ViewMode {
  if (raw && (ALL_MODES as string[]).includes(raw)) return raw as ViewMode;
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
      else sp.set("view", next);
      const qs = sp.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [defaultMode, params, pathname, router],
  );

  return { mode, setMode };
}
