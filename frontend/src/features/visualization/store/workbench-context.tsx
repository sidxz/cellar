"use client";

import { type ReactNode, createContext, useContext, useState } from "react";
import { useStore } from "zustand";
import type { Filter } from "../lib/filters";
import {
  type PanelConfig,
  type WorkbenchState,
  type WorkbenchStore,
  createWorkbenchStore,
} from "./workbench-store";

const WorkbenchContext = createContext<WorkbenchStore | null>(null);

/** One store per mounted workbench, so two open workbenches never share state. */
export function WorkbenchProvider({
  initialPanels,
  initialFilters,
  initialSelection,
  saved,
  children,
}: {
  initialPanels: PanelConfig[];
  initialFilters?: Filter[];
  initialSelection?: string[];
  /** The initial panels and filters are a saved view's: changes from them read as unsaved. */
  saved?: boolean;
  children: ReactNode;
}) {
  const [store] = useState(() =>
    createWorkbenchStore({
      panels: initialPanels,
      filters: initialFilters,
      selection: initialSelection,
      saved,
    }),
  );
  return <WorkbenchContext.Provider value={store}>{children}</WorkbenchContext.Provider>;
}

export function useWorkbench<T>(selector: (s: WorkbenchState) => T): T {
  const store = useContext(WorkbenchContext);
  if (!store) throw new Error("useWorkbench must be used inside <WorkbenchProvider>");
  return useStore(store, selector);
}
