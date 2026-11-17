"use client";

import { type ReactNode, createContext, useContext, useState } from "react";
import { useStore } from "zustand";
import type { Filter } from "../lib/filters";
import {
  type PanelConfig,
  type Snapshot,
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
  onSaved,
  children,
}: {
  initialPanels: PanelConfig[];
  initialFilters?: Filter[];
  initialSelection?: string[];
  /** The saved view's panels and filters as last saved: changes from them read as unsaved. */
  saved?: Snapshot;
  /** Told what each save stored. */
  onSaved?: (saved: Snapshot) => void;
  children: ReactNode;
}) {
  const [store] = useState(() =>
    createWorkbenchStore({
      panels: initialPanels,
      filters: initialFilters,
      selection: initialSelection,
      saved,
      onSaved,
    }),
  );
  return <WorkbenchContext.Provider value={store}>{children}</WorkbenchContext.Provider>;
}

/** The store itself: read it at event time, without re-rendering on every change. */
export function useWorkbenchStore(): WorkbenchStore {
  const store = useContext(WorkbenchContext);
  if (!store) throw new Error("useWorkbench must be used inside <WorkbenchProvider>");
  return store;
}

export function useWorkbench<T>(selector: (s: WorkbenchState) => T): T {
  return useStore(useWorkbenchStore(), selector);
}
