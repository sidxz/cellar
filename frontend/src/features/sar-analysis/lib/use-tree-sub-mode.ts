"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";

/**
 * Sub-mode WITHIN the scaffold-tree view:
 * - "groups"    flat list of distinct Murcko scaffolds, sorted by count desc.
 *               Chemist default — answers "what chemotypes do I have?"
 * - "hierarchy" Schuffenhauer DAG with the Path A frequency-sort + filters.
 *               Power-user mode for SAR drill-down.
 *
 * Local React state is the source of truth (so toggles work in tests + jsdom
 * without round-tripping through URL/router internals). The URL is a side
 * effect on change: `?sub=hierarchy` is written when the user opts in, removed
 * when they're back at the default. Initial value is read from the URL once
 * on mount so deep-linked `?view=tree&sub=hierarchy` URLs land in hierarchy.
 */
export type TreeSubMode = "groups" | "hierarchy";

const DEFAULT_SUB_MODE: TreeSubMode = "groups";
const PARAM = "sub";

function parse(raw: string | null): TreeSubMode {
  return raw === "hierarchy" ? "hierarchy" : DEFAULT_SUB_MODE;
}

function writeUrl(next: TreeSubMode): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (next === DEFAULT_SUB_MODE) {
    url.searchParams.delete(PARAM);
  } else {
    url.searchParams.set(PARAM, next);
  }
  // replaceState avoids polluting browser history with every toggle.
  window.history.replaceState({}, "", url.toString());
}

export function useTreeSubMode(): {
  subMode: TreeSubMode;
  setSubMode: (next: TreeSubMode) => void;
} {
  const params = useSearchParams();
  // Read URL exactly once on mount; subsequent state is React-owned.
  // Re-syncing on `params` change every render is unsafe because consumers
  // (and tests) often hand back a new URLSearchParams instance each call,
  // which would clobber user-driven toggles. Back-button-mid-session
  // mode switching is a rare ask; add a popstate listener if a chemist
  // actually requests it.
  const [subMode, setLocal] = useState<TreeSubMode>(() => parse(params.get(PARAM)));

  const setSubMode = useCallback((next: TreeSubMode) => {
    setLocal(next);
    writeUrl(next);
  }, []);

  return { subMode, setSubMode };
}
