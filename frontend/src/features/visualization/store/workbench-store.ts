import { createStore } from "zustand/vanilla";
import type { Filter } from "../lib/filters";

export const MAX_PANELS = 4;
const MAX_HISTORY = 50;

export type PanelType = "scatter" | "histogram" | "bar" | "box";

export interface Appearance {
  colorBy?: string;
  colorMode: "range" | "bins";
  colorBins?: number[];
  shapeBy?: string;
  sizeBy?: string;
  opacity: number;
  splitBy?: string;
  tooltip: string[];
  showFiltered: boolean;
}

export interface PanelConfig {
  id: string;
  type: PanelType;
  x?: string;
  y?: string;
  category?: string;
  agg?: "count" | "mean" | "median";
  logX?: boolean;
  logY?: boolean;
  bins?: number;
  appearance: Appearance;
}

export type PanelPatch = Partial<Omit<PanelConfig, "id" | "appearance">> & {
  appearance?: Partial<Appearance>;
};

interface Snapshot {
  panels: PanelConfig[];
  filters: Filter[];
}

export interface WorkbenchState extends Snapshot {
  selection: ReadonlySet<string>;
  maximized: string | null;
  past: Snapshot[];
  future: Snapshot[];
  addPanel: (type: PanelType, defaults?: PanelPatch) => string | null;
  updatePanel: (id: string, patch: PanelPatch) => void;
  removePanel: (id: string) => void;
  setFilters: (filters: Filter[]) => void;
  upsertFilter: (filter: Filter) => void;
  removeFilter: (id: string) => void;
  setSelection: (rowIds: Iterable<string>) => void;
  clearSelection: () => void;
  /** Turn the selection into a rows filter (one undo step) and clear it. */
  filterToSelection: () => void;
  setMaximized: (id: string | null) => void;
  undo: () => void;
  redo: () => void;
}

export const DEFAULT_APPEARANCE: Appearance = {
  colorMode: "range",
  opacity: 0.8,
  tooltip: [],
  showFiltered: true,
};

export const canUndo = (s: WorkbenchState) => s.past.length > 0;
export const canRedo = (s: WorkbenchState) => s.future.length > 0;

let panelSeq = 0;

/** A panel of ``type`` with caller-computed ``defaults`` over the default appearance. */
export function makePanel(type: PanelType, defaults: PanelPatch = {}): PanelConfig {
  panelSeq += 1;
  const { appearance, ...rest } = defaults;
  return {
    id: `panel-${Date.now().toString(36)}-${panelSeq}`,
    type,
    ...rest,
    appearance: { ...DEFAULT_APPEARANCE, ...appearance },
  };
}

/** ``p`` with ``patch`` applied; appearance merges field by field. */
export function patchPanel(p: PanelConfig, patch: PanelPatch): PanelConfig {
  const { appearance, ...rest } = patch;
  return { ...p, ...rest, appearance: { ...p.appearance, ...appearance } };
}

/** A maximize survives history steps only while its panel exists. */
const keepMaximized = (id: string | null, panels: PanelConfig[]) =>
  id && panels.some((p) => p.id === id) ? id : null;

export function createWorkbenchStore(initial: { panels: PanelConfig[]; filters?: Filter[] }) {
  return createStore<WorkbenchState>()((set, get) => {
    /** Apply a panels/filters change as one undoable step. */
    const commit = (next: Partial<Snapshot>) => {
      const { panels, filters, past } = get();
      set({
        ...next,
        past: [...past, { panels, filters }].slice(-MAX_HISTORY),
        future: [],
      });
    };

    return {
      panels: initial.panels,
      filters: initial.filters ?? [],
      selection: new Set<string>(),
      maximized: null,
      past: [],
      future: [],

      addPanel: (type, defaults) => {
        if (get().panels.length >= MAX_PANELS) return null;
        const panel = makePanel(type, defaults);
        commit({ panels: [...get().panels, panel] });
        return panel.id;
      },
      updatePanel: (id, patch) => {
        commit({ panels: get().panels.map((p) => (p.id === id ? patchPanel(p, patch) : p)) });
      },
      removePanel: (id) => {
        commit({ panels: get().panels.filter((p) => p.id !== id) });
        if (get().maximized === id) set({ maximized: null });
      },
      setFilters: (filters) => commit({ filters }),
      upsertFilter: (filter) => {
        const filters = get().filters;
        const exists = filters.some((f) => f.id === filter.id);
        commit({
          filters: exists
            ? filters.map((f) => (f.id === filter.id ? filter : f))
            : [...filters, filter],
        });
      },
      removeFilter: (id) => commit({ filters: get().filters.filter((f) => f.id !== id) }),
      setSelection: (rowIds) => set({ selection: new Set(rowIds) }),
      clearSelection: () => set({ selection: new Set<string>() }),
      filterToSelection: () => {
        get().upsertFilter({ id: "selection", kind: "rows", rowIds: [...get().selection] });
        set({ selection: new Set<string>() });
      },
      setMaximized: (id) => set({ maximized: id }),
      undo: () => {
        const { past, future, panels, filters } = get();
        const prev = past.at(-1);
        if (!prev) return;
        set({
          ...prev,
          maximized: keepMaximized(get().maximized, prev.panels),
          past: past.slice(0, -1),
          future: [{ panels, filters }, ...future],
        });
      },
      redo: () => {
        const { past, future, panels, filters } = get();
        const next = future[0];
        if (!next) return;
        set({
          ...next,
          maximized: keepMaximized(get().maximized, next.panels),
          past: [...past, { panels, filters }],
          future: future.slice(1),
        });
      },
    };
  });
}

export type WorkbenchStore = ReturnType<typeof createWorkbenchStore>;
